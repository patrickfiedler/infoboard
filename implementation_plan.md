# Implementation Plan: Kundenstopper Expansion

## Goal
Expand the app from a single-display PDF viewer into a multi-display digital signage platform supporting images, video, websites, and YouTube — managed from one admin backend.

---

## Phase 1: Multiple Displays + Multiple Content Types

### Goal
One admin manages N displays. Each display has its own URL, resolution, and content. PDFs are pre-rendered to PNG per display.

### DB Changes
- Rename `pdf_files` → `media_items`, add `content_type` column (`pdf`, `image`, `video`, `youtube`, `url`)
- Add `displays` table: `id`, `name`, `slug` (URL key), `width`, `height`
- Add `display_media` join table: `display_id`, `media_id` (which items are assigned to which display)
- Add `display_settings` table (or extend `settings`): per-display `selected_media_id`, `cycle_interval`, `background_color`, `progress_indicator`
- Add `pdf_renders` table: `media_id`, `display_id`, `render_path` (pre-rendered PNG path)

### Backend (app.py / models.py)
- [ ] DB migration: create new tables, migrate existing data
- [ ] Add `poppler-utils` system dependency (`pdftoppm`)
- [ ] PDF upload: after saving, trigger `pdftoppm` render for each existing display at its resolution → store in `pdf_renders`
- [ ] New display CRUD routes: create/edit/delete displays (admin)
- [ ] When display resolution changes: regenerate all PNG renders for that display
- [ ] API endpoint per display: `GET /api/display/<slug>` → returns current media info + type
- [ ] Serve rendered PNGs: `GET /renders/<display_id>/<filename>`
- [ ] Content assignment: `POST /admin/display/<id>/assign/<media_id>`
- [ ] URL/YouTube items: stored in DB only (no file), `content_type = youtube` or `url`

### Frontend
- [ ] Display route: `GET /display/<slug>` (keep `/display` as backwards-compatible default)
- [ ] display.html: detect content type and render:
  - `pdf` → serve pre-rendered PNG (simple `<img>` tag, no PDF.js)
  - `image` → `<img>` tag
  - `video` → `<video autoplay loop muted>` tag
  - `youtube` → `<iframe>` with YouTube embed URL
  - `url` → `<iframe>` with full-screen sizing
- [ ] Remove PDF.js dependency from display page (keep in codebase for now, just unused)
- [ ] Admin: display management section (create/edit/delete displays, set resolution)
- [ ] Admin: assign content to display
- [ ] Admin: upload accepts images (`jpg`, `png`, `gif`, `webp`) and video (`mp4`, `webm`) in addition to PDF
- [ ] Admin: add URL/YouTube input field (no file upload needed)

### Migration Notes
- Existing single display → becomes "Display 1" with slug `default`
- Existing `/display` route → redirects to `/display/default`
- Existing PDFs → migrated to `media_items`, rendered for default display on startup

### Open Questions
- [ ] Multi-page PDFs: pre-render all pages as individual PNGs, cycle through them (replaces PDF.js cycling logic)
- [ ] File size limits: video files can be large — raise limit or make configurable

---

## Phase 1b: Website Proxy

### Goal
Allow websites to be embedded in the display iframe by fetching them server-side and stripping `X-Frame-Options` / `Content-Security-Policy: frame-ancestors` headers.

### How it works
`<iframe src="/proxy?url=https://example.com">` — Flask fetches the URL, strips the blocking headers, injects `<base href>` so relative links resolve, returns the HTML. Sub-resources (CSS, JS, images) load directly from the origin (no proxy needed for those).

### Backend
- [x] Add `requests` to `requirements.txt`
- [x] `/proxy` route: fetch URL, strip headers, inject `<base href>`, return response
- [x] Security: only proxy URLs that exist as `url`-type media items in the DB (not an open proxy)
- [x] Preserve Content-Type from origin response

### Frontend
- [x] `display.html`: `url` content type already uses `<iframe>` — change `src` from direct URL to `/proxy?url=...`

### Limitations (known, accepted)
- Sites with iframe-busting JavaScript (`if top !== self`) will still break
- Pages behind authentication / SSO will not work
- Fallback: screenshot approach (playwright) if proxy is insufficient for a specific site

### Migration
- [x] `migrations/0002_website_proxy.py` — no DB change needed; proxy is a pure route addition

---

## Phase 1c: Cookie Banner Suppression

### Goal
Prevent cookie consent overlays from blocking the display view on proxied websites.

### Approaches (in order of complexity)

#### A — CSS hiding (implemented)
Inject a `<style>` block into proxied HTML that hides known cookie banner elements by
CSS selector. The banner disappears visually; the site doesn't know consent was given,
but for an unattended display screen that doesn't matter.
- Pro: simple, no JS needed, works for all major CMPs
- Con: requires adding selectors for unusual/custom banners per site

Covered CMPs: OneTrust, CookieBot, Quantcast, Didomi, CookieConsent.js, CookieYes,
Borlabs, TrustArc, Iubenda, Osano, Complianz, Cookie Law Info, Termly, plus generic
`#cookie-banner`, `#cookie-notice`, `#cookie-consent` patterns.

To add a site-specific selector: extend `PROXY_COOKIE_HIDE_CSS` in `app.py`.

#### B — Manual cookie paste (not implemented)
Admin copies cookies from browser DevTools → pastes into input field in admin panel →
stored in DB per URL → proxy forwards them as `Cookie:` header upstream.
- Pro: actually accepts cookies, works for sites with content behind consent wall
- Con: manual, cookies expire and need refreshing

#### C — Playwright headless browser (not implemented)
Server runs a real browser session; admin interacts with it remotely (or it auto-clicks
consent); resulting cookies stored server-side and reused for proxy fetches.
- Pro: most robust, handles any site including JS-only banners
- Con: heavy dependency, complex setup

### Why CSS hiding is right for digital signage
Approaches B and C are only needed if proxied content is genuinely gated behind consent
(e.g. paywalls). For display-only use, visually hiding the overlay is sufficient.

### Backend
- [x] `PROXY_COOKIE_HIDE_CSS` constant in `app.py` with selectors for major CMPs
- [x] Proxy route injects CSS block into HTML responses

### Migration
- No DB change needed

---

## Phase 2: Smart TV Optimization

### Goal
Ensure reliable, performant display on Smart TV built-in browsers (Samsung Tizen, LG WebOS, Android TV).

### Research Needed
- [ ] Test current Phase 1 display page on target TV browser
- [ ] Identify JS/CSS compatibility issues
- [ ] Measure image/video load times on TV hardware

### Changes (based on findings)
- [ ] Per-display "TV mode" flag in `displays` table
- [ ] TV mode: simplified display.html with minimal JS (no ES modules if needed, plain `<script>`)
- [ ] TV mode: aggressive caching headers for images/video
- [ ] TV mode: preload next image while current is displayed
- [ ] Optional: `/display/<slug>?tv=1` query param to force TV mode without DB change
- [ ] Consider: auto-detect TV browser via User-Agent and switch mode automatically

### Notes
- Phase 1 already removes PDF.js from display (biggest compatibility risk)
- Images and video are native browser features — should work on all TV browsers
- ES modules (`type="module"`) may not work on older Smart TVs — evaluate in Phase 1

---

## Phase 3: Multi-Zone Layouts

### Goal
A display can be divided into independently-controlled zones, each showing different content.

### Approach: Predefined Layouts (avoid full layout editor)
Start with a small set of named layout templates rather than a drag-and-drop editor.

Proposed layouts:
- `fullscreen` — 1 zone (current behavior)
- `split-horizontal` — 2 zones, 50/50 left/right
- `split-vertical` — 2 zones, 70/30 top/bottom
- `main-sidebar` — large main zone + narrow sidebar
- `main-ticker` — large main zone + bottom ticker strip

### DB Changes
- Add `layout` column to `displays` table (default: `fullscreen`)
- Add `zones` table: `id`, `display_id`, `zone_key` (e.g. `main`, `sidebar`, `ticker`), `selected_media_id`, `cycle_interval`
- `display_settings` moves to zone level for per-zone cycling

### Backend
- [ ] Zone CRUD in admin
- [ ] API: `GET /api/display/<slug>` returns all zones with their current media
- [ ] Content assignment per zone

### Frontend
- [ ] display.html: render layout container with CSS Grid
- [ ] Each zone runs its own independent polling + cycling loop
- [ ] Each zone renders its content type (reuses Phase 1 type-rendering logic)
- [ ] Admin: layout picker per display, zone content assignment UI

### Deferral Strategy
- Phase 3 can be started with just `fullscreen` + `split-horizontal` to prove the architecture
- More layouts added incrementally without schema changes

---

## Status
**Phase 1 + 1b complete. Phase 2 (Smart TV) when hardware available.**
Phase 2 (Smart TV testing) when hardware is available.

## Decisions Made
- PDF pre-rendering: one PNG per page per display, stored in `renders/<display_id>/` directory
- PNG format (not JPG) for all PDF renders — lossless, sharp text
- Render resolution: use display `width` × `height` from DB, calculate DPI from PDF page dimensions
- Smart TV: remove PDF.js from display page in Phase 1 (biggest compatibility win, zero extra effort)
- Multiple zones: predefined layout templates only, no drag-and-drop editor
- Backwards compatibility: `/display` continues to work (redirects to default display)
