# KaroSpaceSE

Lightweight landing portal for KaroSpace viewers using a hybrid Cloudflare setup:
- Cloudflare Pages serves the landing site from `/site`
- Cloudflare R2 serves viewer files from a public custom domain
- `site/config.json` stores the shared viewer host used by the site and helper scripts

This repository keeps the landing site tracked in git and treats `exports/` and `viewers/`
as local staging/deployment artifacts. Large viewer exports and processed artifacts remain
gitignored by default.

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
│   ├── config.json
│   └── datasets.json
├── scripts/
│   ├── externalize_karospace_html.py
│   ├── validate_portal.py
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
6. Set `site/config.json` with the public viewer host served by R2.

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

4. Validate local metadata and viewer artifacts:

```bash
python scripts/validate_portal.py
```

5. Add/update entries in `site/datasets.json` so the landing page can link to new viewers.

For sidecar gene viewers exported from KaroSpace with `gene_storage="sidecar"`, keep the
generated files together under the same basename:

```text
viewers/<slug>.html
viewers/<slug>.genes.json
viewers/<slug>.genes/*.json
```

The HTML fetches the sidecar manifest and shard files by relative path, so these files must
be deployed together on the same viewer host without renaming.

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
  --host-ip 188.114.96.1 \
  --overwrite
```

## Add Dataset Checklist

- [ ] Export new dataset from KaroSpace to `exports/<slug>.html`
- [ ] Run `externalize_karospace_html.py` in `auto` mode
- [ ] Verify output is either `viewers/<slug>.html` or `viewers/<slug>/index.html`
- [ ] If using sidecar gene storage, also stage `viewers/<slug>.genes.json` and `viewers/<slug>.genes/`
- [ ] Run `python scripts/validate_portal.py`
- [ ] Upload `viewers/` to Cloudflare R2
- [ ] Add dataset entry in `site/datasets.json`
- [ ] Confirm link opens from landing page

## Notes

- No frontend frameworks are used (plain HTML/CSS/JS).
- `exports/` and `viewers/` are intentionally excluded from git, but are expected to exist
  locally as staging artifacts during publishing.
- `upload_to_r2.py` runs a local preflight on externalized viewers before uploading.
- `validate_portal.py` also validates sidecar gene manifests referenced by single-file viewers.
- `validate_portal.py --check-remote` can verify published viewer URLs after deployment.
