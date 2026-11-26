import os
import re
import uuid
import math
import glob as glob_module
import subprocess
import threading
import shutil
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests as http_requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort, Response, get_template_attribute
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import bcrypt

from PIL import Image as PilImage

from config import config
from models import (
    init_db,
    get_setting, set_setting,
    get_all_displays, get_display, get_display_by_slug,
    create_display, update_display, delete_display,
    add_media, get_media, get_all_media, get_all_pdf_media,
    get_media_count, get_media_counts_by_user, get_newest_media, update_media_name, delete_media,
    add_pdf_render, get_pdf_renders, get_pdf_page_count, get_all_pdf_page_counts, delete_pdf_renders,
    delete_pdf_renders_for_display,
    add_pdf_spread_render, get_pdf_spread_renders,
    delete_pdf_spread_renders, delete_pdf_spread_renders_for_display,
    cleanup_old_media,
    get_url_media_by_url,
    update_media_url,
    get_playlist_items, get_playlist_item, add_playlist_item, remove_playlist_item,
    update_playlist_item, reorder_playlist_items,
    add_gallery, get_gallery_images, add_gallery_image,
    remove_gallery_image, reorder_gallery_images,
    get_zones_for_display, get_zone, get_zone_by_display_and_index,
    create_zone, delete_zone,
    get_all_users, get_user, get_user_by_username,
    create_user, update_user, delete_user,
    WHOLE_DISPLAY, get_user_access, set_user_access, clear_zone_access,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = config.secret_key
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # no login cookie on cross-site requests
app.config['UPLOAD_FOLDER'] = config.upload_folder
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

RENDERS_FOLDER = 'renders'

def _get_app_version():
    """Git commit hash of the running checkout, used by the display page to
    detect a deploy and auto-reload. Falls back to this file's mtime outside git."""
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=os.path.dirname(os.path.abspath(__file__)), stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return str(int(os.path.getmtime(__file__)))

APP_VERSION = _get_app_version()

def _p(t, l, w, h):
    return {'top': t, 'left': l, 'width': w, 'height': h}

LAYOUT_PRESETS = {
    'fullscreen': {'zones': 1, 'label': 'Vollbild',
                   'zone_labels': ['Vollbild'],
                   'preview': [_p('0%','0%','100%','100%')]},
    'split-h':    {'zones': 2, 'label': '2 Hälften (nebeneinander)',
                   'zone_labels': ['Links', 'Rechts'],
                   'preview': [_p('0%','0%','50%','100%'), _p('0%','50%','50%','100%')]},
    'split-v':    {'zones': 2, 'label': '2 Hälften (übereinander)',
                   'zone_labels': ['Oben', 'Unten'],
                   'preview': [_p('0%','0%','100%','50%'), _p('50%','0%','100%','50%')]},
    'sidebar-r':  {'zones': 2, 'label': 'Hauptbereich + Spalte (70/30)',
                   'zone_labels': ['Hauptbereich', 'Spalte'],
                   'preview': [_p('0%','0%','70%','100%'), _p('0%','70%','30%','100%')]},
    'sidebar-b':  {'zones': 2, 'label': 'Hauptbereich + Ticker (75/25)',
                   'zone_labels': ['Hauptbereich', 'Ticker'],
                   'preview': [_p('0%','0%','100%','75%'), _p('75%','0%','100%','25%')]},
    'thirds-h':   {'zones': 3, 'label': '3 Spalten',
                   'zone_labels': ['Spalte 1', 'Spalte 2', 'Spalte 3'],
                   'preview': [_p('0%','0%','33.33%','100%'), _p('0%','33.33%','33.33%','100%'), _p('0%','66.66%','33.34%','100%')]},
    'quad':       {'zones': 4, 'label': '4 Felder (2×2)',
                   'zone_labels': ['Oben links', 'Oben rechts', 'Unten links', 'Unten rechts'],
                   'preview': [_p('0%','0%','50%','50%'), _p('0%','50%','50%','50%'), _p('50%','0%','50%','50%'), _p('50%','50%','50%','50%')]},
}

COOKIE_HIDE_CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookie_hide.conf')

# JS injected when scale-to-fit is requested: scales the page to fill the iframe viewport.
PROXY_SCALE_JS = """<script>
(function() {
    function scaleToFit() {
        var vw = window.innerWidth;
        var pw = document.documentElement.scrollWidth;
        if (!pw || pw === vw) return;
        var scale = vw / pw;
        document.documentElement.style.transformOrigin = '0 0';
        document.documentElement.style.transform = 'scale(' + scale + ')';
        document.body.style.overflow = 'hidden';
    }
    window.addEventListener('load', scaleToFit);
    window.addEventListener('resize', scaleToFit);
})();
</script>"""

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(RENDERS_FOLDER, exist_ok=True)

init_db()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Allowed upload extensions mapped to content type
ALLOWED_EXTENSIONS = {
    'pdf': 'pdf',
    'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image', 'webp': 'image',
    'mp4': 'video', 'webm': 'video', 'mov': 'video',
}


WEEKDAYS_SHORT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']


class User(UserMixin):
    """The admin (db_id 0, from config.json) or an account from the users table."""

    def __init__(self, db_id, display_name):
        self.db_id = db_id
        self.display_name = display_name
        self.is_admin = db_id == 0
        # The admin's session id is the username, as in single-user versions
        self.id = config.admin_username if self.is_admin else f'user:{db_id}'


def _admin_user():
    return User(0, 'Administrator')


@login_manager.user_loader
def load_user(user_id):
    if user_id == config.admin_username:
        return _admin_user()
    prefix, _, number = user_id.partition(':')
    if prefix == 'user' and number.isdigit():
        row = get_user(int(number))
        if row:
            return User(row['id'], row['display_name'])
    return None


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'ok': False, 'error': 'Keine Berechtigung'}), 403
            flash('Diese Aktion ist nur für Administratoren verfügbar.', 'error')
            return redirect(url_for('admin'))
        return f(*args, **kwargs)
    return decorated


def _can_access_media(media):
    if not media:
        return False
    if current_user.is_admin:
        return True
    return media['user_id'] == current_user.db_id


def _editable_zones(display):
    """Zone indices whose playlist the current user may edit. On a fullscreen
    display, index 0 stands for the display playlist."""
    preset = LAYOUT_PRESETS.get(display['layout_preset'] or 'fullscreen', LAYOUT_PRESETS['fullscreen'])
    every_zone = set(range(preset['zones']))
    if current_user.is_admin:
        return every_zone
    access = get_user_access(current_user.db_id, display['id'])
    if WHOLE_DISPLAY in access:
        return every_zone
    return access & every_zone if preset['zones'] > 1 else set()


def _delete_media_files(result):
    """Remove physical upload, render, and gallery image files returned by delete_media."""
    if not result:
        return
    if result['filename']:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], result['filename'])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
    for display_id, render_filename in result['renders']:
        render_path = os.path.join(RENDERS_FOLDER, str(display_id), render_filename)
        if os.path.exists(render_path):
            try:
                os.remove(render_path)
            except OSError:
                pass
    for gal_filename in result.get('gallery_images', []):
        gal_path = os.path.join(app.config['UPLOAD_FOLDER'], gal_filename)
        if os.path.exists(gal_path):
            try:
                os.remove(gal_path)
            except OSError:
                pass


def verify_password(password):
    password_hash = config.admin_password_hash
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


# ---------- PDF rendering ----------

# In-memory render job state: {media_id: {'status': 'rendering'|'done'|'error',
#                                          'done': int, 'total': int, 'errors': []}}
render_jobs = {}


def _render_pdf_background(filepath, media_id, displays, upload_folder):
    render_jobs[media_id] = {'status': 'rendering', 'done': 0, 'total': len(displays), 'errors': []}
    for display in displays:
        try:
            render_pdf_for_display(filepath, media_id, display)
        except RuntimeError as e:
            render_jobs[media_id]['errors'].append(f'{display["name"]}: {e}')
        render_jobs[media_id]['done'] += 1
    render_jobs[media_id]['status'] = 'done'
    cleanup_old_media(upload_folder)


def _dpi_for_display(width, height):
    """Calculate a suitable render DPI for a given display resolution."""
    dpi = round(max(width, height) / 7)
    return max(100, min(300, dpi))


_CPU_WORKERS = max(1, config.render_workers or os.cpu_count() or 1)


def _pdf_page_count(filepath):
    """Return page count via pdfinfo, or None if unavailable."""
    try:
        result = subprocess.run(
            ['pdfinfo', filepath], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith('Pages:'):
                    return int(line.split(':', 1)[1].strip())
    except (FileNotFoundError, ValueError, OSError):
        pass
    return None


def _render_pdf_chunk(filepath, dpi, first_page, last_page, prefix_path):
    """Run pdftoppm for a page range. Returns sorted list of output paths."""
    try:
        result = subprocess.run(
            ['pdftoppm', '-r', str(dpi),
             '-f', str(first_page), '-l', str(last_page),
             '-png', filepath, prefix_path],
            capture_output=True, text=True, timeout=120
        )
    except FileNotFoundError:
        raise RuntimeError(
            'pdftoppm nicht gefunden. Bitte poppler-utils installieren: '
            'sudo apt install poppler-utils'
        )
    if result.returncode != 0:
        raise RuntimeError(f'pdftoppm Fehler: {result.stderr.strip()}')
    return sorted(
        glob_module.glob(f'{prefix_path}-*.png'),
        key=lambda p: int(re.search(r'-(\d+)\.png$', p).group(1))
    )


def _find_same_dpi_renders(media_id, dpi, exclude_display_id):
    """Return (display_id, renders) from any other display at the same DPI, or (None, [])."""
    for d in get_all_displays():
        if d['id'] == exclude_display_id:
            continue
        if _dpi_for_display(d['width'], d['height']) == dpi:
            renders = get_pdf_renders(media_id, d['id'])
            if renders:
                return d['id'], renders
    return None, []


def render_pdf_for_display(filepath, media_id, display):
    """Pre-render all pages of a PDF as PNGs for one display. Returns page count."""
    display_id = display['id']
    render_dir = os.path.join(RENDERS_FOLDER, str(display_id))
    os.makedirs(render_dir, exist_ok=True)

    # Remove stale renders for this media+display
    old_renders = delete_pdf_renders(media_id, display_id)
    for fname in old_renders:
        old_path = os.path.join(render_dir, fname)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    dpi = _dpi_for_display(display['width'], display['height'])

    # Fast path: copy renders from another display at the same DPI
    src_display_id, existing = _find_same_dpi_renders(media_id, dpi, display_id)
    if existing:
        src_dir = os.path.join(RENDERS_FOLDER, str(src_display_id))

        def _copy_renders(records, spread_type=None):
            """Copy a list of render records to render_dir. Returns False if any file missing."""
            new_prefix = str(uuid.uuid4())
            copied = []
            for i, r in enumerate(records, 1):
                src = os.path.join(src_dir, r['render_filename'])
                if not os.path.exists(src):
                    return False
                dst_fname = f'{new_prefix}-{i}.png'
                shutil.copy2(src, os.path.join(render_dir, dst_fname))
                copied.append((i, dst_fname))
            for i, dst_fname in copied:
                if spread_type:
                    add_pdf_spread_render(media_id, display_id, spread_type, i, dst_fname)
                else:
                    add_pdf_render(media_id, display_id, i, dst_fname)
            return True

        src_spreads_paired = get_pdf_spread_renders(media_id, src_display_id, 'paired')
        src_spreads_book   = get_pdf_spread_renders(media_id, src_display_id, 'book')

        if (_copy_renders(existing) and
                _copy_renders(src_spreads_paired, 'paired') and
                _copy_renders(src_spreads_book, 'book')):
            return len(existing)

        # Something was missing — clean up partial state and fall through to full render
        delete_pdf_renders(media_id, display_id)
        delete_pdf_spread_renders(media_id, display_id)

    page_count = _pdf_page_count(filepath)
    workers = min(page_count, _CPU_WORKERS) if page_count else 1

    if workers > 1:
        chunk_size = math.ceil(page_count / workers)
        chunks = [
            (w * chunk_size + 1, min((w + 1) * chunk_size, page_count))
            for w in range(workers)
            if w * chunk_size + 1 <= page_count
        ]
        prefixes = [os.path.join(render_dir, str(uuid.uuid4())) for _ in chunks]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_render_pdf_chunk, filepath, dpi, f, l, p): idx
                for idx, ((f, l), p) in enumerate(zip(chunks, prefixes))
            }
            chunk_results = [None] * len(chunks)
            for future in as_completed(futures):
                chunk_results[futures[future]] = future.result()  # raises on error
        pages = [path for chunk in chunk_results for path in chunk]
    else:
        pages = _render_pdf_chunk(filepath, dpi, 1, page_count or 99999,
                                   os.path.join(render_dir, str(uuid.uuid4())))

    if not pages:
        raise RuntimeError('pdftoppm hat keine Seiten ausgegeben — ist die PDF-Datei gültig?')

    for i, page_path in enumerate(pages, 1):
        add_pdf_render(media_id, display_id, i, os.path.basename(page_path))

    _render_pdf_spreads(pages, media_id, display_id, render_dir)
    return len(pages)


def _stitch_spread(left_path, right_path, output_path):
    """Stitch two page images side-by-side. right_path may be None (lone page on left)."""
    left = PilImage.open(left_path).convert('RGB')
    w, h = left.size
    canvas = PilImage.new('RGB', (w * 2, h), (255, 255, 255))
    canvas.paste(left, (0, 0))
    if right_path:
        right = PilImage.open(right_path).convert('RGB')
        canvas.paste(right, (w, 0))
    canvas.save(output_path, 'PNG')


def _render_pdf_spreads(pages, media_id, display_id, render_dir):
    """Generate paired and book spread renders from single-page render paths."""
    # Delete stale spread renders for this media+display
    old = delete_pdf_spread_renders(media_id, display_id)
    for fname in old:
        p = os.path.join(render_dir, fname)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    n = len(pages)
    if n == 0:
        return

    # Build all stitch tasks up front: (left, right, output_path, spread_type, spread_num)
    tasks = []
    prefix_p = str(uuid.uuid4())
    prefix_b = str(uuid.uuid4())

    i, num = 0, 1
    while i < n:
        out = os.path.join(render_dir, f'{prefix_p}-{num}.png')
        tasks.append((pages[i], pages[i + 1] if i + 1 < n else None, out, 'paired', num))
        num += 1
        i += 2

    tasks.append((pages[0], None, os.path.join(render_dir, f'{prefix_b}-1.png'), 'book', 1))
    i, num = 1, 2
    while i < n:
        out = os.path.join(render_dir, f'{prefix_b}-{num}.png')
        tasks.append((pages[i], pages[i + 1] if i + 1 < n else None, out, 'book', num))
        num += 1
        i += 2

    # Stitch all pairs in parallel (I/O-bound: PNG read/write releases GIL)
    with ThreadPoolExecutor(max_workers=_CPU_WORKERS) as pool:
        futures = [pool.submit(_stitch_spread, left, right, out) for left, right, out, _, _ in tasks]
        for f in as_completed(futures):
            f.result()  # propagate exceptions

    for _, _, out, spread_type, num in tasks:
        add_pdf_spread_render(media_id, display_id, spread_type, num, os.path.basename(out))


def render_pdf_for_all_displays(filepath, media_id):
    """Render a PDF for every existing display. Returns dict {display_id: page_count or error}."""
    results = {}
    for display in get_all_displays():
        try:
            results[display['id']] = render_pdf_for_display(filepath, media_id, display)
        except RuntimeError as e:
            results[display['id']] = str(e)
    return results


# ---------- Thumbnail helper ----------

def get_thumbnail_url(media, display_id, gallery_images_map):
    """Return a thumbnail URL string for a media item, or None if unavailable."""
    if not media:
        return None
    ct = media['content_type']
    if ct == 'pdf':
        renders = get_pdf_renders(media['id'], display_id)
        if renders:
            return url_for('serve_render', display_id=display_id, filename=renders[0]['render_filename'])
    elif ct == 'image':
        if media['filename']:
            return url_for('serve_upload', filename=media['filename'])
    elif ct == 'gallery':
        imgs = gallery_images_map.get(media['id'], [])
        if imgs:
            return url_for('serve_upload', filename=imgs[0]['filename'])
    elif ct == 'youtube':
        if media['url']:
            m = re.search(r'/embed/([a-zA-Z0-9_-]+)', media['url'])
            if m:
                return f'https://img.youtube.com/vi/{m.group(1)}/hqdefault.jpg'
    return None


# ---------- URL helpers ----------

def make_youtube_embed_with_params(video_id, controls=False, cc=False, cc_lang='', rel=False, vq='hd1080'):
    """Build a YouTube embed URL from a video ID and display options."""
    params = [
        'autoplay=1', 'mute=1', 'loop=1', f'playlist={video_id}',
        f'controls={"1" if controls else "0"}',
        f'rel={"1" if rel else "0"}',
        'iv_load_policy=3',  # hide annotations
        f'vq={vq}',          # quality hint (may be ignored by YouTube)
    ]
    if cc:
        params.append('cc_load_policy=1')
        if cc_lang.strip():
            params.append(f'cc_lang_pref={cc_lang.strip()}')
    return f'https://www.youtube.com/embed/{video_id}?' + '&'.join(params)


def make_youtube_embed(url):
    """Convert a YouTube watch/short URL to an embed URL with sensible signage defaults."""
    for pattern in (r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]+)',
                    r'youtu\.be/([a-zA-Z0-9_-]+)'):
        m = re.search(pattern, url)
        if m:
            return make_youtube_embed_with_params(m.group(1))
    return url


def parse_youtube_params(embed_url):
    """Extract current embed options from a stored YouTube embed URL."""
    try:
        params = parse_qs(urlparse(embed_url).query)
        return {
            'controls': params.get('controls', ['0'])[0] == '1',
            'cc':       'cc_load_policy' in params,
            'cc_lang':  params.get('cc_lang_pref', [''])[0],
            'rel':      params.get('rel', ['0'])[0] == '1',
            'vq':       params.get('vq', ['hd1080'])[0],
        }
    except Exception:
        return {'controls': False, 'cc': False, 'cc_lang': '', 'rel': False, 'vq': 'hd1080'}


def detect_url_content_type(url):
    """Detect content type for a URL entry."""
    if re.search(r'youtube\.com|youtu\.be', url, re.IGNORECASE):
        return 'youtube'
    return 'url'


# ---------- Public routes ----------

@app.route('/')
def index():
    displays = get_all_displays()
    if displays:
        return redirect(url_for('display_by_slug', slug=displays[0]['slug']))
    return redirect(url_for('display_by_slug', slug='default'))


@app.route('/display')
def display_legacy():
    """Backwards-compatible redirect to first display."""
    displays = get_all_displays()
    slug = displays[0]['slug'] if displays else 'default'
    return redirect(url_for('display_by_slug', slug=slug))


@app.route('/display/<slug>')
def display_by_slug(slug):
    display = get_display_by_slug(slug)
    if not display:
        abort(404)
    layout_preset = display['layout_preset'] if display['layout_preset'] else 'fullscreen'
    zone_count = LAYOUT_PRESETS.get(layout_preset, {'zones': 1})['zones']
    return render_template('display.html', slug=slug, layout_preset=layout_preset, zone_count=zone_count)


def _media_to_item(media, display, spread_mode='none'):
    """Serialize a media item for the display API (used in both single and playlist mode)."""
    item = {'content_type': media['content_type'], 'original_name': media['original_name']}
    if media['content_type'] == 'pdf':
        if spread_mode in ('paired', 'book'):
            renders = get_pdf_spread_renders(media['id'], display['id'], spread_mode)
            if not renders:  # fall back to single pages if spreads not yet generated
                renders = get_pdf_renders(media['id'], display['id'])
        else:
            renders = get_pdf_renders(media['id'], display['id'])
        item['pages'] = [
            url_for('serve_render', display_id=display['id'], filename=r['render_filename'])
            for r in renders
        ]
    elif media['content_type'] == 'gallery':
        images = get_gallery_images(media['id'])
        item['pages'] = [
            url_for('serve_upload', filename=img['filename'])
            for img in images
        ]
    elif media['content_type'] in ('image', 'video'):
        item['url'] = url_for('serve_upload', filename=media['filename'])
        if media['content_type'] == 'video':
            item['video_fit'] = display['video_fit'] or 'contain'
    else:  # youtube, url
        item['url'] = media['url']
        if media['content_type'] == 'url':
            item['scale_to_fit'] = bool(media['scale_to_fit'])
    return item


def _on_today(entries):
    """Playlist entries scheduled for today's weekday (server local time)."""
    today = str(datetime.now().weekday())
    return [e for e in entries if today in e['weekdays']]


def _fallback_media(source):
    """Single item shown without playlist entries. `source` is a display or zone row."""
    selected_id = source['selected_media_id']
    return get_newest_media() if selected_id == 0 else get_media(selected_id)


def _content_response(display, entries, source):
    """JSON for one screen area: today's playlist entries, else the fallback item."""
    common = {
        'background_color': display['background_color'],
        'progress_indicator': display['progress_indicator'],
        'ambient_bg': bool(display['ambient_bg']),
        'version': APP_VERSION,
        'layout_preset': display['layout_preset'] or 'fullscreen',
    }

    # --- Playlist mode ---
    items = []
    for entry in _on_today(entries):
        media = get_media(entry['media_id'])
        if not media:
            continue
        item = _media_to_item(media, display, entry['spread_mode'])
        item['duration'] = entry['duration']
        items.append(item)
    if items:
        return jsonify({**common, 'mode': 'playlist', 'items': items})

    # --- Single item mode ---
    media = _fallback_media(source)
    if not media:
        if entries:  # scheduled for other days only: tell the screen to clear
            return jsonify({**common, 'mode': 'playlist', 'items': []})
        return jsonify({'error': 'Kein Inhalt verfügbar'}), 404

    return jsonify({
        **common,
        'cycle_interval': source['cycle_interval'],
        'video_fit': display['video_fit'] or 'contain',
        **_media_to_item(media, display),
    })


@app.route('/api/display/<slug>')
def display_api(slug):
    """API endpoint: current content info for a display."""
    display = get_display_by_slug(slug)
    if not display:
        return jsonify({'error': 'Display nicht gefunden'}), 404
    return _content_response(display, get_playlist_items('display', display['id']), display)


@app.route('/api/display/<slug>/zone/<int:zone_index>/current')
def zone_api(slug, zone_index):
    """API endpoint: current content info for a specific zone of a display."""
    display = get_display_by_slug(slug)
    if not display:
        return jsonify({'error': 'Display nicht gefunden'}), 404

    # Fullscreen has only the display playlist, even if an old zone record exists
    if zone_index == 0 and (display['layout_preset'] or 'fullscreen') == 'fullscreen':
        return display_api(slug)

    zone = get_zone_by_display_and_index(display['id'], zone_index)

    # Fallback: zone 0 with no zone record uses display-level settings (backward compat)
    if not zone and zone_index == 0:
        return display_api(slug)
    if not zone:
        return jsonify({'error': 'Zone nicht gefunden'}), 404

    return _content_response(display, get_playlist_items('zone', zone['id']), zone)


@app.route('/api/current-pdf')
def current_pdf_legacy():
    """Backwards-compatible API: proxies to first display's API."""
    displays = get_all_displays()
    if not displays:
        return jsonify({'error': 'Keine Anzeige konfiguriert'}), 404
    return display_api(displays[0]['slug'])


@app.route('/api/render-jobs')
@login_required
def api_render_jobs():
    """Return active/recent render jobs visible to the current user."""
    if current_user.is_admin:
        return jsonify(render_jobs)
    visible = {}
    for mid, job in render_jobs.items():
        media = get_media(mid)
        if media and media['user_id'] == current_user.db_id:
            visible[mid] = job
    return jsonify(visible)


@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/renders/<int:display_id>/<filename>')
def serve_render(display_id, filename):
    render_dir = os.path.join(RENDERS_FOLDER, str(display_id))
    return send_from_directory(render_dir, filename)


@app.route('/proxy')
def proxy():
    """Fetch a website server-side so it can be embedded in an iframe.
    Security: only whitelisted URLs (registered url-type media items) are proxied,
    and the page runs sandboxed because it is served from our own address."""
    url = request.args.get('url', '').strip()
    if not url or not url.startswith(('http://', 'https://')):
        abort(400)

    # Whitelist check: only proxy URLs that exist as url-type media items
    if not get_url_media_by_url(url):
        abort(403)

    try:
        resp = http_requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; Infoboard/1.0)'
        })
    except http_requests.RequestException:
        abort(502)

    ct = resp.headers.get('content-type', 'text/html')

    # For HTML: inject <base href>, cookie-hiding CSS, and optionally scale-to-fit JS
    if 'text/html' in ct:
        try:
            cookie_css = f'<style>{open(COOKIE_HIDE_CSS_FILE).read()}</style>'
        except OSError:
            cookie_css = ''
        scale_js = PROXY_SCALE_JS if request.args.get('scale') == 'fit' else ''
        inject = f'<base href="{url}">' + cookie_css + scale_js
        html = resp.text
        if re.search(r'<head', html, re.IGNORECASE):
            html = re.sub(r'(<head[^>]*>)', lambda m: m.group(1) + inject,
                          html, count=1, flags=re.IGNORECASE)
        else:
            html = inject + html
        content = html.encode('utf-8', errors='replace')
        ct = 'text/html; charset=utf-8'
    else:
        content = resp.content

    # Forward no upstream headers (X-Frame-Options would block the iframe,
    # Set-Cookie would write cookies under our origin). The sandbox gives the page
    # an anonymous origin; adding allow-same-origin would undo that.
    return Response(content, status=resp.status_code, content_type=ct,
                    headers={'Content-Security-Policy': 'sandbox allow-scripts'})


# ---------- Auth ----------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if username == config.admin_username and verify_password(password):
            login_user(_admin_user())
            return redirect(url_for('admin'))
        db_user = get_user_by_username(username)
        if db_user and bcrypt.checkpw(password.encode('utf-8'), db_user['password_hash'].encode('utf-8')):
            login_user(User(db_user['id'], db_user['display_name']))
            return redirect(url_for('admin'))
        flash('Ungültiger Benutzername oder Passwort', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------- Admin ----------

def _preview_thumbnail(display_id, entries, fallback, gallery_images_map):
    todays = _on_today(entries)
    media = get_media(todays[0]['media_id']) if todays else fallback
    return get_thumbnail_url(media, display_id, gallery_images_map)


@app.route('/admin')
@login_required
def admin():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    is_admin = current_user.is_admin

    # Users only see displays they were given access to
    all_displays = get_all_displays()
    editable_zones = {d['id']: _editable_zones(d) for d in all_displays}
    displays = [d for d in all_displays if editable_zones[d['id']]]

    # Admin's library lists everything; users list their own files.
    # Playlists only ever take the current user's own files.
    library_owner = None if is_admin else current_user.db_id
    media_list = get_all_media(limit=per_page, offset=offset, user_id=library_owner)
    total_media = get_media_count(user_id=library_owner)
    total_pages = (total_media + per_page - 1) // per_page
    own_media = get_all_media(user_id=current_user.db_id)

    users = get_all_users()
    user_access = {
        u['id']: {d['id']: get_user_access(u['id'], d['id']) for d in all_displays}
        for u in users
    } if is_admin else {}

    auto_cleanup_enabled = get_setting('auto_cleanup_enabled', 'true')
    auto_cleanup_days = int(get_setting('auto_cleanup_days', '180'))

    youtube_params = {
        item['id']: parse_youtube_params(item['url'])
        for item in media_list
        if item['content_type'] == 'youtube' and item['url']
    }

    pdf_media_page_counts = get_all_pdf_page_counts()  # {media_id: page_count} for media library

    gallery_images_map = {
        item['id']: get_gallery_images(item['id'])
        for item in get_all_media()  # playlists may show other users' galleries
        if item['content_type'] == 'gallery'
    }
    gallery_image_counts = {mid: len(imgs) for mid, imgs in gallery_images_map.items()}

    display_playlists = {d['id']: get_playlist_items('display', d['id']) for d in displays}
    display_zones = {d['id']: get_zones_for_display(d['id']) for d in displays}
    zone_playlists = {
        zone['id']: get_playlist_items('zone', zone['id'])
        for d in displays for zone in display_zones[d['id']]
    }

    pdf_page_counts = {}
    for d in displays:
        entries = list(display_playlists[d['id']])
        for zone in display_zones[d['id']]:
            entries += zone_playlists[zone['id']]
        pdf_page_counts[d['id']] = {
            e['media_id']: get_pdf_page_count(e['media_id'], d['id'])
            for e in entries if e['content_type'] == 'pdf'
        }

    display_thumbnails = {
        d['id']: _preview_thumbnail(d['id'], display_playlists[d['id']], _fallback_media(d), gallery_images_map)
        for d in displays
    }
    zone_thumbnails = {
        zone['id']: _preview_thumbnail(d['id'], zone_playlists[zone['id']], None, gallery_images_map)
        for d in displays for zone in display_zones[d['id']]
    }

    return render_template(
        'admin.html',
        is_admin=is_admin,
        users=users,
        user_access=user_access,
        media_counts=get_media_counts_by_user(),
        whole_display=WHOLE_DISPLAY,
        weekdays_short=WEEKDAYS_SHORT,
        editable_zones=editable_zones,
        displays=displays,
        all_displays=all_displays,
        display_playlists=display_playlists,
        display_thumbnails=display_thumbnails,
        own_media=own_media,
        media_list=media_list,
        page=page,
        total_pages=total_pages,
        auto_cleanup_enabled=auto_cleanup_enabled,
        auto_cleanup_days=auto_cleanup_days,
        youtube_params=youtube_params,
        gallery_images_map=gallery_images_map,
        gallery_image_counts=gallery_image_counts,
        pdf_page_counts=pdf_page_counts,
        pdf_media_page_counts=pdf_media_page_counts,
        layout_presets=LAYOUT_PRESETS,
        display_zones=display_zones,
        zone_playlists=zone_playlists,
        zone_thumbnails=zone_thumbnails,
    )


# --- Display management ---

@app.route('/admin/display/create', methods=['POST'])
@admin_required
def create_display_route():
    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip().lower()
    width = request.form.get('width', type=int)
    height = request.form.get('height', type=int)

    if not name or not slug or not width or not height:
        flash('Alle Felder sind erforderlich', 'error')
        return redirect(url_for('admin'))

    if not re.match(r'^[a-z0-9][a-z0-9-]*$', slug):
        flash('URL-Kürzel darf nur Kleinbuchstaben, Ziffern und Bindestriche enthalten', 'error')
        return redirect(url_for('admin'))

    if get_display_by_slug(slug):
        flash(f'URL-Kürzel "{slug}" ist bereits vergeben', 'error')
        return redirect(url_for('admin'))

    display_id = create_display(name, slug, width, height)
    display = get_display(display_id)

    # Render all existing PDFs for this new display
    errors = []
    for media in get_all_pdf_media():
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], media['filename'])
        if os.path.exists(filepath):
            try:
                render_pdf_for_display(filepath, media['id'], display)
            except RuntimeError as e:
                errors.append(f'{media["original_name"]}: {e}')

    if errors:
        flash(f'Display "{name}" erstellt. Render-Fehler: ' + '; '.join(errors), 'error')
    else:
        flash(f'Display "{name}" erfolgreich erstellt', 'success')

    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/settings', methods=['POST'])
@admin_required
def update_display_settings(display_id):
    display = get_display(display_id)
    if not display:
        flash('Display nicht gefunden', 'error')
        return redirect(url_for('admin'))

    name = request.form.get('name', '').strip()
    width = request.form.get('width', type=int)
    height = request.form.get('height', type=int)
    background_color = request.form.get('background_color', '').strip()
    progress_indicator = request.form.get('progress_indicator', '').strip()
    ambient_bg = 1 if request.form.get('ambient_bg') else 0
    cycle_interval = request.form.get('cycle_interval', type=int)

    errors = []
    if not name:
        errors.append('Name darf nicht leer sein')
    if not width or width < 1:
        errors.append('Ungültige Breite')
    if not height or height < 1:
        errors.append('Ungültige Höhe')
    if not (background_color and len(background_color) == 7 and background_color.startswith('#')):
        errors.append('Ungültige Hintergrundfarbe')
    if progress_indicator not in ('progress', 'subtle', 'countdown', 'none'):
        errors.append('Ungültige Fortschrittsanzeige')
    if not cycle_interval or cycle_interval < 1:
        errors.append('Ungültige Standard-Dauer')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('admin'))

    resolution_changed = (width != display['width'] or height != display['height'])

    update_display(display_id, name=name, width=width, height=height,
                   background_color=background_color,
                   progress_indicator=progress_indicator,
                   ambient_bg=ambient_bg,
                   cycle_interval=cycle_interval)

    if resolution_changed:
        display = get_display(display_id)
        render_errors = []
        for media in get_all_pdf_media():
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], media['filename'])
            if os.path.exists(filepath):
                try:
                    render_pdf_for_display(filepath, media['id'], display)
                except RuntimeError as e:
                    render_errors.append(f'{media["original_name"]}: {e}')
        if render_errors:
            flash('Einstellungen gespeichert. Render-Fehler: ' + '; '.join(render_errors), 'error')
        else:
            flash(f'Einstellungen gespeichert, PDFs für neue Auflösung neu gerendert', 'success')
    else:
        flash('Einstellungen gespeichert', 'success')

    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/delete', methods=['POST'])
@admin_required
def delete_display_route(display_id):
    displays = get_all_displays()
    if len(displays) <= 1:
        flash('Das letzte Display kann nicht gelöscht werden', 'error')
        return redirect(url_for('admin'))

    # Clean up render files (single pages + spreads)
    render_filenames = (
        delete_pdf_renders_for_display(display_id) +
        delete_pdf_spread_renders_for_display(display_id)
    )
    render_dir = os.path.join(RENDERS_FOLDER, str(display_id))
    for fname in render_filenames:
        path = os.path.join(render_dir, fname)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    delete_display(display_id)
    flash('Display gelöscht', 'success')
    return redirect(url_for('admin'))



# --- Playlists (one set of routes for display and zone playlists) ---

PLAYLIST_URL = '/admin/<any(display, zone):kind>/<int:owner_id>/playlist'


def _require_playlist_access(kind, owner_id):
    """Abort unless the playlist exists and the current user may edit it."""
    if kind == 'display':
        display, zone_index = get_display(owner_id), 0
    else:
        zone = get_zone(owner_id)
        display = get_display(zone['display_id']) if zone else None
        zone_index = zone['zone_index'] if zone else None
    if not display:
        abort(404)
    if zone_index not in _editable_zones(display):
        abort(403)
    return display


@app.route(f'{PLAYLIST_URL}/add', methods=['POST'])
@login_required
def playlist_add(kind, owner_id):
    display = _require_playlist_access(kind, owner_id)
    media_id = request.form.get('media_id', type=int)
    duration = max(1, request.form.get('duration', 10, type=int))
    media = get_media(media_id) if media_id else None
    # Only the owner adds a file, so deleting your files never changes others' entries
    if not media or media['user_id'] != current_user.db_id:
        return jsonify({'ok': False, 'error': 'Inhalt nicht gefunden'}), 404
    item_id = add_playlist_item(kind, owner_id, media_id, duration)
    entry = get_playlist_item(kind, owner_id, item_id)
    render_row = get_template_attribute('_playlist_row.html', 'playlist_row')
    html = render_row(
        entry,
        page_count=get_pdf_page_count(media_id, display['id']) if media['content_type'] == 'pdf' else 0,
        image_count=len(get_gallery_images(media_id)) if media['content_type'] == 'gallery' else 0,
        can_change=True,
        show_owner=bool(get_all_users()),
        weekdays_short=WEEKDAYS_SHORT,
    )
    return jsonify({'ok': True, 'html': str(html)})


def _parse_entry_value(action, form):
    """Return (column, value) for an entry update, or None if the input is invalid."""
    if action == 'duration':
        duration = form.get('duration', type=int)
        return ('duration', duration) if duration and duration > 0 else None
    if action == 'spread':
        mode = form.get('spread_mode')
        return ('spread_mode', mode) if mode in ('none', 'paired', 'book') else None
    days = ''.join(d for d in '0123456' if d in form.get('weekdays', ''))
    return ('weekdays', days) if days else None


@app.route(f'{PLAYLIST_URL}/item/<int:item_id>/<any(remove, duration, spread, weekdays):action>',
           methods=['POST'])
@login_required
def playlist_item_action(kind, owner_id, item_id, action):
    _require_playlist_access(kind, owner_id)
    entry = get_playlist_item(kind, owner_id, item_id)
    if not entry:
        return jsonify({'ok': False, 'error': 'Eintrag nicht gefunden'}), 404
    if not current_user.is_admin and entry['owner_id'] != current_user.db_id:
        return jsonify({'ok': False, 'error': 'Keine Berechtigung'}), 403
    if action == 'remove':
        remove_playlist_item(kind, owner_id, item_id)
    else:
        update = _parse_entry_value(action, request.form)
        if not update:
            return jsonify({'ok': False, 'error': 'Ungültige Eingabe'}), 400
        update_playlist_item(kind, owner_id, item_id, *update)
    return jsonify({'ok': True})


@app.route(f'{PLAYLIST_URL}/reorder', methods=['POST'])
@login_required
def playlist_reorder(kind, owner_id):
    _require_playlist_access(kind, owner_id)
    ordered_ids = (request.json or {}).get('order', [])
    reorder_playlist_items(kind, owner_id, ordered_ids)
    return jsonify({'ok': True})


@app.route('/admin/gallery/create', methods=['POST'])
@login_required
def gallery_create():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name darf nicht leer sein', 'error')
        return redirect(url_for('admin'))
    add_gallery(name, user_id=current_user.db_id)
    flash(f'Galerie "{name}" erstellt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/gallery/<int:gallery_id>/upload', methods=['POST'])
@login_required
def gallery_upload(gallery_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    media = get_media(gallery_id)
    if not media or media['content_type'] != 'gallery' or not _can_access_media(media):
        if is_ajax:
            return jsonify({'ok': False, 'error': 'Galerie nicht gefunden'}), 404
        flash('Galerie nicht gefunden', 'error')
        return redirect(url_for('admin'))

    files = request.files.getlist('files')
    uploaded = []
    for file in files:
        if not file.filename:
            continue
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            continue
        original_name = secure_filename(file.filename)
        unique_filename = f'{uuid.uuid4()}.{ext}'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        file_size = os.path.getsize(filepath)
        new_id = add_gallery_image(gallery_id, unique_filename, original_name, file_size)
        uploaded.append({'id': new_id, 'filename': unique_filename, 'original_name': original_name})

    if is_ajax:
        return jsonify({'ok': True, 'images': uploaded})
    flash(f'{len(uploaded)} Bild(er) hochgeladen', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/gallery/<int:gallery_id>/image/<int:image_id>/remove', methods=['POST'])
@login_required
def gallery_remove_image(gallery_id, image_id):
    media = get_media(gallery_id)
    if not _can_access_media(media):
        abort(403)
    filename = remove_gallery_image(image_id, gallery_id)
    if filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    return redirect(url_for('admin'))


@app.route('/admin/gallery/<int:gallery_id>/image/reorder', methods=['POST'])
@login_required
def gallery_reorder_images(gallery_id):
    media = get_media(gallery_id)
    if not _can_access_media(media):
        abort(403)
    ordered_ids = (request.json or {}).get('order', [])
    reorder_gallery_images(gallery_id, ordered_ids)
    return jsonify({'ok': True})


@app.route('/admin/display/<int:display_id>/regenerate', methods=['POST'])
@admin_required
def regenerate_renders(display_id):
    display = get_display(display_id)
    if not display:
        flash('Display nicht gefunden', 'error')
        return redirect(url_for('admin'))

    errors = []
    count = 0
    for media in get_all_pdf_media():
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], media['filename'])
        if os.path.exists(filepath):
            try:
                render_pdf_for_display(filepath, media['id'], display)
                count += 1
            except RuntimeError as e:
                errors.append(f'{media["original_name"]}: {e}')

    if errors:
        flash(f'{count} PDF(s) gerendert. Fehler: ' + '; '.join(errors), 'error')
    else:
        flash(f'{count} PDF(s) für "{display["name"]}" erfolgreich neu gerendert', 'success')

    return redirect(url_for('admin'))


# --- Content management ---

@app.route('/admin/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt', 'error')
        return redirect(url_for('admin'))

    file = request.files['file']
    if not file.filename:
        flash('Keine Datei ausgewählt', 'error')
        return redirect(url_for('admin'))

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    content_type = ALLOWED_EXTENSIONS.get(ext)
    if not content_type:
        flash('Nicht unterstütztes Dateiformat. Erlaubt: PDF, Bild (JPG/PNG/GIF/WebP), Video (MP4/WebM/MOV)', 'error')
        return redirect(url_for('admin'))

    original_name = secure_filename(file.filename)
    unique_filename = f'{uuid.uuid4()}.{ext}'
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    media_id = add_media(
        content_type, original_name, filename=unique_filename,
        file_size=file_size, user_id=current_user.db_id,
    )

    # For PDFs: render in background so the upload response is immediate
    if content_type == 'pdf':
        displays = get_all_displays()
        threading.Thread(
            target=_render_pdf_background,
            args=(filepath, media_id, displays, app.config['UPLOAD_FOLDER']),
            daemon=True,
        ).start()
        flash(f'"{original_name}" hochgeladen — wird gerendert…', 'success')
    else:
        deleted_count = cleanup_old_media(app.config['UPLOAD_FOLDER'])
        msg = f'"{original_name}" erfolgreich hochgeladen'
        flash(f'{msg}. {deleted_count} alte Datei(en) gelöscht.' if deleted_count else msg, 'success')

    return redirect(url_for('admin'))


@app.route('/admin/url', methods=['POST'])
@login_required
def add_url():
    name = request.form.get('name', '').strip()
    raw_url = request.form.get('url', '').strip()

    if not name or not raw_url:
        flash('Name und URL sind erforderlich', 'error')
        return redirect(url_for('admin'))

    if not raw_url.startswith(('http://', 'https://')):
        flash('URL muss mit http:// oder https:// beginnen', 'error')
        return redirect(url_for('admin'))

    content_type = detect_url_content_type(raw_url)
    final_url = make_youtube_embed(raw_url) if content_type == 'youtube' else raw_url

    add_media(content_type, name, url=final_url, user_id=current_user.db_id)
    flash(f'"{name}" erfolgreich hinzugefügt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/media/<int:media_id>/url-options', methods=['POST'])
@login_required
def url_options(media_id):
    media = get_media(media_id)
    if not media or media['content_type'] != 'url' or not _can_access_media(media):
        flash('Inhalt nicht gefunden oder kein Website-Typ', 'error')
        return redirect(url_for('admin'))

    new_url = request.form.get('url', '').strip()
    if not new_url.startswith(('http://', 'https://')):
        flash('Ungültige URL', 'error')
        return redirect(url_for('admin'))

    update_media_url(media_id, new_url)
    flash('URL gespeichert', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/media/<int:media_id>/youtube-options', methods=['POST'])
@login_required
def youtube_options(media_id):
    media = get_media(media_id)
    if not media or media['content_type'] != 'youtube' or not _can_access_media(media):
        flash('Inhalt nicht gefunden oder kein YouTube-Typ', 'error')
        return redirect(url_for('admin'))

    m = re.search(r'/embed/([a-zA-Z0-9_-]+)', media['url'])
    if not m:
        flash('Video-ID konnte nicht ermittelt werden', 'error')
        return redirect(url_for('admin'))

    video_id = m.group(1)
    valid_vq = {'hd720', 'hd1080', 'hd1440'}
    vq = request.form.get('vq', 'hd1080')
    if vq not in valid_vq:
        vq = 'hd1080'
    new_url = make_youtube_embed_with_params(
        video_id,
        controls='controls' in request.form,
        cc='cc' in request.form,
        cc_lang=request.form.get('cc_lang', ''),
        rel='rel' in request.form,
        vq=vq,
    )
    update_media_url(media_id, new_url)
    flash('YouTube-Einstellungen gespeichert', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/rename/<int:media_id>', methods=['POST'])
@login_required
def rename_media(media_id):
    new_name = request.form.get('new_name', '').strip()
    if not new_name:
        flash('Name darf nicht leer sein', 'error')
        return redirect(url_for('admin'))

    media = get_media(media_id)
    if not _can_access_media(media):
        flash('Keine Berechtigung', 'error')
        return redirect(url_for('admin'))

    if media['content_type'] == 'pdf' and not new_name.lower().endswith('.pdf'):
        new_name += '.pdf'

    update_media_name(media_id, new_name)
    flash('Umbenennung erfolgreich', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/delete/<int:media_id>', methods=['POST'])
@login_required
def delete_media_item(media_id):
    media = get_media(media_id)
    if not _can_access_media(media):
        flash('Inhalt nicht gefunden oder keine Berechtigung', 'error')
        return redirect(url_for('admin'))

    result = delete_media(media_id)
    if not result:
        flash('Inhalt nicht gefunden', 'error')
        return redirect(url_for('admin'))

    _delete_media_files(result)
    flash('Inhalt erfolgreich gelöscht', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/settings', methods=['POST'])
@admin_required
def update_global_settings():
    auto_cleanup_enabled = request.form.get('auto_cleanup_enabled', '').strip()
    auto_cleanup_days = request.form.get('auto_cleanup_days', type=int)

    errors = []
    if auto_cleanup_enabled not in ('true', 'false'):
        errors.append('Ungültige Auto-Cleanup-Einstellung')
    if not auto_cleanup_days or auto_cleanup_days < 1:
        errors.append('Ungültige Aufbewahrungsdauer')

    if errors:
        for e in errors:
            flash(e, 'error')
    else:
        set_setting('auto_cleanup_enabled', auto_cleanup_enabled)
        set_setting('auto_cleanup_days', auto_cleanup_days)
        flash('Einstellungen gespeichert', 'success')

    return redirect(url_for('admin'))


@app.route('/admin/cleanup', methods=['POST'])
@admin_required
def manual_cleanup():
    deleted_count = cleanup_old_media(app.config['UPLOAD_FOLDER'])
    if deleted_count > 0:
        flash(f'{deleted_count} alte Datei(en) gelöscht', 'success')
    else:
        flash('Keine alten Dateien zum Löschen gefunden', 'info')
    return redirect(url_for('admin'))


# --- Zone management ---

@app.route('/admin/display/<int:display_id>/layout', methods=['POST'])
@admin_required
def update_display_layout(display_id):
    display = get_display(display_id)
    if not display:
        flash('Display nicht gefunden', 'error')
        return redirect(url_for('admin'))

    preset = request.form.get('layout_preset', 'fullscreen')
    if preset not in LAYOUT_PRESETS:
        flash('Ungültiges Layout', 'error')
        return redirect(url_for('admin'))

    zone_count = LAYOUT_PRESETS[preset]['zones']
    existing_zones = get_zones_for_display(display_id)
    existing_by_index = {z['zone_index']: z['id'] for z in existing_zones}

    # Create missing zones
    for i in range(zone_count):
        if i not in existing_by_index:
            create_zone(display_id, i)

    # Delete extra zones
    for idx, zone_id in existing_by_index.items():
        if idx >= zone_count:
            delete_zone(zone_id)

    changed = preset != (display['layout_preset'] or 'fullscreen')
    update_display(display_id, layout_preset=preset)
    flash(f'Layout: {LAYOUT_PRESETS[preset]["label"]}', 'success')
    if changed:
        affected = clear_zone_access(display_id)
        if affected:
            flash(f'Zonen-Freigaben für dieses Display wurden entfernt ({affected} Benutzer). '
                  'Bitte im Tab „Benutzer“ neu vergeben.', 'info')
    return redirect(url_for('admin'))


# --- User management ---

@app.route('/admin/users/create', methods=['POST'])
@admin_required
def users_create():
    display_name = request.form.get('display_name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password') or ''

    if not display_name or not username or not password:
        flash('Bezeichnung, Benutzername und Passwort sind erforderlich', 'error')
        return redirect(url_for('admin'))

    if username.lower() == config.admin_username.lower() or get_user_by_username(username):
        flash(f'Benutzername "{username}" ist bereits vergeben', 'error')
        return redirect(url_for('admin'))

    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
    create_user(username, pw_hash, display_name)
    flash(f'Benutzer "{display_name}" erstellt. Bitte unten den Zugriff festlegen.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:user_id>/update', methods=['POST'])
@admin_required
def users_update(user_id):
    user = get_user(user_id)
    if not user:
        flash('Benutzer nicht gefunden', 'error')
        return redirect(url_for('admin'))

    display_name = request.form.get('display_name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password') or ''

    if not display_name or not username:
        flash('Bezeichnung und Benutzername dürfen nicht leer sein', 'error')
        return redirect(url_for('admin'))

    if username.lower() == config.admin_username.lower():
        flash('Dieser Benutzername ist für den Administrator reserviert', 'error')
        return redirect(url_for('admin'))

    existing = get_user_by_username(username)
    if existing and existing['id'] != user_id:
        flash(f'Benutzername "{username}" ist bereits vergeben', 'error')
        return redirect(url_for('admin'))

    pw_hash = (
        bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
        if password else None
    )
    update_user(user_id, username=username, display_name=display_name, password_hash=pw_hash)
    flash(f'Benutzer "{display_name}" aktualisiert', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def users_delete(user_id):
    user = get_user(user_id)
    if not user:
        flash('Benutzer nicht gefunden', 'error')
        return redirect(url_for('admin'))

    cleanups = delete_user(user_id)
    for res in cleanups:
        _delete_media_files(res)

    flash(f'Benutzer "{user["display_name"]}" und zugehörige Inhalte gelöscht', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:user_id>/access', methods=['POST'])
@admin_required
def users_access(user_id):
    user = get_user(user_id)
    if not user:
        flash('Benutzer nicht gefunden', 'error')
        return redirect(url_for('admin'))

    for d in get_all_displays():
        did = d['id']
        zone_count = LAYOUT_PRESETS.get(d['layout_preset'] or 'fullscreen', {'zones': 1})['zones']
        if request.form.get(f'whole_{did}'):
            grants = [WHOLE_DISPLAY]
        elif zone_count > 1:
            grants = [z for z in request.form.getlist(f'zones_{did}', type=int) if 0 <= z < zone_count]
        else:
            grants = []
        set_user_access(user_id, did, grants)

    flash(f'Zugriff für "{user["display_name"]}" gespeichert', 'success')
    return redirect(url_for('admin'))


if __name__ == '__main__':
    from waitress import serve
    print(f'Starting Infoboard on {config.host}:{config.port}')
    print(f'Admin: http://{config.host}:{config.port}/admin')
    for d in get_all_displays():
        print(f'Display "{d["name"]}": http://{config.host}:{config.port}/display/{d["slug"]}')
    serve(app, host=config.host, port=config.port)
