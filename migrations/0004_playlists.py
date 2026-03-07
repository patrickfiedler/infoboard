"""Add playlist_items table."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'infoboard.db')


def run():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_id INTEGER NOT NULL,
                media_id INTEGER NOT NULL,
                duration INTEGER NOT NULL DEFAULT 10,
                position INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.commit()
    finally:
        conn.close()
