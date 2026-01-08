import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DATABASE_PATH = 'kundenstopper.db'


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database with required tables."""
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pdf_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                original_name TEXT NOT NULL,
                upload_date TIMESTAMP NOT NULL,
                file_size INTEGER NOT NULL
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')

        # Initialize default settings
        conn.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('selected_pdf_id', '0')
        ''')

        conn.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('cycle_interval', '10')
        ''')

        conn.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('background_color', '#ffffff')
        ''')

        conn.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('progress_indicator', 'progress')
        ''')


def get_setting(key, default=None):
    """Get a setting value from the database."""
    with get_db() as conn:
        result = conn.execute(
            'SELECT value FROM settings WHERE key = ?', (key,)
        ).fetchone()
        return result['value'] if result else default


def set_setting(key, value):
    """Set a setting value in the database."""
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
            (key, str(value))
        )


def add_pdf(filename, original_name, file_size):
    """Add a new PDF file to the database."""
    with get_db() as conn:
        conn.execute(
            '''INSERT INTO pdf_files (filename, original_name, upload_date, file_size)
               VALUES (?, ?, ?, ?)''',
            (filename, original_name, datetime.now(), file_size)
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def get_pdf(pdf_id):
    """Get a PDF file by ID."""
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM pdf_files WHERE id = ?', (pdf_id,)
        ).fetchone()


def get_all_pdfs(limit=None, offset=0):
    """Get all PDF files, ordered by upload date (newest first)."""
    with get_db() as conn:
        if limit:
            return conn.execute(
                '''SELECT * FROM pdf_files
                   ORDER BY upload_date DESC
                   LIMIT ? OFFSET ?''',
                (limit, offset)
            ).fetchall()
        else:
            return conn.execute(
                'SELECT * FROM pdf_files ORDER BY upload_date DESC'
            ).fetchall()


def get_pdf_count():
    """Get total count of PDF files."""
    with get_db() as conn:
        return conn.execute('SELECT COUNT(*) FROM pdf_files').fetchone()[0]


def update_pdf_name(pdf_id, new_name):
    """Update the original name of a PDF file."""
    with get_db() as conn:
        conn.execute(
            'UPDATE pdf_files SET original_name = ? WHERE id = ?',
            (new_name, pdf_id)
        )


def delete_pdf(pdf_id):
    """Delete a PDF file from the database."""
    with get_db() as conn:
        pdf = get_pdf(pdf_id)
        if pdf:
            conn.execute('DELETE FROM pdf_files WHERE id = ?', (pdf_id,))
            return pdf['filename']
        return None


def get_newest_pdf():
    """Get the newest uploaded PDF file."""
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM pdf_files ORDER BY upload_date DESC LIMIT 1'
        ).fetchone()
