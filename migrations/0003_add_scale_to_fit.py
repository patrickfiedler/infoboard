"""Add scale_to_fit column to media_items table."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'kundenstopper.db')


def run():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("ALTER TABLE media_items ADD COLUMN scale_to_fit INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # Column already exists on fresh installs
    finally:
        conn.close()
