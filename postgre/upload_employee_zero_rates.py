import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import Json

# ---------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------

ENV_FILE = Path(__file__).with_name("env.development")
load_dotenv(ENV_FILE)

HOST = os.getenv("POSTGRES_HOST")
PORT = int(os.getenv("POSTGRES_PORT", "5432"))
USER = os.getenv("POSTGRES_USER")
PASSWORD = os.getenv("POSTGRES_PASSWORD")
DATABASE = os.getenv("POSTGRES_TARGET_DB") or os.getenv("POSTGRES_DATABASE")

DEFAULT_JSON = r"C:\Users\Admin\Downloads\Dashboard_data.Employee_Zero_Rates.json"


# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------

def connect():
    sslmode = "require" if HOST not in ("localhost", "127.0.0.1") else "prefer"

    return psycopg2.connect(
        host=HOST,
        port=PORT,
        database=DATABASE,
        user=USER,
        password=PASSWORD,
        sslmode=sslmode,
    )


def create_table(cur):
    cur.execute("DROP TABLE IF EXISTS employee_zero_rates;")

    cur.execute("""
        CREATE TABLE employee_zero_rates (
            id SERIAL PRIMARY KEY,
            employee_name TEXT,
            store_name TEXT,
            regular_rate NUMERIC,
            overtime_rate NUMERIC,
            pay NUMERIC,
            raw_payload JSONB
        );
    """)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def to_number(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def insert_row(cur, document):
    cur.execute(
        """
        INSERT INTO employee_zero_rates (
            employee_name,
            store_name,
            regular_rate,
            overtime_rate,
            pay,
            raw_payload
        )
        VALUES (%s, %s, %s, %s, %s, %s);
        """,
        (
            document.get("Employee Name"),
            document.get("Store"),
            to_number(document.get("Regular")),
            to_number(document.get("Overtime")),
            to_number(document.get("Pay")),
            Json(document),
        ),
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import Employee Zero Rates from MongoDB JSON into PostgreSQL"
    )

    parser.add_argument(
        "--file",
        default=DEFAULT_JSON,
        help="Path to MongoDB JSON export",
    )

    args = parser.parse_args()

    path = Path(args.file)

    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    print("Loading JSON...")

    with open(path, "r", encoding="utf-8") as f:
        documents = json.load(f)

    print(f"Found {len(documents)} documents")

    conn = connect()

    try:
        with conn.cursor() as cur:

            cur.execute("SELECT current_database(), current_schema();")
            print("Connected to:", cur.fetchone())

            # Create table if it doesn't exist
            create_table(cur)

            # Replace all existing data
            print("Clearing existing records...")
            cur.execute("TRUNCATE TABLE employee_zero_rates RESTART IDENTITY;")

            count = 0

            for i, doc in enumerate(documents, start=1):
                try:
                    insert_row(cur, doc)
                    count += 1

                    if count % 1000 == 0:
                        print(f"Imported {count} rows...")

                except Exception as e:
                    print(f"\nError importing row {i}")
                    print(doc)
                    raise

        conn.commit()

        print(f"\nSuccessfully imported {count} rows.")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()