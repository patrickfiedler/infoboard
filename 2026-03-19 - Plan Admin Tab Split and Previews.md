# Plan: Admin Tab Split + Display Previews

**Goal:** Split the admin page into "Displays" and "Inhalte" (content) tabs, and add thumbnail previews to display cards showing what's currently on screen.

**Scope:** Frontend-heavy, mostly admin.html + small admin route additions. No new DB tables needed.

---

## Phases

- [ ] Phase 1: Tab navigation
- [ ] Phase 2: Thumbnail helper in app.py
- [ ] Phase 3: Preview widget in display card

---

## Phase 1 — Tab navigation

**File: `templates/admin.html`**

Add a simple tab bar above the two existing `<div class="section">` blocks. Pure HTML/CSS/JS — no backend.

```html
<div class="tab-bar">
  <button class="tab active" data-tab="displays">Displays</button>
  <button class="tab" data-tab="content">Inhalte</button>
</div>
<div id="tab-displays"> ...existing displays section... </div>
<div id="tab-content" style="display:none"> ...existing media library section... </div>
```

JS (20 lines): click handler toggles `display:none` and `active` class.

CSS: tab bar is a flex row with border-bottom styling, active tab has a blue underline.

**Preserve:** flash messages stay above the tabs (always visible). "Neues Display" form can be integrated into the Displays tab.

---

## Phase 2 — Thumbnail helper

**File: `app.py`**

Add a helper function `get_thumbnail_url(media, display_id)` that returns a URL string or `None`:

| `content_type` | Returns |
|---|---|
| `pdf` | URL of first render image: calls `get_pdf_renders(media_id, display_id)`, takes `renders[0]['render_filename']`, returns `url_for('serve_render', display_id=..., filename=...)` |
| `image` | `url_for('serve_upload', filename=media['filename'])` (already exists) |
| `gallery` | First gallery image filename → `url_for('serve_upload', filename=first_img['filename'])` |
| `youtube` | `https://img.youtube.com/vi/<VIDEO_ID>/hqdefault.jpg` — parse video ID from `media['url']` with existing `parse_youtube_params` |
| `video`, `url` | `None` (show placeholder icon) |

In the admin route, compute:

```python
display_thumbnails = {}
for d in displays:
    cur = display_current.get(d['id'])
    if cur:
        display_thumbnails[d['id']] = get_thumbnail_url(cur, d['id'])
```

Pass `display_thumbnails` to the template.

For gallery: need first gallery image. The admin route already loads `gallery_images_map` for `gallery_image_counts` — extend it to also keep `gallery_first_images = {media_id: first_image_row}`.

---

## Phase 3 — Preview widget in display card

**File: `templates/admin.html`**

Add a preview area to the display card header or status bar. Suggested placement: right side of the card header (next to action buttons), 16:9 aspect ratio thumbnail, ~120px wide.

```html
<!-- in display-card-header -->
{% set thumb = display_thumbnails.get(d.id) %}
{% if thumb %}
  <img src="{{ thumb }}" class="display-preview-thumb" alt="Vorschau">
{% else %}
  <div class="display-preview-placeholder">
    {% if display_current.get(d.id) and display_current[d.id]['content_type'] == 'url' %}🌐
    {% elif display_current.get(d.id) and display_current[d.id]['content_type'] == 'video' %}▶
    {% else %}—{% endif %}
  </div>
{% endif %}
```

CSS:
```css
.display-preview-thumb {
    width: 120px;
    height: 68px;   /* 16:9 */
    object-fit: cover;
    border-radius: 4px;
    border: 1px solid #ddd;
    flex-shrink: 0;
}
.display-preview-placeholder {
    width: 120px; height: 68px;
    border: 1px solid #ddd; border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    color: #bbb; font-size: 22px; flex-shrink: 0;
}
```

---

## Edge cases

- **Playlist active:** `display_current` for a playlist display shows the selected_media (or newest). That's still useful as a preview of the most recently queued item. Could alternatively show the first item in the playlist — whichever is clearer.
- **No media at all:** `display_current` is `None` → skip thumbnail, show placeholder.
- **PDF render missing:** `get_pdf_renders` returns empty list → return `None`, show placeholder.

---

## Files changed

| File | Change |
|---|---|
| `templates/admin.html` | Tab bar HTML/CSS/JS; preview widget HTML/CSS |
| `app.py` | `get_thumbnail_url()` helper; extend admin route to pass `display_thumbnails`, `gallery_first_images` |

**No migration needed. No new routes (uses existing serve_render and serve_upload).**

---

## Estimated effort

1 session (~2–3 hours). Low risk — all changes are additive to the admin page.
