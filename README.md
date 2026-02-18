# KaroSpaceSE

Lightweight landing portal for KaroSpace viewers using a hybrid Cloudflare setup:
- Cloudflare Pages serves the landing site from `/site`
- Cloudflare R2 serves viewer files from a public custom domain

This repository intentionally excludes large viewer exports and processed viewer artifacts.

## Suggested GitHub Metadata

- Suggested repository names:
  - `karospace-atlas`
  - `spatial-atlas-portal`
  - `karospace-viewer-hub`
- Suggested repository description:
  - `Static Cloudflare Pages portal for KaroSpace viewers hosted on Cloudflare R2.`

## Repository Structure

```text
/
├── site/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── datasets.json
├── scripts/
│   ├── externalize_karospace_html.py
│   ├── upload_to_r2.py
│   └── generate_thumbnails.py
├── site/thumbs/ # optional local thumbnails for dataset cards
├── exports/      # local-only, gitignored
├── viewers/      # local-only, gitignored
├── .gitignore
├── README.md
└── LICENSE
```

## Architecture

```text
GitHub repo
   |
   v
Cloudflare Pages (serves /site)
   |
   v
https://yourdomain.com  (landing portal)

Cloudflare R2 bucket + custom domain
   |
   v
https://viewers.yourdomain.com/viewers/<viewer-path>
```

## Deployment

### Landing Page (Cloudflare Pages)

1. Push this repo to GitHub.
2. In Cloudflare Pages, connect the repo.
3. Build command: none.
4. Output directory: `site`.
5. Attach your custom domain (for example `yourdomain.com`).

### Viewers (Cloudflare R2)

1. Export KaroSpace as self-contained HTML into `exports/` (local only).
2. For large files, run externalization:

```bash
python scripts/externalize_karospace_html.py \
  --input ./exports/RRMap.html \
  --outdir ./viewers \
  --slug RRMap \
  --mode auto \
  --threshold-mb 80 \
  --chunk-mb 50
```

3. Upload processed outputs to R2:

```bash
python scripts/upload_to_r2.py --viewers-dir ./viewers
```

4. Add/update entries in `site/datasets.json` so the landing page can link to new viewers.

### Optional: Auto-generate dataset thumbnails

Install Playwright once:

```bash
pip install playwright
python -m playwright install chromium
```

Generate thumbnails and update `site/datasets.json` automatically:

```bash
python scripts/generate_thumbnails.py \
  --datasets site/datasets.json \
  --output-dir site/thumbs \
  --viewer-host https://viewers.karospace.se \
  --overwrite
```

This writes image files like `site/thumbs/CODEX.jpg` and sets:

```json
"thumbnail": "thumbs/CODEX.jpg"
```

If your local DNS still returns `NXDOMAIN` for `viewers.karospace.se`, run with
temporary host override:

```bash
python scripts/generate_thumbnails.py \
  --viewer-host https://viewers.karospace.se \
  --host-ip 188.114.96.1 \
  --overwrite
```

## Add Dataset Checklist

- [ ] Export new dataset from KaroSpace to `exports/<slug>.html`
- [ ] Run `externalize_karospace_html.py` in `auto` mode
- [ ] Verify output is either `viewers/<slug>.html` or `viewers/<slug>/index.html`
- [ ] Upload `viewers/` to Cloudflare R2
- [ ] Add dataset entry in `site/datasets.json`
- [ ] Confirm link opens from landing page

## Notes

- No frontend frameworks are used (plain HTML/CSS/JS).
- `exports/` and `viewers/` are intentionally excluded from git.
