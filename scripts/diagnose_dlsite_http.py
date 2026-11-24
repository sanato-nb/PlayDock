"""DLsite HTML 접속 장애 원인 조사. API 키·쿠키·개인 정보 미사용.

특정 공개 URL에 접속했을 때 HTTP 코드, 응답 형식, 리다이렉트, 오류 종류만
출력한다. 로그인/성인 인증/보안 차단을 우회하지 않으며 페이지 본문은 저장하지 않는다.
"""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from collections import Counter
import re
import socket
import ssl

TIMEOUT = 6.0
MAX_READ = 2_500_001


class _Facts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = Counter()
    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1


def probe(label: str, url: str, *, browser_headers: bool = False):
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
          if browser_headers else
          "Mozilla/5.0 (compatible; PlayDockFilenameResearch/0.11.7)")
    req = Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    })
    variant = "browser-UA" if browser_headers else "current-PlayDock-UA"
    try:
        with urlopen(req, timeout=TIMEOUT) as response:
            final = response.geturl()
            body = response.read(MAX_READ)
            ctype = (response.headers.get("Content-Type") or "").split(";")[0]
            moved = (urlsplit(final).hostname != urlsplit(url).hostname or
                     urlsplit(final).path != urlsplit(url).path)
            found = _Facts()
            try:
                found.feed(body.decode("utf-8", "replace"))
            except Exception:
                pass
            lower = body[:100_000].lower()
            markers = [name for name, term in [
                ("captcha", b"captcha"), ("challenge", b"challenge"),
                ("age-check", b"age_check"), ("result-links", b"product_id"),
                ("script", b"<script")
            ] if term in lower]
            print("PROBE", label, variant, "HTTP", response.status,
                  "ctype", ctype, "redirected", moved,
                  "bytes_read", len(body), "size_over_limit", len(body)>2_500_000,
                  "anchor_sample", found.tags["a"],
                  "markers", ",".join(markers) or "none", flush=True)
    except HTTPError as exc:
        ctype = (exc.headers.get("Content-Type") or "").split(";")[0]
        print("PROBE", label, variant, "HTTP", exc.code,
              "ctype", ctype, "redirected", exc.url != url,
              "error", "HTTPError", flush=True)
    except URLError as exc:
        reason = exc.reason
        detail = "dns" if isinstance(reason, socket.gaierror) else (
            "ssl" if isinstance(reason, ssl.SSLError) else type(reason).__name__)
        print("PROBE", label, variant, "NETWORK", detail,
              "error", type(exc).__name__, flush=True)
    except Exception as exc:
        print("PROBE", label, variant, "ERROR", type(exc).__name__, flush=True)


def main():
    probes = [
        ("maniax-home", "https://www.dlsite.com/maniax/"),
        ("maniax-search", "https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/RPG/"),
        ("home-search", "https://www.dlsite.com/home/fsr/=/language/jp/keyword/RPG/"),
        ("known-product", "https://www.dlsite.com/maniax/work/=/product_id/RJ01379611.html"),
    ]
    for label, url in probes:
        probe(label, url)
    # 헤더가 원인인지 동등한 공개 GET 요청으로만 비교. 쿠키/로그인/우회 없음.
    probe("maniax-search", probes[1][1], browser_headers=True)
    # Search route-space encoding A/B test, one public title, same language/category.
    for label, path in [
        ("space-percent20", "Stardew%20Valley"),
        ("space-plus", "Stardew+Valley"),
        ("space-hyphen", "Stardew-Valley"),
    ]:
        probe(label, "https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/" + path + "/")

    # Read/parse with the actual PlayDock code path (not just urllib).
    from experiments.dlsite_detector.reverse_lookup import search_catalog_html
    from experiments.dlsite_detector.no_api_html import _fetch_html, PublicHtmlUnavailable
    for category in ("maniax", "home", "soft", "girls"):
        for title in ("RPG", "NOR", "Stardew Valley", "AnUnlistedPlayDockFiction2026"):
            try:
                rows = search_catalog_html(title, category, timeout=6)
                print("REAL_CATALOG", title, category, "ok", len(rows), flush=True)
            except PublicHtmlUnavailable as exc:
                print("REAL_CATALOG", title, category,
                      "unavailable", str(exc)[:160], flush=True)
            except Exception as exc:
                print("REAL_CATALOG", title, category,
                      "error", type(exc).__name__, flush=True)



if __name__ == "__main__":
    main()
