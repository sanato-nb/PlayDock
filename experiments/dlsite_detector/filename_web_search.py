"""v0.11.1 — 파일명 제목의 격리·제한 시간 웹 검색.

DDGS가 백엔드 요청에서 무한 대기해도 메인 GUI/다음 검색에 영향이 없도록
별도 프로세스에서 실행하고 제한시간이 지나면 해당 프로세스를 종료한다.
Bing RSS는 API 키가 없는 무료 공개 응답이므로 형식/오류를 보수적으로 검증한다.
이 검색 모듈은 아카이브 경로/파일 본문/내부 폴더를 절대 받지 않는다.
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
import re
import time
import subprocess
import sys
import tempfile
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MAX_RESULTS = 6
MAX_XML_BYTES = 160_000
WALL_SECONDS = 13.0
_RSS_ENDPOINT = "https://www.bing.com/search"


class SearchWorkerError(RuntimeError):
    def __init__(self, message: str, *, providers=()):
        super().__init__(message)
        self.providers = tuple(providers)


class SearchWorkerTimeout(TimeoutError):
    pass


class SearchRows(list):
    """제목 검색 결과와 공급자별 품질 진단을 함께 전달한다."""
    def __init__(self, rows, providers=()):
        super().__init__(rows)
        self.providers = tuple(providers)


def _valid_url(raw: str) -> bool:
    try:
        value = urlsplit(raw)
        return value.scheme == "https" and bool(value.hostname)
    except (ValueError, TypeError):
        return False


def _clean_rss_text(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()[:700]


def bing_rss_search(title: str, *, timeout: float = 3.0,
                    opener=urlopen) -> list[dict]:
    """RSS가 아닌 HTML/차단 페이지를 '작품 없음'으로 오해하지 않는다."""
    if not title or len(title) > 180:
        return []
    url = _RSS_ENDPOINT + "?" + urlencode({
        "q": f'"{title}" game', "format": "rss",
    })
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; PlayDock-Identity-Research/0.11)",
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.5",
    })
    with opener(req, timeout=timeout) as response:
        payload = response.read(MAX_XML_BYTES + 1)
    if len(payload) > MAX_XML_BYTES:
        raise SearchWorkerError("RSS 검색 응답 크기 초과")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise SearchWorkerError("RSS 응답이 XML 형식이 아닙니다") from exc
    if root.tag.lower() != "rss" and not root.tag.lower().endswith("}rss"):
        raise SearchWorkerError("검색 제공자가 RSS가 아닌 내용을 반환했습니다")
    channel = root.find("channel")
    if channel is None:
        raise SearchWorkerError("RSS 채널이 없습니다")
    rows = []
    for entry in channel.findall("item"):
        dest = (entry.findtext("link") or "").strip()
        if not _valid_url(dest):
            continue
        rows.append({
            "href": dest,
            "title": _clean_rss_text(entry.findtext("title") or ""),
            "body": _clean_rss_text(entry.findtext("description") or ""),
        })
        if len(rows) >= MAX_RESULTS:
            break
    return rows


from .filename_page_rank import page_score
from .serper_client import serper_google_search


def _row_quality(query: str, row: dict) -> int:
    """전체 제목과 작품 URL이 부합하는 결과만 채택한다."""
    if not isinstance(row, dict):
        return 0
    return page_score(
        query,
        str(row.get("title") or ""),
        str(row.get("href") or row.get("url") or ""),
        snippet=str(row.get("body") or row.get("snippet") or ""),
    )


def _rank_relevant(query: str, rows: list[dict]) -> tuple[list[dict], list[dict], int]:
    selected = []
    dropped = []
    high = 0
    for row in list(rows)[:MAX_RESULTS * 2]:
        score = _row_quality(query, row)
        if score:
            selected.append((score, row))
            high += score >= 4
        elif isinstance(row, dict) and len(dropped) < 3:
            dropped.append({
                "title": str(row.get("title") or "")[:140],
                "url": str(row.get("href") or row.get("url") or "")[:350],
            })
    selected.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in selected], dropped, high


def search_one_title(title: str, providers: list[dict] | None = None,
                     *, serper_api_key: str = "") -> list[dict]:
    """Google 키 제공 시 Serper 우선; 결과 부적합/오류 시 DDGS → Bing RSS."""
    from .pipeline import fast_web_search

    trace = providers if providers is not None else []
    had_success = False
    faults = []
    combined: dict[str, tuple[int, dict]] = {}
    sources = (("google_serper", "ddgs", "bing_rss") if serper_api_key
               else ("ddgs", "bing_rss"))

    for source in sources:
        if combined:
            break
        begin = time.monotonic()
        try:
            if source == "google_serper":
                rows = serper_google_search(title, serper_api_key)
            elif source == "ddgs":
                rows = fast_web_search(title)
            else:
                rows = bing_rss_search(title)
            had_success = True
            accepted, examples, _ = _rank_relevant(title, list(rows))
            raw_count = len(rows)
            trace.append({
                "provider": source,
                "state": "relevant" if accepted else ("irrelevant" if rows else "empty"),
                "result_count": raw_count,
                "relevant_count": len(accepted),
                "rejected_count": raw_count - len(accepted),
                "discarded_examples": examples,
                "seconds": round(time.monotonic() - begin, 3),
            })
            for row in accepted:
                url = str(row.get("href") or row.get("url") or "")
                quality = _row_quality(title, row)
                if url not in combined or quality > combined[url][0]:
                    combined[url] = (quality, row)
        except Exception as exc:
            # 제3자 API 키는 검색 오류·결과 기록에도 남기지 않는다.
            detail = type(exc).__name__ + ": " + str(exc)[:140]
            if serper_api_key:
                detail = detail.replace(serper_api_key, "[REDACTED]")
            trace.append({
                "provider": source, "state": "error",
                "error": detail, "result_count": 0, "relevant_count": 0,
                "rejected_count": 0,
                "seconds": round(time.monotonic() - begin, 3),
            })
            faults.append(f"{source}: {detail}")
    if combined:
        return [row for _, row in sorted(
            combined.values(), key=lambda r: r[0], reverse=True
        )][:MAX_RESULTS]
    if faults:
        raise SearchWorkerError("; ".join(faults), providers=trace)
    if had_success:
        return []
    raise SearchWorkerError("검색 공급자 응답 없음", providers=trace)



def worker_main(input_path: str, output_path: str) -> int:
    """GUI와 별개로 실행되는 일회성 검색 워커. 직접 게임 ZIP을 열지 않는다."""
    try:
        raw = json.loads(Path(input_path).read_text(encoding="utf-8"))
        query = raw.get("query", "")
        if not isinstance(query, str) or not 1 <= len(query) <= 180:
            raise ValueError("검색어 길이가 잘못되었습니다")
        providers: list[dict] = []
        rows = search_one_title(
            query, providers,
            serper_api_key=os.environ.get("PLAYDOCK_SERPER_API_KEY", ""),
        )
        payload = {"ok": True, "rows": rows, "providers": providers}
    except Exception as exc:
        payload = {
            "ok": False,
            "error": type(exc).__name__,
            "details": str(exc)[:180],
            "providers": locals().get("providers", []),
        }
    Path(output_path).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8",
    )
    return 0 if payload["ok"] else 2


def isolated_web_search(title: str, *, timeout: float = WALL_SECONDS,
                        runner=subprocess.run,
                        serper_api_key: str = "") -> list[dict]:
    """제한시간 초과 시 subprocess.run이 자식 프로세스를 kill/wait한다.

    추가 검색에도 이전 검색이 잠금을 잡고 남지 않는다.
    단일 PyInstaller EXE에서도 --filename-web-worker로 자신을 다시 실행한다.
    """
    if not title or len(title) > 180:
        return []
    with tempfile.TemporaryDirectory(prefix="playdock_title_") as tmp:
        folder = Path(tmp)
        incoming = folder / "query.json"
        outgoing = folder / "result.json"
        incoming.write_text(json.dumps({"query": title}, ensure_ascii=False),
                            encoding="utf-8")
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--filename-web-worker",
                       str(incoming), str(outgoing)]
        else:
            command = [sys.executable, "-m", "scripts.filename_identity_tester",
                       "--filename-web-worker", str(incoming), str(outgoing)]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        options = {}
        if serper_api_key:
            child_env = os.environ.copy()
            child_env["PLAYDOCK_SERPER_API_KEY"] = serper_api_key
            options["env"] = child_env
        try:
            # Linux/Windows 모두 timeout 이후 자식 종료를 기다림. 프로그램
            # 내부 스레드 잠금과 달리 다음 파일 검색이 막히지 않는다.
            finished = runner(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=timeout,
                creationflags=flags, **options,
            )
        except subprocess.TimeoutExpired as exc:
            raise SearchWorkerTimeout(
                f"웹 검색 워커가 {timeout:g}초 안에 종료되지 않아 강제 종료했습니다"
            ) from exc
        if not outgoing.is_file():
            raise SearchWorkerError(
                "웹 검색 워커가 결과를 기록하지 못했습니다 "
                f"(exit={finished.returncode})"
            )
        try:
            payload = json.loads(outgoing.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise SearchWorkerError("웹 검색 결과를 해석하지 못했습니다") from exc
        if not payload.get("ok"):
            raise SearchWorkerError(
                f"{payload.get('error', 'WorkerError')}: "
                f"{payload.get('details','')}",
                providers=payload.get("providers", []),
            )
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise SearchWorkerError("웹 검색 결과가 배열이 아닙니다")
        return SearchRows(
            [row for row in rows[:MAX_RESULTS] if isinstance(row, dict)],
            payload.get("providers", []),
        )
