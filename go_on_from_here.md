# Go On From Here

## Last session summary
Implemented drag-and-drop playlist editor in admin panel. All display cards now show a permanent 2-column layout (Einstellungen | Playlist) without toggle buttons. Playlist uses SortableJS for drag reorder; all mutations (add, remove, duration change) are AJAX — page never reloads.

## Current state
- **Branch:** main, last commit: 4f38bef (need to commit this session's work)
- **Phase 1 complete** — multi-display, multi-content-type
- **Phase 1b–1e complete** — proxy, cookie hiding, scale-to-fit, playlist
- **Drag-and-drop playlist editor** — just implemented, not yet committed

## What to do next
- Commit current changes
- Phase 2: Smart TV testing (needs hardware)
- Phase 3: Multi-zone layouts
- No pending bugs

## Key files
- `app.py` — all routes (proxy, playlist, YouTube options, display API)
- `models.py` — DB schema + playlist CRUD (incl. new `reorder_playlist_items`)
- `migrate.py` — migration runner
- `migrations/` — 0001–0004 applied
- `templates/display.html` — unified slide model JS (buildSlides → startSlide)
- `templates/admin.html` — 2-column display cards, SortableJS, AJAX playlist
- `static/js/sortable.min.js` — SortableJS library (new)
- `cookie_hide.conf` — CSS selectors for cookie banner hiding (edit without restart)
- `implementation_plan.md` — phases 1–3 with full spec
- `deploy.sh` / `update.sh` — deployment scripts

## Architecture reminders
- Playlist takes priority over selected_media_id in display API
- Proxy whitelist: only registered url-type media items can be proxied
- cookie_hide.conf read per-request (no restart needed for changes)
- PDF pre-rendering: pdftoppm → renders/<display_id>/ directory
- AJAX detection: `X-Requested-With: XMLHttpRequest` header
