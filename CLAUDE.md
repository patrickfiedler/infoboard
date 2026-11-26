# CLAUDE.md

This file provides guidance to AI assistants and developers when working with code in this repository.

## Project Overview

Infoboard is a Flask-based digital signage web application designed for Raspberry Pi kiosk displays. It supports multiple displays, multi-zone layouts (up to 4 zones), per-zone playlists, multiple media types (PDF, image, image gallery, local video, YouTube embed, proxied website), multi-user editing with shared playlists, and per-entry weekdays.

## Technology Stack

- **Backend**: Flask 3 (Python web framework)
- **WSGI Server**: Waitress 3.0 (production server)
- **Authentication**: Flask-Login 0.6.3 with bcrypt 4.1.2
- **Database**: SQLite (`infoboard.db`, managed via `models.py` and `migrations/`)
- **PDF Rendering**: `pdftoppm` (`poppler-utils`) + Pillow for spread stitching — pre-renders PDFs server-side into `renders/<display_id>/`
- **Frontend**: Vanilla JS + SortableJS (`static/js/sortable.min.js`)
- **Storage**: Local filesystem (`uploads/`, `renders/`)

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

### Running and Migrating

```bash
# Apply pending database migrations
python3 migrate.py

# Start production server with Waitress
python3 app.py

# URLs:
# Display: http://localhost:8080/display/<slug>
# Admin:   http://localhost:8080/admin
```

### Database Reset

```bash
rm infoboard.db
python3 app.py  # Reinitializes database via models.init_db()
```

## Architecture

### Application Structure

- **`app.py`**: Main Flask application, routes, background PDF rendering, website proxy, authentication, and API endpoints.
- **`models.py`**: SQLite database schema initialization (`init_db`) and CRUD operations with `get_db()` context manager.
- **`migrate.py` & `migrations/`**: Numbered migration scripts applied during updates via `./update.sh`. Untracked installations record them as baseline without running them, so schema and data migrations that must always run belong in `init_db()`.
- **`config.py`**: Loads configuration from `config.json`.
- **`templates/admin.html`**: Role-aware management UI (displays, playlists, media library, user management). `templates/_playlist_row.html` is the only markup for a playlist row (page and AJAX add).
- **`templates/display.html`**: Fullscreen kiosk display client polling `/api/display/<slug>/zone/<zi>/current` every 10 seconds.
- **`templates/login.html`**: Login form for both Administrator and standard users.

### Key Components

1. **Multi-Display & Multi-Zone Display View** (`/display/<slug>`):
   - Supports 7 `LAYOUT_PRESETS` (`fullscreen`, `split-h`, `split-v`, `sidebar-r`, `sidebar-b`, `thirds-h`, `quad`).
   - Each zone runs a `SlideEngine` polling `/api/display/<slug>/zone/<zone_index>/current` every 10 seconds.
   - Polling picks up weekday changes (00:00), content updates, layout changes, and app deploys (`APP_VERSION`).
   - When `layout_preset == 'fullscreen'`, `zone_api(..., 0)` delegates directly to `display_api(slug)`.

2. **Users & Access**:
   - **Administrator** (`config.json` credentials, `db_id = 0`): everything, including displays, layouts, users and global settings.
   - **Users** (`users` table): see only displays they have access to. Access (`user_zone_permissions`) is the whole display (`zone_index = -1`) or single zones. Single-zone access is cleared when a layout changes.
   - Library: users see and manage only their own files; the admin manages all files.

3. **Shared Playlists**:
   - One playlist per display (fullscreen) or zone, edited by everyone with access.
   - Only a file's owner can add it (the admin too), so deleting your own file never changes other people's entries.
   - Users change/remove only their own entries (owner = owner of the media item) but may reorder the whole list.
   - `weekdays` (string of digits, `0` = Monday) limits an entry to certain days. With nothing to show today, the area falls back to the selected or newest **admin** file; user uploads never appear on a screen by themselves.

4. **Admin UI** (`templates/admin.html`):
   - Collapsible display settings drawer and creation forms; layout preview thumbnails.
   - In multi-zone layouts the fullscreen playlist is hidden (banner points to the zone playlists).
   - `Benutzer` tab (admin only): accounts and access checkboxes.
   - Confirm dialogs use `<form data-confirm="...">`; never put names into inline JavaScript.

5. **PDF Rendering**:
   - PDFs are pre-rendered in a background thread (`_render_pdf_background`) using `pdftoppm` and Pillow (`_render_pdf_spreads` for `paired`/`book` spreads).
   - Output images are stored in `renders/<display_id>/` and tracked via `/api/render-jobs` (filtered by owner for non-admin users).

### Database Schema (`models.py`)

- `displays`: `id`, `name`, `slug`, `width`, `height`, `selected_media_id`, `cycle_interval`, `background_color`, `progress_indicator`, `video_fit`, `ambient_bg`, `layout_preset`
- `zones`: `id`, `display_id`, `zone_index`, `selected_media_id`, `cycle_interval`
- `media_items`: `id`, `content_type`, `filename`, `original_name`, `url`, `upload_date`, `file_size`, `scale_to_fit`, `user_id` (`0` = Admin)
- `gallery_images`: `id`, `media_id`, `filename`, `original_name`, `file_size`, `position`
- `pdf_renders` & `pdf_spread_renders`: pre-rendered page PNG references per `media_id` and `display_id`
- `playlist_items`: `id`, `display_id`, `media_id`, `duration`, `position`, `spread_mode`, `weekdays`
- `zone_playlist_items`: `id`, `zone_id`, `media_id`, `duration`, `position`, `spread_mode`, `weekdays`
- `users`: `id`, `username`, `password_hash`, `display_name`, `created_at`
- `user_zone_permissions`: `id`, `user_id`, `display_id`, `zone_index` (`-1` = whole display)
- `settings`: global key/value settings (`auto_cleanup_enabled`, `auto_cleanup_days`)

## Important Patterns

### Database Access

Always use the context manager from `models.py`:

```python
from models import get_db

with get_db() as conn:
    result = conn.execute('SELECT * FROM displays').fetchall()
    # conn.commit() called automatically on success
    # conn.rollback() called on exception
```

### Permission Checks

- Admin-only routes must use `@admin_required`.
- Media mutations must check `_can_access_media(media)`.
- Playlist routes must call `_require_playlist_access(kind, owner_id)`; `kind` is `display` or `zone`.
- `/proxy` is sandboxed: never add `allow-same-origin`, never forward upstream headers.

## Routes Overview

**Public / Display Routes**:
- `GET /` & `GET /display`: Redirect to first display (`/display/<slug>`)
- `GET /display/<slug>`: Fullscreen kiosk view
- `GET /api/display/<slug>` & `GET /api/display/<slug>/zone/<int:zone_index>/current`: JSON APIs for display/zone content (today's playlist entries or fallback)
- `GET /api/current-pdf`: Legacy display API proxy
- `GET /uploads/<filename>` & `GET /renders/<int:display_id>/<filename>`: Serve media and rendered PDF pages
- `GET /proxy?url=...`: Website proxy for whitelisted `url`-type media items
- `GET|POST /login`: Authentication for Admin and DB users

**Authenticated Routes** (Users & Admin, checked for ownership & access):
- `GET /admin`: Management UI (role-filtered)
- `GET /logout`: Logout
- `GET /api/render-jobs`: Background PDF render status
- `POST /admin/upload`, `POST /admin/url`, `POST /admin/gallery/create`
- `POST /admin/gallery/<id>/upload`, `.../image/<id>/remove`, `.../image/reorder`
- `POST /admin/media/<id>/url-options`, `.../youtube-options`, `POST /admin/rename/<id>`, `POST /admin/delete/<id>`
- `POST /admin/<display|zone>/<id>/playlist/add`, `.../reorder`, `.../item/<item_id>/<remove|duration|spread|weekdays>`

**Admin-Only Routes** (`@admin_required`):
- `POST /admin/display/create`, `.../settings`, `.../delete`, `.../layout`, `.../regenerate`
- `POST /admin/users/create`, `.../update`, `.../delete`, `.../access`
- `POST /admin/settings`, `POST /admin/cleanup`

## Workflow
workflow_initialized = true
