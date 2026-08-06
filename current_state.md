# Current State

**Branch:** main — deploy.sh now checks font packages on Debian/Ubuntu (new step 3/9), about to commit. Prior latest: `fdc2b60` (carlito/caladea docs)
**Status:** Stable. No open bugs, no open PRs. v1.0, v2.0, v2.1 GitHub releases published (v2.1: https://github.com/patrickfiedler/infoboard/releases/tag/v2.1 — kiosk CPU fix, auto-reload, admin UX polish; no migration). Progress bar / auto-reload work confirmed working on Pi 5 kiosk hardware by user.

## Next steps
- Smart TV testing (needs hardware)
- DietPi/Mate kundenstopper machine (`/home/dietpi/kundenstopper/`) still not migrated to infoboard — see [[project-kundenstopper-migration]] memory

## Key architecture notes
- PDF render pipeline: pdfinfo → parallel pdftoppm chunks → parallel Pillow spread stitching
- Same-DPI fast path: `_find_same_dpi_renders()` → `shutil.copy2`
- Everything is a playlist; empty playlist → `get_newest_media()` fallback
- Zone API: `/api/display/<slug>/zone/<int>/current`; zone 0 falls back to `display_api()`
- Display auto-reload: `APP_VERSION` (git short hash, computed once at Flask startup) is served in `common` dict of `display_api()`/`zone_api()`; `display.html` poll() compares against baseline and calls `location.reload()` on mismatch. Only takes effect after `update.sh` restarts the systemd service — a plain `git pull` without restart won't update `APP_VERSION`.
- Progress bar (`display.html` SlideEngine): `progress`/`subtle` modes tick at `PROGRESS_TICK_MS` (4Hz), `countdown` mode ticks at 1Hz — both computed via `startSlide()`'s `tickMs`/`tickSeconds` locals. No CSS transition on `.zone-progress-fill` — instant transform writes only, avoids the continuous-compositor CPU cost a `transition` caused on Pi 5.
- `cycle_interval` column on `displays`/`zones` now doubles as the per-display/zone default duration prefilled in the admin "add content" duration field (previously hardcoded to 10s, only used as single-item-mode fallback).
