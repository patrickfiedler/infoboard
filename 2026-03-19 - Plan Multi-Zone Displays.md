# Plan: Multi-Zone Display Layouts

**Goal:** Allow each display to be split into 2–4 independent viewing zones, each showing its own content/playlist simultaneously.

**Approach:** Option B — multiple JS engine instances in one page (no iframe nesting). Zone layout is defined by a preset on the display; each zone runs its own slide-cycling logic.

---

## Phases

- [ ] Phase 1: DB + models
- [ ] Phase 2: API endpoints
- [ ] Phase 3: display.html JS refactor + zone rendering
- [ ] Phase 4: Admin UI for zone management
- [ ] Phase 5: Migration + testing

---

## Phase 1 — DB + Models

### Migration: `migrations/0006_zones.sql`

```sql
-- Layout preset on display (fullscreen = existing single-zone behaviour)
ALTER TABLE displays ADD COLUMN layout_preset TEXT NOT NULL DEFAULT 'fullscreen';

-- Zones table
CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_id INTEGER NOT NULL,
    zone_index INTEGER NOT NULL,          -- 0-based, order matches layout preset
    selected_media_id INTEGER NOT NULL DEFAULT 0,
    cycle_interval INTEGER NOT NULL DEFAULT 10,
    UNIQUE(display_id, zone_index),
    FOREIGN KEY (display_id) REFERENCES displays(id)
);

-- Zone playlists (mirrors playlist_items but per zone, not per display)
CREATE TABLE IF NOT EXISTS zone_playlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id INTEGER NOT NULL,
    media_id INTEGER NOT NULL,
    duration INTEGER NOT NULL DEFAULT 10,
    position INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (zone_id) REFERENCES zones(id)
);
```

### Layout presets

Hardcode in Python (and mirror in JS). Each preset defines zone count and CSS geometry:

| preset | zones | description |
|---|---|---|
| `fullscreen` | 1 | 100% × 100% (current behaviour — default) |
| `split-h` | 2 | Left 50% / Right 50% |
| `split-v` | 2 | Top 50% / Bottom 50% |
| `sidebar-r` | 2 | Main 70% left / Sidebar 30% right |
| `sidebar-b` | 2 | Main 75% top / Ticker 25% bottom |
| `thirds-h` | 3 | Three equal horizontal columns |
| `quad` | 4 | 2×2 grid |

```python
LAYOUT_PRESETS = {
    'fullscreen': {'zones': 1, 'label': 'Vollbild'},
    'split-h':    {'zones': 2, 'label': '2 Hälften (nebeneinander)'},
    'split-v':    {'zones': 2, 'label': '2 Hälften (übereinander)'},
    'sidebar-r':  {'zones': 2, 'label': 'Hauptbereich + rechte Spalte (70/30)'},
    'sidebar-b':  {'zones': 2, 'label': 'Hauptbereich + Ticker unten (75/25)'},
    'thirds-h':   {'zones': 3, 'label': '3 Spalten'},
    'quad':       {'zones': 4, 'label': '4 Felder (2×2)'},
}
```

### New model functions (`models.py`)

```python
get_zones_for_display(display_id)       # → list of zone rows, ordered by zone_index
get_zone(zone_id)
create_zone(display_id, zone_index)     # creates with defaults
delete_zone(zone_id)
update_zone_settings(zone_id, selected_media_id, cycle_interval)

get_zone_playlist_items(zone_id)
add_zone_playlist_item(zone_id, media_id, duration)
remove_zone_playlist_item(item_id)
update_zone_playlist_item_duration(item_id, duration)
reorder_zone_playlist_items(zone_id, ordered_ids)
```

---

## Phase 2 — API Endpoints

### Existing API (keep, adapt for zone 0 in fullscreen):
`GET /api/display/<slug>/current` — unchanged, continues to serve zone-0 (or single-zone) content.

### New API:
`GET /api/display/<slug>/zone/<int:zone_index>/current`

Returns same JSON shape as existing `/current` endpoint but resolves content from the zone's `selected_media_id` and zone playlist:

```json
{
  "content_type": "pdf",
  "original_name": "Menu.pdf",
  "pages": [...],
  "cycle_interval": 15
}
```

**Logic:** same as existing `current_media` logic but reading from `zones` and `zone_playlist_items` instead of `displays` and `playlist_items`.

### New admin routes:
```
POST /admin/display/<id>/layout          # update layout_preset; creates/deletes zones as needed
POST /admin/zone/<zone_id>/settings      # update zone selected_media_id + cycle_interval
POST /admin/zone/<zone_id>/playlist/add
POST /admin/zone/<zone_id>/playlist/remove/<item_id>
POST /admin/zone/<zone_id>/playlist/duration/<item_id>
POST /admin/zone/<zone_id>/playlist/reorder
```

The layout route must reconcile zones: if switching from `split-h` (2 zones) to `fullscreen` (1 zone), delete zone 1; if switching from `fullscreen` to `split-h`, create zone 1 with defaults.

---

## Phase 3 — display.html Refactor

### Current problem
The display.html JS uses global variables and a single content container. It cannot be instantiated multiple times per page.

### Solution: SlideEngine class

Refactor all display JS into a class:

```javascript
class SlideEngine {
    constructor(containerEl, apiUrl, displaySlug) {
        this.container = containerEl;
        this.apiUrl = apiUrl;
        // ... all existing state as instance vars
    }
    start() { this.poll(); }
    poll() { fetch(this.apiUrl).then(...) }
    // ... all existing methods as class methods
}
```

### Zone rendering

The display template receives `layout_preset` and `zones` from the server:

```html
<div id="zone-0" class="zone zone-{{ layout_preset }}-0">
  <!-- content container for zone 0 -->
</div>
<div id="zone-1" class="zone zone-{{ layout_preset }}-1">
  <!-- content container for zone 1, only rendered if zones > 1 -->
</div>
```

JS init at bottom of page:
```javascript
{% for z in zones %}
new SlideEngine(
    document.getElementById('zone-{{ z.zone_index }}'),
    '/api/display/{{ slug }}/zone/{{ z.zone_index }}/current',
    '{{ slug }}'
).start();
{% endfor %}
```

### Zone CSS (one block per preset)

```css
/* fullscreen (default) */
.zone { position: absolute; overflow: hidden; }
body.layout-fullscreen .zone { top:0; left:0; width:100%; height:100%; }

/* split-h */
body.layout-split-h .zone-split-h-0 { top:0; left:0; width:50%; height:100%; }
body.layout-split-h .zone-split-h-1 { top:0; left:50%; width:50%; height:100%; }

/* sidebar-r */
body.layout-sidebar-r .zone-sidebar-r-0 { top:0; left:0; width:70%; height:100%; }
body.layout-sidebar-r .zone-sidebar-r-1 { top:0; left:70%; width:30%; height:100%; }

/* ... etc for all presets */
```

### Backward compatibility

`fullscreen` (default) has one zone (zone 0). The new API `/api/display/<slug>/zone/0/current` reads from `zones` if they exist, otherwise falls back to existing display-level `selected_media_id` / playlist logic. This means **existing displays work without any migration data change**.

---

## Phase 4 — Admin UI

In each display card, after the existing settings form:

1. **Layout selector:** dropdown to choose preset; shows zone count description. Submit triggers layout change route.

2. **Per-zone panels:** rendered only if layout_preset ≠ `fullscreen`. Each zone gets a collapsible sub-card with:
   - Zone label: "Zone 0 (Hauptbereich)" / "Zone 1 (Nebenbereich)" etc.
   - Same single-select dropdown (Einzelinhalt) as main display card
   - Same playlist add/remove/reorder table as main display card

   These are styled as a nested section inside the display card, reusing existing CSS classes.

3. **Cycle interval** per zone (in zone settings form), separate from main display cycle_interval.

**Note:** The main display cycle_interval and selected_media_id remain relevant only for `fullscreen` mode. For multi-zone, zones own their content. Consider adding a note in the UI.

---

## Phase 5 — Migration + Testing

- Add `migrate.py` step for migration 0006
- Test: switching layout presets, adding/removing playlist items per zone, content cycling per zone independently
- Test: fullscreen display (zone 0) continues to work as before

---

## Files changed

| File | Change |
|---|---|
| `migrations/0006_zones.sql` | New file — zones + zone_playlist_items tables, layout_preset column |
| `migrate.py` | Register migration 0006 |
| `models.py` | ~8 new zone CRUD functions |
| `app.py` | `LAYOUT_PRESETS` dict; new zone API + admin routes; extend admin route to pass zones + presets |
| `templates/display.html` | Refactor JS to `SlideEngine` class; zone rendering loop; zone CSS |
| `templates/admin.html` | Layout dropdown in display card settings; per-zone sub-panels |

---

## Key design decisions

- **Presets over free-form:** Keeps CSS and admin UI manageable. Adding a new preset later is just one CSS block + one dict entry.
- **Zones own their content:** zone's `selected_media_id` + `zone_playlist_items` are independent of the display's. The display-level fields remain for fullscreen backward compat.
- **SlideEngine class:** Cleanest way to run N independent timers on one page. Each zone polls its own API URL independently.
- **No iframes:** Avoids YouTube-in-iframe nesting issues and keeps a single DOM context.

---

## Estimated effort

2–3 sessions. Phase 3 (JS refactor) is the most delicate step.
