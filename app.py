import os
import uuid
import mimetypes
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import bcrypt

from config import config
from models import (
    init_db, add_pdf, get_pdf, get_all_pdfs, get_pdf_count,
    update_pdf_name, delete_pdf, get_newest_pdf,
    get_setting, set_setting
)

# Add MIME type for .mjs files (ES6 JavaScript modules)
mimetypes.add_type('text/javascript', '.mjs')

app = Flask(__name__)
app.config['SECRET_KEY'] = config.secret_key
app.config['UPLOAD_FOLDER'] = config.upload_folder
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
init_db()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin):
    """Simple user class for Flask-Login."""
    def __init__(self, username):
        self.id = username
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login."""
    if user_id == config.admin_username:
        return User(user_id)
    return None


def verify_password(password):
    """Verify password against stored hash."""
    password_hash = config.admin_password_hash
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


@app.route('/')
def index():
    """Redirect to display page."""
    return redirect(url_for('display'))


@app.route('/display')
def display():
    """Public display page for showing PDFs."""
    return render_template('display.html')


@app.route('/api/current-pdf')
def current_pdf():
    """API endpoint to get the current PDF to display."""
    selected_id = get_setting('selected_pdf_id', '0')

    # If no specific PDF is selected (0), use the newest
    if selected_id == '0':
        pdf = get_newest_pdf()
    else:
        pdf = get_pdf(int(selected_id))

    if pdf:
        cycle_interval = int(get_setting('cycle_interval', '10'))
        background_color = get_setting('background_color', '#ffffff')
        progress_indicator = get_setting('progress_indicator', 'progress')
        return jsonify({
            'filename': pdf['filename'],
            'original_name': pdf['original_name'],
            'cycle_interval': cycle_interval,
            'background_color': background_color,
            'progress_indicator': progress_indicator
        })

    return jsonify({'error': 'Keine PDF verfügbar'}), 404


@app.route('/uploads/<filename>')
def serve_pdf(filename):
    """Serve PDF files."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page."""
    if current_user.is_authenticated:
        return redirect(url_for('admin'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == config.admin_username and verify_password(password):
            user = User(username)
            login_user(user)
            return redirect(url_for('admin'))
        else:
            flash('Ungültiger Benutzername oder Passwort', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Logout the current user."""
    logout_user()
    return redirect(url_for('login'))


@app.route('/admin')
@login_required
def admin():
    """Admin panel for managing PDFs."""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    pdfs = get_all_pdfs(limit=per_page, offset=offset)
    total_pdfs = get_pdf_count()
    total_pages = (total_pdfs + per_page - 1) // per_page

    selected_id = int(get_setting('selected_pdf_id', '0'))
    cycle_interval = int(get_setting('cycle_interval', '10'))
    background_color = get_setting('background_color', '#ffffff')
    progress_indicator = get_setting('progress_indicator', 'progress')

    return render_template(
        'admin.html',
        pdfs=pdfs,
        page=page,
        total_pages=total_pages,
        selected_id=selected_id,
        cycle_interval=cycle_interval,
        background_color=background_color,
        progress_indicator=progress_indicator
    )


@app.route('/admin/upload', methods=['POST'])
@login_required
def upload_pdf():
    """Upload a new PDF file."""
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt', 'error')
        return redirect(url_for('admin'))

    file = request.files['file']

    if file.filename == '':
        flash('Keine Datei ausgewählt', 'error')
        return redirect(url_for('admin'))

    if not file.filename.lower().endswith('.pdf'):
        flash('Nur PDF-Dateien sind erlaubt', 'error')
        return redirect(url_for('admin'))

    # Generate unique filename
    original_name = secure_filename(file.filename)
    file_ext = '.pdf'
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

    # Save file
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    # Add to database
    add_pdf(unique_filename, original_name, file_size)

    flash(f'Datei "{original_name}" erfolgreich hochgeladen', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/rename/<int:pdf_id>', methods=['POST'])
@login_required
def rename_pdf(pdf_id):
    """Rename a PDF file."""
    new_name = request.form.get('new_name', '').strip()

    if not new_name:
        flash('Name darf nicht leer sein', 'error')
        return redirect(url_for('admin'))

    if not new_name.lower().endswith('.pdf'):
        new_name += '.pdf'

    update_pdf_name(pdf_id, new_name)
    flash('Datei erfolgreich umbenannt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/delete/<int:pdf_id>', methods=['POST'])
@login_required
def delete_pdf_file(pdf_id):
    """Delete a PDF file."""
    filename = delete_pdf(pdf_id)

    if filename:
        # Delete physical file
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)

        # If this was the selected PDF, reset to newest
        if int(get_setting('selected_pdf_id', '0')) == pdf_id:
            set_setting('selected_pdf_id', '0')

        flash('Datei erfolgreich gelöscht', 'success')
    else:
        flash('Datei nicht gefunden', 'error')

    return redirect(url_for('admin'))


@app.route('/admin/select/<int:pdf_id>', methods=['POST'])
@login_required
def select_pdf(pdf_id):
    """Select a PDF to display."""
    pdf = get_pdf(pdf_id)

    if pdf:
        set_setting('selected_pdf_id', pdf_id)
        flash(f'Wird jetzt angezeigt: {pdf["original_name"]}', 'success')
    else:
        flash('Datei nicht gefunden', 'error')

    return redirect(url_for('admin'))


@app.route('/admin/select-newest', methods=['POST'])
@login_required
def select_newest():
    """Set display to show newest PDF automatically."""
    set_setting('selected_pdf_id', '0')
    flash('Anzeige auf neueste PDF eingestellt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/settings', methods=['POST'])
@login_required
def update_settings():
    """Update application settings."""
    cycle_interval = request.form.get('cycle_interval', type=int)
    background_color = request.form.get('background_color', '').strip()
    progress_indicator = request.form.get('progress_indicator', '').strip()

    errors = []

    # Validate and update cycle interval
    if cycle_interval and cycle_interval > 0:
        set_setting('cycle_interval', cycle_interval)
    else:
        errors.append('Ungültiges Wechselintervall')

    # Validate and update background color
    if background_color and len(background_color) == 7 and background_color.startswith('#'):
        set_setting('background_color', background_color)
    else:
        errors.append('Ungültige Hintergrundfarbe')

    # Validate and update progress indicator
    if progress_indicator in ['countdown', 'progress', 'none']:
        set_setting('progress_indicator', progress_indicator)
    else:
        errors.append('Ungültige Fortschrittsanzeige')

    if errors:
        for error in errors:
            flash(error, 'error')
    else:
        flash('Einstellungen erfolgreich aktualisiert', 'success')

    return redirect(url_for('admin'))


if __name__ == '__main__':
    from waitress import serve
    print(f"Starting Kundenstopper on {config.host}:{config.port}")
    print(f"Display URL: http://{config.host}:{config.port}/display")
    print(f"Admin URL: http://{config.host}:{config.port}/admin")
    serve(app, host=config.host, port=config.port)
