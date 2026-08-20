import argparse
import csv
import io
import os
import re
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

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
    "ssn",
    "employee_name",
    "regular_rate",
    "overtime_rate",
    "raw_payload",
    "created_at",
    "updated_at",
    "store_name",
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


def read_employee_rates(path: Path):
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

    with io.StringIO() as buffer:
        writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        for _, fields, _ in rows:
            writer.writerow(fields)
        buffer.seek(0)

        with connection.cursor() as cur:
            copy_sql = sql.SQL("COPY {}.{} ({}) FROM STDIN WITH CSV HEADER").format(
                sql.Identifier(schema),
                sql.Identifier(table_name),
                sql.SQL(", ").join(map(sql.Identifier, columns)),
            )
            cur.copy_expert(copy_sql, buffer)
        connection.commit()


def locate_default_employee_rates_file():
    candidate_paths = []
    base_name = "employee_rates"

    script_dir = Path(__file__).resolve().parent
    candidate_paths.extend(script_dir.glob(f"{base_name}*"))
    candidate_paths.extend(Path.cwd().glob(f"{base_name}*"))

    home_dir = Path.home()
    search_dirs = [home_dir, home_dir / "OneDrive", home_dir / "Documents", home_dir / "Downloads"]
    for search_dir in search_dirs:
        if search_dir.exists() and search_dir.is_dir():
            candidate_paths.extend(search_dir.glob(f"**/{base_name}*"))

    candidates = [p for p in dict.fromkeys(candidate_paths) if p.is_file()]
    if len(candidates) == 1:
        return candidates[0]
    return Path(__file__).with_name(base_name)


def parse_args():
    default_path = locate_default_employee_rates_file()
    parser = argparse.ArgumentParser(
        description="Upload raw employee_rates data into PostgreSQL with fixed employee_rates headers."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(default_path),
        help=f"Path to the employee_rates file. Defaults to {default_path}",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="PostgreSQL host.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="PostgreSQL port.",
    )
    parser.add_argument(
        "--user",
        default=USER,
        help="PostgreSQL user.",
    )
    parser.add_argument(
        "--password",
        default=PASSWORD,
        help="PostgreSQL password.",
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
        default="employee_rates",
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

    rows = read_employee_rates(path)
    if not rows:
        raise ValueError(f"No rows found in employee_rates file: {path}")

    print(f"Detected {len(rows)} rows and {len(HEADERS)} columns.")
    print(f"Creating table {args.schema}.{args.table} with columns: {', '.join(HEADERS)}")

    if args.dry_run:
        print("Dry run complete; no data was uploaded. Run without --dry-run to perform the upload.")
        return

    print(
        f"Connecting to PostgreSQL host={args.host} port={args.port} user={args.user} database={args.database}"
    )
    connection = make_connection(args.database, args.host, args.port, args.user, args.password)
    try:
        ensure_table(connection, args.schema, args.table, HEADERS, replace=args.replace)
        copy_rows(connection, args.schema, args.table, HEADERS, rows)
        print(f"Uploaded employee_rates into {args.database}.{args.schema}.{args.table}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
