---
name: r2-upload
description: Stage and upload exported KaroSpace viewer bundles (sidecar HTML + gene manifest + shard directory) to Cloudflare R2. Use when user has an exported viewer and wants to upload it.
disable-model-invocation: true
argument-hint: "[html-path] [manifest-path] [shards-path]"
---

# KaroSpace R2 Uploader

Stage an exported KaroSpace viewer bundle and upload it to Cloudflare R2.

## Inputs

The three required files for a sidecar viewer upload:

1. **Sidecar HTML viewer** (`.html`)
2. **Gene manifest** (`.genes.json`)
3. **Shard directory** (`.genes/` containing `.bin` files)

If `$ARGUMENTS` are provided, treat them as paths to these three files in order.
Otherwise, ask the user or infer from context.

## Workflow

1. **Validate** that all three inputs exist and the manifest references the shard directory.
2. **Generate staging commands** using `scripts/emit_r2_upload_commands.py`:
   ```
   python scripts/emit_r2_upload_commands.py \
     --repo-root "$(pwd)" \
     --html <html-path> \
     --manifest <manifest-path> \
     --shards <shards-path> \
     --include-validation
   ```
3. **Stage** files into `/tmp/<stage-name>-r2/` using the emitted commands.
4. **Dry run** upload with `python scripts/upload_to_r2.py --viewers-dir "$STAGE_DIR" --dry-run` — show output to user.
5. **Confirm** with user before live upload.
6. **Upload** with `python scripts/upload_to_r2.py --viewers-dir "$STAGE_DIR"`.

## Rules

- Preserve source bundle filenames exactly when staging.
- Stage shard directory under its original basename.
- Use `rsync -a --delete` for the shard directory.
- Default staging to `/tmp/<stage-name>-r2`.
- Always dry-run first, show results, then confirm before live upload.
- R2 credentials must be in environment (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET`).
