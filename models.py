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

        conn.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('auto_cleanup_enabled', 'true')
        ''')

        conn.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('auto_cleanup_days', '180')
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


def cleanup_old_pdfs(upload_folder):
    """
    Delete PDF files older than the configured threshold.
    Excludes the currently active PDF from deletion.

    Args:
        upload_folder: Path to the uploads directory

    Returns:
        int: Number of files deleted
    """
    from datetime import timedelta

    # Check if auto cleanup is enabled
    auto_cleanup_enabled = get_setting('auto_cleanup_enabled', 'true')
    if auto_cleanup_enabled.lower() != 'true':
        return 0

    # Get cleanup threshold in days
    cleanup_days = int(get_setting('auto_cleanup_days', '180'))

    # Get currently active PDF ID
    selected_pdf_id = int(get_setting('selected_pdf_id', '0'))

    # If selected_pdf_id is 0, get the actual newest PDF ID to exclude it
    active_pdf_id = None
    if selected_pdf_id == 0:
        newest_pdf = get_newest_pdf()
        if newest_pdf:
            active_pdf_id = newest_pdf['id']
    else:
        active_pdf_id = selected_pdf_id

    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=cleanup_days)

    # Find old PDFs to delete
    with get_db() as conn:
        if active_pdf_id:
            old_pdfs = conn.execute(
                '''SELECT * FROM pdf_files
                   WHERE upload_date < ? AND id != ?''',
                (cutoff_date, active_pdf_id)
            ).fetchall()
        else:
            # No active PDF, delete all old ones
            old_pdfs = conn.execute(
                '''SELECT * FROM pdf_files
                   WHERE upload_date < ?''',
                (cutoff_date,)
            ).fetchall()

        deleted_count = 0
        for pdf in old_pdfs:
            # Delete from database
            conn.execute('DELETE FROM pdf_files WHERE id = ?', (pdf['id'],))

            # Delete physical file
            filepath = os.path.join(upload_folder, pdf['filename'])
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    deleted_count += 1
                except OSError:
                    # Log error but continue with other files
                    pass

        return deleted_count
