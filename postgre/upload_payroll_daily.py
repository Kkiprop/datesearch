import argparse
import csv
import io
import os
import re
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
PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DEFAULT_DB = os.getenv("POSTGRES_TARGET_DB") or os.getenv("POSTGRES_DATABASE") or "apnimandi"
DEFAULT_HOST = os.getenv(
    "POSTGRES_HOST",
    "database-1.<region>.us-west-1.rds.amazonaws.com"
)
DEFAULT_PORT = int(os.getenv("POSTGRES_PORT", "5432"))

HEADERS = [
    "id",
    "date",
    "check_date",
    "period_start",
    "period_end",
    "period_length_days",
    "total_pay",
    "employee_count",
    "payroll_data",
    "payroll_sources",
    "updated_at",
    "created_at",
    "raw_payload",
]


def make_connection(database: str, host: str, port: int, user: str, password: str):
    sslmode = "require" if host not in ("localhost", "127.0.0.1") else "prefer"
    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        sslmode=sslmode,
    )


def normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        return "column"
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return normalized.lower()


def split_top_level_fields(line: str):
    fields = []
    current = []
    in_quote = False
    i = 0

    while i < len(line):
        ch = line[i]
        if ch == '"':
            prev = line[i - 1] if i > 0 else None
            nxt = line[i + 1] if i + 1 < len(line) else None
            if in_quote:
                if prev == "'" or nxt == "'":
                    current.append(ch)
                    i += 1
                    continue
                if nxt == "," or nxt is None:
                    in_quote = False
                    current.append(ch)
                    i += 1
                    continue
                current.append(ch)
                i += 1
                continue
            in_quote = True
            current.append(ch)
            i += 1
            continue

        if ch == "," and not in_quote:
            fields.append(''.join(current))
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    fields.append(''.join(current))
    return fields


def read_payroll_daily(path: Path):
    rows = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            fields = split_top_level_fields(line)
            if len(fields) != len(HEADERS):
                raise ValueError(
                    f"Unexpected column count on line {line_number}: "
                    f"expected {len(HEADERS)}, got {len(fields)}"
                )
            rows.append((line_number, fields, raw_line.rstrip("\r\n")))

    return rows


def build_table_columns():
    return HEADERS.copy()


def ensure_table(connection, schema, table_name, columns, replace=False):
    with connection.cursor() as cur:
        if replace:
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.{};").format(sql.Identifier(schema), sql.Identifier(table_name)))
        column_defs = [sql.SQL("{} TEXT").format(sql.Identifier(col)) for col in columns]

        create_sql = sql.SQL("CREATE TABLE IF NOT EXISTS {}.{} ({})").format(
            sql.Identifier(schema),
            sql.Identifier(table_name),
            sql.SQL(", ").join(column_defs),
        )
        cur.execute(create_sql)
        connection.commit()


def copy_rows(connection, schema, table_name, columns, rows):
    if not rows:
        return

    field_names = columns
    with io.StringIO() as buffer:
        writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(field_names)

        for _, fields, _ in rows:
            writer.writerow(fields)

        buffer.seek(0)
        with connection.cursor() as cur:
            copy_sql = sql.SQL("COPY {}.{} ({}) FROM STDIN WITH CSV HEADER").format(
                sql.Identifier(schema),
                sql.Identifier(table_name),
                sql.SQL(", ").join(map(sql.Identifier, field_names)),
            )
            cur.copy_expert(copy_sql, buffer)
        connection.commit()


def parse_args():
    default_path = Path(__file__).with_name("payroll_daily")
    parser = argparse.ArgumentParser(
        description="Upload the raw payroll_daily file into PostgreSQL with every top-level field preserved."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(default_path),
        help=f"Path to the payroll_daily file. Defaults to {default_path}",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="PostgreSQL host (default from env or hosted server).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="PostgreSQL port (default from env or 5432).",
    )
    parser.add_argument(
        "--user",
        default=USER,
        help="PostgreSQL user (default from env).",
    )
    parser.add_argument(
        "--password",
        default=PASSWORD,
        help="PostgreSQL password (default from env).",
    )
    parser.add_argument(
        "--database", "-d",
        default=DEFAULT_DB,
        help="Target PostgreSQL database.",
    )
    parser.add_argument(
        "--schema", "-s",
        default="public",
        help="Target schema.",
    )
    parser.add_argument(
        "--table", "-t",
        default="payroll_daily",
        help="Target table name.",
    )
    parser.add_argument(
        "--replace", "-r",
        action="store_true",
        help="Drop and recreate the destination table before loading.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the file and print the detected schema without uploading.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    path = Path(args.path)
    if not path.exists():
        raise FileNotFoundError(f"Input path not found: {path}")

    rows = read_payroll_daily(path)
    if not rows:
        raise ValueError(f"No rows found in payroll_daily file: {path}")

    columns = build_table_columns()
    print(f"Detected {len(rows)} rows and {len(columns)} columns.")
    print(f"Creating table {args.schema}.{args.table} with columns: {', '.join(columns)}")

    if args.dry_run:
        print("Dry run complete; no data was uploaded. Run without --dry-run to perform the upload.")
        return

    print(
        f"Connecting to PostgreSQL host={args.host} port={args.port} user={args.user} database={args.database}"
    )
    connection = make_connection(args.database, args.host, args.port, args.user, args.password)
    try:
        ensure_table(connection, args.schema, args.table, columns, replace=args.replace)
        copy_rows(connection, args.schema, args.table, columns, rows)
        print(f"Uploaded payroll_daily into {args.database}.{args.schema}.{args.table}")
    finally:
        connection.close()


if __name__ == "__main__":
    import io
    main()
