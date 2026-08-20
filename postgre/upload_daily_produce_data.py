import argparse
import json
import math
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

DEFAULT_JSON = r"C:\Users\Admin\Downloads\Dashboard_data.daily_produce_data.json"

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
    cur.execute("DROP TABLE IF EXISTS daily_produce_data;")

    cur.execute(
        """
        CREATE TABLE daily_produce_data (
            id BIGSERIAL PRIMARY KEY,
            sku TEXT,
            date DATE,
            establishment TEXT,
            cost NUMERIC,
            final_price NUMERIC,
            gross_margin NUMERIC,
            gross_margin_pct NUMERIC,
            n_items INTEGER,
            product_category TEXT,
            product_name TEXT,
            product_subcategory TEXT,
            product_weight NUMERIC,
            qty_sold_items INTEGER,
            qty_sold_weight NUMERIC,
            total NUMERIC,
            total_sales NUMERIC,
            transaction_date DOUBLE PRECISION,
            updated_at TIMESTAMPTZ,
            vendor DOUBLE PRECISION,
            month TEXT,
            raw_payload JSONB
        );
        """
    )


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

    # Handle MongoDB Extended JSON
    if isinstance(value, dict):
        if "$numberDouble" in value:
            v = value["$numberDouble"]
            if v == "NaN":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

    try:
        v = float(value)
        if math.isnan(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def to_int(value):
    n = to_number(value)
    return int(n) if n is not None else None


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------

def insert_row(cur, document):

    updated_at = None

    if isinstance(document.get("updated_at"), dict):
        updated_at = document["updated_at"].get("$date")

    cur.execute(
        """
        INSERT INTO daily_produce_data (
            sku,
            date,
            establishment,
            cost,
            final_price,
            gross_margin,
            gross_margin_pct,
            n_items,
            product_category,
            product_name,
            product_subcategory,
            product_weight,
            qty_sold_items,
            qty_sold_weight,
            total,
            total_sales,
            transaction_date,
            updated_at,
            vendor,
            month,
            raw_payload
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s
        );
        """,
        (
            document.get("sku"),
            document.get("date"),
            document.get("establishment"),
            to_number(document.get("cost")),
            to_number(document.get("final_price")),
            to_number(document.get("gross_margin")),
            to_number(document.get("gross_margin_pct")),
            to_int(document.get("n_items")),
            document.get("product_category"),
            document.get("product_name"),
            document.get("product_subcategory"),
            to_number(document.get("product_weight")),
            to_int(document.get("qty_sold_items")),
            to_number(document.get("qty_sold_weight")),
            to_number(document.get("total")),
            to_number(document.get("total_sales")),
            to_number(document.get("transaction_date")),
            updated_at,
            to_number(document.get("vendor")),
            document.get("month"),
            Json(document),
        ),
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Upload Daily Produce data to PostgreSQL"
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
                    insert_row(cur, doc)
                    imported += 1

                    if imported % 1000 == 0:
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