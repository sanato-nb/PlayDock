"""DLsite→인터넷 검색 실험 CLI와 수동 검토·이름·이미지 변경 단계.

기본 명령은 온라인 요청 없이 데이터 확인만 한다.
검색은 --online 명시 시에만 실행한다. 본체/사용자 DB와 분리해 사용한다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import classify_game
from .review_store import ReviewStore
from .artwork_staging import ArtworkStaging


def _dump(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PlayDock 독립 검색·변경 검토 실험")
    parser.add_argument("--db", type=Path, required=True, help="실험용 DB 경로 (*.db), 본체 playdock.db 사용 금지")
    sub = parser.add_subparsers(dest="action", required=True)

    scan = sub.add_parser("scan", help="DLsite→인터넷 순서로 조회, DB에 결과 기록")
    scan.add_argument("--id", required=True, help="개인 데이터와 무관한 고정 게임 ID")
    scan.add_argument("--title", required=True, help="원본 표시 게임명")
    scan.add_argument("--archive", required=True, help="원본 압축파일 이름 (경로 금지)")
    scan.add_argument("--size", type=int, default=None, help="원본 압축파일 크기(바이트)")
    scan.add_argument("--code", default="", help="직접 확인한 DLsite 작품 코드")
    scan.add_argument("--online", action="store_true", help="인터넷 조회를 명시적으로 허용")

    queue = sub.add_parser("queue", help="조회 불가/비게임 추정 별도 목록")
    queue.add_argument("kind", choices=("unresolved", "non-game"))

    manual = sub.add_parser("manual", help="수동으로 게임 여부 분류")
    manual.add_argument("--id", required=True)
    manual.add_argument("--status", choices=("manual_game", "manual_non_game", "lookup_unavailable"), required=True)
    manual.add_argument("--reason", default="사용자가 확인해 변경함")

    change = sub.add_parser("name-stage", help="이름 변경 전후를 DB에 먼저 기록")
    change.add_argument("--id", required=True)
    change.add_argument("--field", choices=("display_name", "archive_label"), default="display_name")
    change.add_argument("--new", required=True)

    apply_name = sub.add_parser("name-apply", help="DB에 미리 기록한 이름 변경 적용")
    apply_name.add_argument("--change", type=int, required=True)

    restore = sub.add_parser("name-restore", help="DB에 기록 후 원본 표시 이름으로 복구")
    restore.add_argument("--id", required=True)
    restore.add_argument("--field", choices=("display_name", "archive_label"), default="display_name")

    image = sub.add_parser("image-stage", help="새 PNG/기존 PNG를 DB에 먼저 저장")
    image.add_argument("--id", required=True)
    image.add_argument("--kind", choices=("hero", "icon"), required=True)
    image.add_argument("--image", type=Path, required=True)
    image.add_argument("--cache-root", type=Path, required=True, help="실험용 이미지 캐시 경로")
    image.add_argument("--source", default="")

    for action in ("image-apply", "image-restore"):
        cmd = sub.add_parser(action, help="DB에 기록된 이미지 적용/복원")
        cmd.add_argument("--change", type=int, required=True)
        cmd.add_argument("--cache-root", type=Path, required=True)

    history = sub.add_parser("history", help="검색/수동 분류/이름 변경 이력")
    history.add_argument("--id", required=True)

    args = parser.parse_args(argv)
    if args.db.name.lower() == "playdock.db":
        parser.error("실험 단계에서는 본체 playdock.db를 사용하지 마세요. 별도 DB 파일을 지정해야 합니다.")
    store = ReviewStore(args.db)
    if args.action == "scan":
        if not args.online:
            parser.error("네트워크 요청과 검색 결과 저장은 --online 명시가 필요합니다.")
        store.add_game(args.id, args.title, args.archive, archive_size=args.size)
        result = classify_game(args.title, code=args.code)
        store.save_search_result(args.id, result)
        _dump(result.to_dict())
        return 0
    if args.action == "queue":
        _dump(store.list_unresolved() if args.kind == "unresolved"
              else store.list_suspected_non_game())
        return 0
    if args.action == "manual":
        store.manual_classify(args.id, args.status, reason=args.reason)
        _dump(store.get_game(args.id))
        return 0
    if args.action == "name-stage":
        _dump({"pending_change": store.stage_name_change(args.id, args.new, field=args.field),
               "note": "원본 파일은 변경하지 않았습니다."})
        return 0
    if args.action == "name-apply":
        _dump(store.apply_name_change(args.change))
        return 0
    if args.action == "name-restore":
        _dump({"restore_change": store.restore_original_name(args.id, field=args.field)})
        return 0
    if args.action == "image-stage":
        artwork = ArtworkStaging(args.db)
        _dump({"pending_change": artwork.stage_image(
            args.id, args.kind, args.image.read_bytes(),
            cache_root=args.cache_root, source=args.source),
            "note": "DB에 먼저 저장했으며 실제 PNG 파일은 변경하지 않았습니다."})
        return 0
    if args.action in {"image-apply", "image-restore"}:
        artwork = ArtworkStaging(args.db)
        if args.action == "image-apply":
            artwork.apply_image(args.change, cache_root=args.cache_root)
        else:
            artwork.restore_image(args.change, cache_root=args.cache_root)
        _dump(artwork.get_change(args.change))
        return 0
    if args.action == "history":
        _dump({
            "game": store.get_game(args.id),
            "search": store.search_history(args.id),
            "classifications": store.classification_history(args.id),
            "names": store.name_history(args.id),
            "artwork": ArtworkStaging(args.db).list_changes(args.id),
        })
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
