import argparse
import json
import os
from datetime import datetime
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

DEFAULT_JSON = r"C:\Users\Admin\Downloads\Dashboard_data.store_wise_sales.json"

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
    cur.execute("DROP TABLE IF EXISTS store_wise_sales;")

    cur.execute("""
        CREATE TABLE store_wise_sales (
            date DATE PRIMARY KEY,
            sales_data JSONB NOT NULL,
            updated_at TIMESTAMPTZ
        );
    """)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def is_valid_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------

def upsert(cur, document):

    updated_at = None

    if isinstance(document.get("updated_at"), dict):
        updated_at = document["updated_at"].get("$date")

    cur.execute(
        """
        INSERT INTO store_wise_sales (
            date,
            sales_data,
            updated_at
        )
        VALUES (%s, %s, %s)

        ON CONFLICT (date)
        DO UPDATE SET
            sales_data = EXCLUDED.sales_data,
            updated_at = EXCLUDED.updated_at;
        """,
        (
            document.get("date"),
            Json(document.get("sales_data", {})),
            updated_at,
        ),
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Import Store Wise Sales into PostgreSQL"
    )

    parser.add_argument(
        "--file",
        default=DEFAULT_JSON,
        help="MongoDB JSON export",
    )

    args = parser.parse_args()

    path = Path(args.file)

    if not path.exists():
        raise FileNotFoundError(path)

    print("Loading JSON...")

    with open(path, encoding="utf-8") as f:
        documents = json.load(f)

    print(f"Found {len(documents)} documents")

    conn = connect()

    try:

        with conn.cursor() as cur:

            cur.execute(
                "SELECT current_database(), current_schema();"
            )
            print("Connected to:", cur.fetchone())

            create_table(cur)

            imported = 0
            skipped = 0

            for i, doc in enumerate(documents, start=1):

                if not is_valid_date(doc.get("date")):
                    skipped += 1
                    print(
                        f"Skipping row {i}: invalid date '{doc.get('date')}'"
                    )
                    continue

                try:
                    upsert(cur, doc)
                    imported += 1

                    if imported % 100 == 0:
                        conn.commit()
                        print(f"Imported {imported} rows...")

                except Exception:
                    print(f"\nError on row {i}")
                    print(doc)
                    raise

        conn.commit()

        print("\nImport completed successfully.")
        print(f"Imported : {imported}")
        print(f"Skipped  : {skipped}")

    except Exception:

        if not conn.closed:
            conn.rollback()

        raise

    finally:

        if not conn.closed:
            conn.close()


if __name__ == "__main__":
    main()