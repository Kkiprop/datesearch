import json
import os
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2 import OperationalError, sql

ENV_FILE = Path(__file__).with_name("env.development")
load_dotenv(ENV_FILE)

if not ENV_FILE.exists():
    raise FileNotFoundError(f"PostgreSQL environment file not found: {ENV_FILE}")

HOST = os.getenv(
    "POSTGRES_HOST",
    "database-1.<region>.us-west-1.rds.amazonaws.com"
)
try:
    PORT = int(os.environ["POSTGRES_PORT"])
except KeyError as exc:
    raise RuntimeError(f"POSTGRES_PORT is not set in {ENV_FILE}") from exc
except ValueError as exc:
    raise RuntimeError("POSTGRES_PORT must be an integer") from exc
USER = os.getenv("POSTGRES_USER", "")
PASSWORD = os.getenv("POSTGRES_PASSWORD", "" )
DEFAULT_DB = os.getenv("POSTGRES_DEFAULT_DB", "postgres")
OUTPUT_FILE = Path(os.getenv("POSTGRES_ANALYSIS_FILE", "postgres_analysis.json"))


def make_connection(database: str):
    sslmode = "require" if HOST not in ("localhost", "127.0.0.1") else "prefer"
    return psycopg2.connect(
        host=HOST,
        port=PORT,
        user=USER,
        password=PASSWORD,
        database=database,
        sslmode=sslmode,
    )


def list_databases(connection):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT datname FROM pg_database "
            "WHERE datistemplate = false AND datallowconn = true "
            "  AND datname != 'rdsadmin' "
            "ORDER BY datname;"
        )
        return [row[0] for row in cur.fetchall()]


def list_tables(connection):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "  AND table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name;"
        )
        return cur.fetchall()


def get_table_summary(connection, schema, table):
    with connection.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{};").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        )
        row_count = cur.fetchone()[0]

        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position;",
            (schema, table),
        )
        columns = [row[0] for row in cur.fetchall()]
        column_count = len(columns)

    return {
        "schema": schema,
        "table": table,
        "row_count": row_count,
        "column_count": column_count,
        "column_names": columns,
    }


def gather_database_analysis(database_name):
    print(f"\nAnalyzing database: {database_name}")
    try:
        conn = make_connection(database_name)
    except OperationalError as exc:
        print(f"  ⚠️ Unable to connect to database '{database_name}': {exc}")
        return {
            "name": database_name,
            "error": str(exc),
            "table_count": 0,
            "tables": [],
        }

    try:
        tables = list_tables(conn)
        table_summaries = []

        for schema, table in tables:
            summary = get_table_summary(conn, schema, table)
            table_summaries.append(summary)
            print(
                f"  - {schema}.{table}: {summary['row_count']} rows, {summary['column_count']} cols"
            )

        return {
            "name": database_name,
            "table_count": len(table_summaries),
            "tables": table_summaries,
        }
    finally:
        conn.close()


def load_existing_analysis(path: Path):
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        print(f"⚠️ Failed to parse existing JSON file: {path}. Recreating file.")
        return {}


def save_analysis(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    print(f"\n✅ Saved analysis to {path.resolve()}")


def main():
    today_key = date.today().isoformat()
    now_ts = datetime.now().isoformat()

    try:
        conn = make_connection(DEFAULT_DB)
    except OperationalError as exc:
        print(f"❌ Cannot connect to default database '{DEFAULT_DB}': {exc}")
        return

    try:
        database_names = list_databases(conn)
    finally:
        conn.close()

    print(f"\nFound {len(database_names)} databases: {', '.join(database_names)}")
    database_details = []

    for db_name in database_names:
        database_details.append(gather_database_analysis(db_name))

    analysis = {
        "timestamp": now_ts,
        "database_count": len(database_names),
        "databases": database_details,
    }

    existing = load_existing_analysis(OUTPUT_FILE)
    existing[today_key] = analysis
    save_analysis(OUTPUT_FILE, existing)


def print_runtime_notice():
    print(
        "\nRun this script daily from cron. "
        f"It stores results in '{OUTPUT_FILE}'. "
        "Same-date runs overwrite the current day's summary."
    )


if __name__ == "__main__":
    print_runtime_notice()
    main()
