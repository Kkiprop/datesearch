import argparse
import csv
import io
import json
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
DEFAULT_DB = os.getenv("POSTGRES_TARGET_DB") or os.getenv("POSTGRES_DATABASE") or os.getenv("POSTGRES_DEFAULT_DB", "postgres")


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


def normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        return "column"
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return normalized.lower()


def infer_type(values):
    if not values:
        return "TEXT"

    def is_bool(value):
        return value in (True, False, "true", "false", "True", "False", "t", "f", "0", "1")

    def is_int(value):
        if isinstance(value, bool):
            return False
        try:
            if value is None or value == "":
                return False
            int(value)
            return True
        except (ValueError, TypeError):
            return False

    def is_float(value):
        try:
            if value is None or value == "":
                return False
            float(value)
            return True
        except (ValueError, TypeError):
            return False

    cleaned = [v for v in values if v not in (None, "")]
    if not cleaned:
        return "TEXT"

    if all(is_bool(v) for v in cleaned):
        return "BOOLEAN"
    if all(is_int(v) for v in cleaned):
        return "INTEGER"
    if all(is_float(v) for v in cleaned):
        return "DOUBLE PRECISION"
    return "TEXT"


def normalize_row(row, field_map):
    normalized = {}
    for original, column_name in field_map.items():
        value = row.get(original)
        if isinstance(value, (dict, list)):
            normalized[column_name] = json.dumps(value, ensure_ascii=False)
        else:
            normalized[column_name] = value
    return normalized


def load_csv_file(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header row: {path}")

        field_map = {}
        normalized_columns = []
        seen = {}
        for header in reader.fieldnames:
            column_name = normalize_identifier(header)
            if not column_name:
                column_name = "column"
            if column_name in seen:
                seen[column_name] += 1
                column_name = f"{column_name}_{seen[column_name]}"
            else:
                seen[column_name] = 1
            field_map[header] = column_name
            normalized_columns.append(column_name)

        rows = []
        for row in reader:
            normalized = normalize_row(row, field_map)
            rows.append(normalized)
    return normalized_columns, rows


def load_json_file(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict):
        if all(isinstance(value, dict) for value in data.values()):
            records = list(data.values())
        else:
            records = [data]
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("JSON file must contain an object or an array of objects.")

    if not records:
        return [], []

    field_map = {}
    normalized_columns = []
    seen = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in record.keys():
            if key in field_map:
                continue
            column_name = normalize_identifier(str(key))
            if not column_name:
                column_name = "column"
            if column_name in seen:
                seen[column_name] += 1
                column_name = f"{column_name}_{seen[column_name]}"
            else:
                seen[column_name] = 1
            field_map[key] = column_name
            normalized_columns.append(column_name)

    rows = []
    for record in records:
        if isinstance(record, dict):
            normalized = normalize_row(record, field_map)
            rows.append(normalized)
        else:
            rows.append({normalized_columns[0]: record} if normalized_columns else {"value": record})

    if not normalized_columns:
        normalized_columns = ["value"]
        rows = [{"value": json.dumps(record, ensure_ascii=False)} for record in records]

    return normalized_columns, rows


def build_table_definition(columns, rows):
    column_types = []
    for column in columns:
        values = [row.get(column) for row in rows]
        column_types.append((column, infer_type(values)))
    definitions = [sql.SQL("{} {}") . format(sql.Identifier(name), sql.SQL(col_type)) for name, col_type in column_types]
    return sql.SQL(", ").join(definitions)


def ensure_table(connection, schema, table_name, columns, rows, replace=False):
    with connection.cursor() as cur:
        if replace:
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.{};").format(sql.Identifier(schema), sql.Identifier(table_name)))
        create_sql = sql.SQL(
            "CREATE TABLE IF NOT EXISTS {}.{} ({})"
        ).format(sql.Identifier(schema), sql.Identifier(table_name), build_table_definition(columns, rows))
        cur.execute(create_sql)
        connection.commit()


def copy_rows(connection, schema, table_name, columns, rows):
    if not rows:
        return

    with io.StringIO() as buffer:
        writer = csv.writer(buffer)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(column, "") for column in columns])
        buffer.seek(0)

        with connection.cursor() as cur:
            copy_sql = sql.SQL(
                "COPY {}.{} ({}) FROM STDIN WITH CSV HEADER"
            ).format(
                sql.Identifier(schema),
                sql.Identifier(table_name),
                sql.SQL(", ").join(map(sql.Identifier, columns)),
            )
            cur.copy_expert(copy_sql, buffer)
        connection.commit()


def process_file(connection, schema, path: Path, table_name: str, replace: bool):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        columns, rows = load_csv_file(path)
    elif suffix == ".json":
        columns, rows = load_json_file(path)
    else:
        raise ValueError(f"Unsupported file type: {path}")

    if not columns:
        raise ValueError(f"No columns detected for file: {path}")

    print(f"Uploading '{path.name}' into {schema}.{table_name} ({len(rows)} rows)")
    ensure_table(connection, schema, table_name, columns, rows, replace=replace)
    copy_rows(connection, schema, table_name, columns, rows)
    print(f"  ✅ Completed {schema}.{table_name}")


def collect_files(path: Path):
    if path.is_file():
        return [path]
    files = []
    for child in sorted(path.iterdir()):
        if child.is_file() and child.suffix.lower() in {".csv", ".json"}:
            files.append(child)
    return files


def parse_args():
    parser = argparse.ArgumentParser(
        description="Upload CSV and JSON files into PostgreSQL by creating tables from file structure."
    )
    parser.add_argument("path", help="Path to a CSV/JSON file or directory containing CSV/JSON files.")
    parser.add_argument("--database", "-d", default=DEFAULT_DB, help="Target PostgreSQL database.")
    parser.add_argument("--schema", "-s", default="public", help="Target schema name.")
    parser.add_argument("--table", "-t", default=None, help="Override the destination table name for a single file.")
    parser.add_argument("--replace", "-r", action="store_true", help="Drop and recreate the target table before loading.")
    parser.add_argument("--dry-run", action="store_true", help="Show the files and tables without uploading.")
    return parser.parse_args()


def main():
    args = parse_args()
    path = Path(args.path)
    if not path.exists():
        raise FileNotFoundError(f"Input path not found: {path}")

    files = collect_files(path)
    if not files:
        raise ValueError(f"No CSV or JSON files found at path: {path}")

    if args.table and len(files) != 1:
        raise ValueError("The --table override may only be used when uploading a single file.")

    print(f"Connecting to database '{args.database}' on host '{HOST}:{PORT}'")
    if args.dry_run:
        for file_path in files:
            target_table = args.table or normalize_identifier(file_path.stem)
            print(f"Dry run: would upload {file_path} -> {args.schema}.{target_table}")
        return

    try:
        connection = make_connection(args.database)
    except OperationalError as exc:
        raise RuntimeError(f"Unable to connect to database '{args.database}': {exc}") from exc

    try:
        for file_path in files:
            target_table = args.table or normalize_identifier(file_path.stem)
            process_file(connection, args.schema, file_path, target_table, replace=args.replace)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
