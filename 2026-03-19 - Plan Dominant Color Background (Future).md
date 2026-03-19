# Plan: Dominant Color Background (Future Reference)

**Status: Shelved** — superseded by the blurred image clone approach (simpler, better visual result). Keep for future use cases where a portable dominant color value is needed (e.g. Ambilight sync, UI tinting, external integrations).

---

## Goal
Compute the dominant color of each gallery image at upload time and use it as the display background color while that image is shown.

## Algorithm: K-means via Pillow

```python
from PIL import Image

def compute_dominant_color(filepath, n_colors=6):
    """Return hex string of dominant color, darkened and desaturated for use as background."""
    img = Image.open(filepath).convert('RGB')
    img = img.resize((150, 150), Image.LANCZOS)  # downsample for speed
    paletted = img.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
    palette = paletted.getpalette()  # flat list: R,G,B,R,G,B,...
    counts = sorted(paletted.getcolors(), reverse=True)  # (count, palette_index)
    dominant_idx = counts[0][1]
    r, g, b = palette[dominant_idx*3], palette[dominant_idx*3+1], palette[dominant_idx*3+2]

    # Desaturate and darken for use as background
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    s *= 0.5   # reduce saturation by 50%
    v *= 0.25  # reduce brightness to 25%
    r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
    return '#{:02x}{:02x}{:02x}'.format(int(r2*255), int(g2*255), int(b2*255))
```

## Required changes

### New dependency
```
Pillow>=10.0.0
```

### DB migration: `migrations/0006_dominant_color.sql`
```sql
ALTER TABLE gallery_images ADD COLUMN dominant_color TEXT;
ALTER TABLE media_items ADD COLUMN dynamic_bg INTEGER NOT NULL DEFAULT 1;
```

### Models
- `update_gallery_image_color(image_id, hex_color)`
- `get_gallery_image_colors(media_id)` — returns list of (image_id, filename, dominant_color)

### Upload flow (`app.py`)
After saving each gallery image, call `compute_dominant_color(filepath)` and store result.

### Backfill route
`POST /admin/gallery/<media_id>/recompute-colors` — iterates existing images, computes and stores dominant color. Triggered by "Farben berechnen" button in admin.

### Display API
Include `dominant_color` per image in gallery slide response.

### Display JS
On image switch:
- Read `dominant_color` from current slide data
- Apply to `document.body.style.backgroundColor`
- CSS `transition: background-color 0.8s ease` on body
- On non-gallery slides: revert to display's configured `background_color`

### Admin UI
- Checkbox "Hintergrundfarbe anpassen" per gallery item (reads/writes `dynamic_bg`)
- "Farben berechnen" button for existing images

## Why k-means beats median cut
Median cut splits the color space along its longest axis — fast but can over-represent large uniform areas (white wall dominates over colorful subject). K-means minimizes within-cluster variance, producing more perceptually balanced cluster centers. For 1-in-5 complex photos the difference is clearly visible. Since computation is one-time per image, the extra cost is negligible.
