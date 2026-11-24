"""Apply explicitly selected, already verified DB artwork in bounded batches."""
from pathlib import Path
from database.work_repository import WorkDatabase
from integrations.official_lookup.code_only import Work
from services.official_artwork_service import (
    trusted_image_url, prepare_official_images, apply_checked_images,
)


def apply_bulk_artwork(library, db_path, jobs, *, cancelled=lambda: False,
                       progress=lambda i, n, name: None, prepare=prepare_official_images,
                       apply=apply_checked_images):
    db = WorkDatabase(Path(db_path).parent, db_path=Path(db_path))
    results = []
    for index, (game, identity, selected, overwrite) in enumerate(jobs, 1):
        if cancelled():
            break
        row = {"name": game.name, "applied": [], "skipped": []}
        results.append(row)
        try:
            record = db.get_linked_official_work(game.id)
            meta = library.meta(game)
            if (not record or (record["store"], record["code"]) != identity
                    or ("product_code" in meta and not meta.get("product_code"))):
                row["skipped"] = ["공식 연결 변경"] * len(selected)
                continue
            work = Work(record["code"], record["title"], record.get("category") or "",
                        record["page_url"], "verified", record["store"])
            urls = {r["kind"]: r["url"] for r in record.get("images", ())
                    if isinstance(r, dict) and r.get("kind") in selected
                    and trusted_image_url(work.store, work.code, r.get("url", ""))}
            folder = library.art_dir(game)
            # Only existing images explicitly approved for replacement can be overwritten.
            urls = {k:v for k,v in urls.items()
                    if k in overwrite or not (folder / f"{k}.png").exists()}
            offerings = prepare(work, candidates=urls) if urls else {}
            for kind in ("hero", "icon"):
                if kind not in selected:
                    continue
                if (cancelled() or kind not in offerings or
                    (kind not in overwrite and (folder / f"{kind}.png").exists())):
                    row["skipped"].append(f"{kind}: 중단·후보 없음·기존 이미지 보호")
                    continue
                # Verify the link again after network I/O.
                latest = db.get_linked_official_work(game.id)
                fresh = library.meta(game)
                if (not latest or (latest["store"], latest["code"]) != identity
                        or ("product_code" in fresh and not fresh.get("product_code"))):
                    row["skipped"].append(f"{kind}: 공식 연결 변경")
                    continue
                try:
                    applied = apply(library, game, work, offerings, {kind})
                    row["applied"].extend(applied)
                    if not applied:
                        row["skipped"].append(f"{kind}: 적용 안 됨")
                except (OSError, ValueError, RuntimeError) as exc:
                    row["skipped"].append(f"{kind}: {type(exc).__name__}")
        except Exception as exc:
            row["skipped"].extend(f"{k}: {type(exc).__name__}" for k in selected
                                  if k not in row["applied"] and
                                  not any(s.startswith(k+":") for s in row["skipped"]))
        finally:
            progress(index, len(jobs), game.name)
    return results
