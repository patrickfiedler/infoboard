# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kundenstopper is a Flask-based web application for displaying PDF files with automatic page cycling. It's designed for digital signage, displaying menus, announcements, or promotional materials in fullscreen mode.

## Technology Stack

- **Backend**: Flask 3.0 (Python web framework)
- **WSGI Server**: Waitress 3.0 (production server)
- **Authentication**: Flask-Login 0.6.3 with bcrypt 4.1.2
- **Database**: SQLite (metadata and settings)
- **PDF Rendering**: PDF.js v4.0.379 (local copy)
- **Storage**: Local filesystem

## Common Commands

### Setup and Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Generate admin password hash
python3 generate_password_hash.py

# Create configuration from template
cp config.json.example config.json
# Then edit config.json with your settings
```

### Running the Application

```bash
# Start production server with Waitress
python3 app.py

# The app will display URLs:
# Display: http://localhost:8080/display
# Admin: http://localhost:8080/admin
```

### Database Operations

The database (`kundenstopper.db`) is automatically created on first run. To reset:

```bash
rm kundenstopper.db
python3 app.py  # Will reinitialize database
```

## Architecture

### Application Structure

- **app.py**: Main Flask application with all routes and business logic
  - Routes: `/`, `/display`, `/admin`, `/login`, `/logout`
  - API: `/api/current-pdf`, `/uploads/<filename>`
  - Admin actions: upload, rename, delete, select PDFs, update settings

- **models.py**: SQLite database operations
  - Tables: `pdf_files`, `settings`
  - Functions for CRUD operations on PDFs and settings
  - Context manager for database connections

- **config.py**: Configuration management
  - Loads from `config.json`
  - Provides typed accessors for settings

### Key Components

1. **Display View** (`/display`):
   - Public-facing page that renders PDFs using PDF.js
   - Automatically cycles through pages based on configured interval
   - Polls `/api/current-pdf` every 10 seconds for updates
   - Loops indefinitely when reaching the last page

2. **Admin Panel** (`/admin`):
   - Protected by Flask-Login authentication
   - File management: upload, rename, delete PDFs
   - Selection: choose specific PDF or auto-select newest
   - Settings: configure page cycling interval
   - Pagination: 10 files per page

3. **Authentication**:
   - Single admin user with bcrypt-hashed password
   - Credentials stored in `config.json`
   - Session-based authentication via Flask-Login

4. **File Storage**:
   - PDFs stored in `uploads/` directory
   - Files saved with UUID filenames to prevent conflicts
   - Original names preserved in database
   - Max file size: 100MB

### Database Schema

**pdf_files table**:
- `id`: Primary key
- `filename`: UUID-based filename on disk
- `original_name`: User-friendly display name
- `upload_date`: Timestamp of upload
- `file_size`: File size in bytes

**settings table**:
- `key`: Setting name (primary key)
- `value`: Setting value (stored as text)

Default settings:
- `selected_pdf_id`: ID of currently selected PDF (0 = newest)
- `cycle_interval`: Seconds per page (default: 10)

### PDF.js Integration

- Located in `static/pdfjs/`
- Uses local copy for offline operation
- Files: `pdf.min.js`, `pdf.worker.min.js`
- Renders PDFs to HTML5 canvas
- Scales PDFs to fit screen dimensions

## Important Patterns

### Database Access

Always use the context manager from models.py:

```python
from models import get_db

with get_db() as conn:
    result = conn.execute('SELECT * FROM pdf_files').fetchall()
    # conn.commit() called automatically on success
    # conn.rollback() called on exception
```

### File Upload Handling

```python
# Generate unique filename
unique_filename = f"{uuid.uuid4()}.pdf"
filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

# Save and record
file.save(filepath)
file_size = os.path.getsize(filepath)
add_pdf(unique_filename, original_name, file_size)
```

### Password Verification

```python
import bcrypt

def verify_password(password):
    password_hash = config.admin_password_hash
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
```

## Configuration

The `config.json` file must be created from `config.json.example`. Required fields:

- `admin_username`: Admin login username
- `admin_password_hash`: Bcrypt hash (generate with `generate_password_hash.py`)
- `secret_key`: Flask session secret (change from default!)
- `port`: Server port (default: 8080)
- `host`: Bind address (default: 0.0.0.0)
- `upload_folder`: PDF storage directory (default: uploads)

## Routes Overview

**Public Routes**:
- `GET /`: Redirect to `/display`
- `GET /display`: PDF viewer page
- `GET /api/current-pdf`: JSON API for current PDF info
- `GET /uploads/<filename>`: Serve PDF files
- `GET /login`: Login page
- `POST /login`: Handle login

**Protected Routes** (require authentication):
- `GET /admin`: Admin panel with file list
- `GET /logout`: Logout
- `POST /admin/upload`: Upload new PDF
- `POST /admin/rename/<id>`: Rename PDF
- `POST /admin/delete/<id>`: Delete PDF
- `POST /admin/select/<id>`: Select specific PDF to display
- `POST /admin/select-newest`: Auto-select newest PDF
- `POST /admin/settings`: Update cycling interval

## Security Considerations

- Passwords stored as bcrypt hashes (cost factor: 12)
- File uploads restricted to `.pdf` extension
- Uploaded files use UUID filenames (prevent path traversal)
- Flask sessions use secret key for signing
- Login required for all admin operations
- CSRF protection via Flask forms (POST only)
