# Image Attribution

Demo imagery used in the Vehicle Detail page. Everything here is licensed for reuse; no
manufacturer marketing photography and no dealer inventory images are used.

---

## `toyota_rav4_2022.jpg`

| | |
| --- | --- |
| **Source website** | Wikimedia Commons |
| **File page** | https://commons.wikimedia.org/wiki/File:2021_Toyota_RAV4_PHV.jpg |
| **Original file URL** | https://upload.wikimedia.org/wikipedia/commons/5/5b/2021_Toyota_RAV4_PHV.jpg |
| **Title** | 2021 Toyota RAV4 PHV |
| **Creator** | TTTNIS (own work) |
| **Date taken** | 2024-10-19 |
| **License** | **CC0 1.0 Universal — Public Domain Dedication** |
| **License URL** | https://creativecommons.org/publicdomain/zero/1.0/deed.en |
| **Attribution required?** | No. CC0 waives all rights; credit is given here as good practice, not obligation. |

### Why this one

CC0 was chosen over the CC BY-SA and CC BY alternatives on Commons deliberately. It
imposes no attribution obligation and no share-alike condition, which is the least
encumbered footing for an image that will appear in a customer-facing demo.

### Modifications

Downscaled from 4482 × 2294 to **1600 × 819** and re-encoded as progressive JPEG at
quality 86 (3.16 MB → 232 KB) to keep the repository light. Camera EXIF metadata was
dropped in the process. No cropping, retouching, or colour adjustment.

### Accuracy note

The subject is a **2021 RAV4 PHV**, not the 2022 RAV4 XLE that fixture `V-10001`
describes. Both are the XA50 generation, so the body is right, but the trim and model year
are not an exact match. This is demo imagery standing in for a merchandising photo, not a
record of the specific vehicle — the same way `image_url` would carry a real photo of the
actual car in production.

---

## Fallback artwork

Vehicles without an `image_url` render a generated body-style silhouette from
`ui_components.py`. That artwork is original to this repository and carries no third-party
rights.
