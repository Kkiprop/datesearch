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

DEFAULT_JSON = r"C:\Users\Admin\Downloads\Dashboard_data.hourly_sales.json"

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

    cur.execute("DROP TABLE IF EXISTS hourly_sales;")

    cur.execute("""
        CREATE TABLE hourly_sales (
            id BIGSERIAL PRIMARY KEY,
            date DATE NOT NULL,
            hour TIME NOT NULL,
            establishment TEXT NOT NULL,
            daily_sales_total NUMERIC,
            discounts NUMERIC,
            n_guests INTEGER,
            n_items INTEGER,
            n_orders INTEGER,
            sales NUMERIC,
            sales_pct_of_day NUMERIC,
            service_fees NUMERIC,
            tax NUMERIC,
            updated_at TIMESTAMPTZ,
            raw_payload JSONB,
            UNIQUE(date, hour, establishment)
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


def to_number(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value):
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------

def upsert(cur, document):

    updated_at = None

    if isinstance(document.get("updated_at"), dict):
        updated_at = document["updated_at"].get("$date")

    cur.execute(
        """
        INSERT INTO hourly_sales (
            date,
            hour,
            establishment,
            daily_sales_total,
            discounts,
            n_guests,
            n_items,
            n_orders,
            sales,
            sales_pct_of_day,
            service_fees,
            tax,
            updated_at,
            raw_payload
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )

        ON CONFLICT (date, hour, establishment)

        DO UPDATE SET
            daily_sales_total = EXCLUDED.daily_sales_total,
            discounts = EXCLUDED.discounts,
            n_guests = EXCLUDED.n_guests,
            n_items = EXCLUDED.n_items,
            n_orders = EXCLUDED.n_orders,
            sales = EXCLUDED.sales,
            sales_pct_of_day = EXCLUDED.sales_pct_of_day,
            service_fees = EXCLUDED.service_fees,
            tax = EXCLUDED.tax,
            updated_at = EXCLUDED.updated_at,
            raw_payload = EXCLUDED.raw_payload;
        """,
        (
            document.get("date"),
            document.get("hour"),
            document.get("establishment"),
            to_number(document.get("daily_sales_total")),
            to_number(document.get("discounts")),
            to_int(document.get("n_guests")),
            to_int(document.get("n_items")),
            to_int(document.get("n_orders")),
            to_number(document.get("sales")),
            to_number(document.get("sales_pct_of_day")),
            to_number(document.get("service_fees")),
            to_number(document.get("tax")),
            updated_at,
            Json(document),
        ),
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Import Hourly Sales into PostgreSQL"
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

            cur.execute("SELECT current_database(), current_schema();")
            print("Connected to:", cur.fetchone())

            create_table(cur)

            imported = 0
            skipped = 0

            for i, doc in enumerate(documents, start=1):

                if not is_valid_date(doc.get("date")):
                    skipped += 1
                    print(f"Skipping row {i}: invalid date '{doc.get('date')}'")
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