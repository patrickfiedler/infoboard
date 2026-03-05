# Task Plan: Drag-and-Drop Playlist Editor in Admin

## Goal
Always-visible 2-column display cards (settings | playlist) with SortableJS drag-and-drop and AJAX for all playlist mutations.

## Phases
- [x] 1. Download SortableJS → `static/js/sortable.min.js`
- [x] 2. `models.py`: add `reorder_playlist_items`, make `add_playlist_item` return `lastrowid`
- [x] 3. `app.py`: AJAX returns for playlist_add/remove/update_dur, new `playlist_reorder` route
- [x] 4. `admin.html`: 2-column layout, drag handles, AJAX JS with SortableJS
- [ ] 5. Commit & push

## Status
**COMPLETED** – All code changes done. Ready to commit.
