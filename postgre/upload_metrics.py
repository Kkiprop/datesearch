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

DEFAULT_JSON = r"C:\Users\Admin\Downloads\PrecomputedMetrics.json"

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
    # Recreate table every run to keep schema clean
    cur.execute("DROP TABLE IF EXISTS precomputed_metrics;")

    cur.execute(
        """
        CREATE TABLE precomputed_metrics (
            date DATE PRIMARY KEY,
            metrics JSONB NOT NULL,
            computed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def is_valid_date(value):
    """Validate YYYY-MM-DD format."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------


def upsert(cur, document):

    computed_at = None

    if isinstance(document.get("computedAt"), dict):
        computed_at = document["computedAt"].get("$date")

    cur.execute(
        """
        INSERT INTO precomputed_metrics (
            date,
            metrics,
            computed_at,
            updated_at
        )
        VALUES (%s, %s, %s, NOW())

        ON CONFLICT (date)
        DO UPDATE SET
            metrics = EXCLUDED.metrics,
            computed_at = EXCLUDED.computed_at,
            updated_at = NOW();
        """,
        (
            document.get("date"),
            Json(document.get("metrics", [])),
            computed_at,
        ),
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


def main():

    parser = argparse.ArgumentParser(
        description="Import Precomputed Metrics from MongoDB JSON into PostgreSQL"
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

            create_table(cur)

            imported = 0
            skipped = 0

            for i, doc in enumerate(documents, start=1):

                # Skip invalid dates (e.g. "status")
                if not is_valid_date(doc.get("date")):
                    skipped += 1
                    print(
                        f"Skipping row {i}: invalid date '{doc.get('date')}'"
                    )
                    continue

                try:
                    upsert(cur, doc)
                    imported += 1

                    # Commit every 100 rows
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