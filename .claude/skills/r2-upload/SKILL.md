---
name: r2-upload
description: Prepare exported KaroSpace viewer bundles for website/R2 upload. Use when user has an exported viewer HTML file plus its `.genes.json` manifest and shard directory, needs to sanity-check the bundle layout, and generate the exact bash commands for staging, dry-run upload, live upload, and optional local sidecar validation.
argument-hint: "[html-path] [manifest-path] [shards-path]"
---

# KaroSpace R2 Uploader

Use this skill when the user already has a KaroSpace export and wants upload commands, not when the main task is creating a new dataset card or thumbnail.

## Workflow

1. Verify the three required inputs exist:
   - exported HTML viewer (`.html`)
   - exported `.genes.json` manifest
   - shard directory (`.genes/` containing `.bin` files)
2. If `$ARGUMENTS` are provided, treat them as paths to these three files in order. Otherwise, ask the user or infer from context.
3. Prefer a temporary staging directory plus `--viewers-dir` over per-file uploads.
4. Use `scripts/upload_to_r2.py` from the repo root and emit both:
   - dry run
   - real upload
5. When helpful, also emit the optional local validation block that calls `portal_validation.validate_viewers_tree(...)` on the staging directory.

## Rules

- Preserve the source bundle names exactly when copying into the staging directory.
- Stage the shard directory under the same basename that appears in the export.
- Use `rsync -a --delete` for the shard directory so reruns stay clean.
- Default the staging directory to `/tmp/<stage-name>-r2`.
- If the user already has the files refreshed under the repo's local `viewers/` tree, generate commands from those repo-local paths.
- If the user only gives source export paths outside the repo, generate commands directly from those source paths rather than forcing a copy into `viewers/`.
- Keep the answer compact: one bash block for upload, one optional bash block for validation.
- Always dry-run first, show results, then confirm before live upload.
- R2 credentials must be in environment (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET`).

## Output Pattern

Use this structure unless the user asks for something else:

```bash
cd /path/to/repo

STAGE_DIR=/tmp/<stage-name>-r2

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

cp /path/to/viewer.html "$STAGE_DIR/"
cp /path/to/manifest.genes.json "$STAGE_DIR/"
rsync -a --delete \
  /path/to/shards/ \
  "$STAGE_DIR/shards/"

python scripts/upload_to_r2.py --viewers-dir "$STAGE_DIR" --dry-run
python scripts/upload_to_r2.py --viewers-dir "$STAGE_DIR"
```

Optional local validation block:

```bash
cd /path/to/repo
python -c 'from pathlib import Path; import sys; sys.path.insert(0, "scripts"); from portal_validation import validate_viewers_tree, format_report; print(format_report(validate_viewers_tree(Path("/tmp/<stage-name>-r2"))))'
```
