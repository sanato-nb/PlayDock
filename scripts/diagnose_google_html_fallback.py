"""DLsite 직접 검색 실패 후 Google HTML 무키 검색의 실제 추출 가능성을 검증.

일반 공개 GET만 사용. 쿠키, 계정, 프록시, CAPTCHA 우회 없음.
콘솔에는 URL이나 원문을 저장하지 않고 HTTP 상태/응답 내 링크 개수만 출력.
"""
from __future__ import annotations
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from html.parser import HTMLParser
from experiments.dlsite_detector.reverse_lookup import (
    search_catalog_html, search_engine_html, parse_catalog_links, parse_web_code_hints,
)
from experiments.dlsite_detector.no_api_html import PublicHtmlUnavailable

MAX_BYTES = 1_000_000

class LinkFacts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.meta = []
    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "a":
            self.links.append((props.get("href", ""), props.get("class", "")))
        elif tag == "meta":
            self.meta.append((props.get("name", ""), props.get("content", "")))

def inspect_query(query: str, *, params: dict):
    request = Request("https://www.google.com/search?" + urlencode({"q": query, **params}), headers={
        "User-Agent": "Mozilla/5.0 (compatible; PlayDockFilenameResearch/0.11.7)",
        "Accept": "text/html,application/xhtml+xml;q=0.9",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    })
    try:
        with urlopen(request, timeout=7) as response:
            status = response.status
            final = response.geturl()
            raw = response.read(MAX_BYTES+1)
            kind = response.headers.get("Content-Type", "").split(";")[0]
        body = raw.decode("utf-8", errors="replace")
        facts = LinkFacts()
        facts.feed(body)
        match_links = parse_catalog_links(body,final)
        hints = parse_web_code_hints(body,final,query)
        print("GOOGLE_PROBE", repr(query), repr(params), "HTTP", status,
              "type", kind, "bytes", len(raw), "anchors", len(facts.links),
              "official_urls", len(match_links), "code_hints", len(hints),
              "redirected", urlsplit(final).hostname!="www.google.com",
              "consent", "consent" in body[:20000].lower(),
              "captcha", "captcha" in body[:20000].lower(),
              "first_href_shapes", [u.split("?")[0][:42] for u, c in facts.links[:4]],
              flush=True)
    except HTTPError as err:
        print("GOOGLE_PROBE", repr(query), repr(params), "HTTP", err.code, flush=True)
    except Exception as err:
        print("GOOGLE_PROBE", repr(query), repr(params), "ERROR", type(err).__name__, flush=True)

def main():
    titles = ["비겁자의 비보 Hero Legend", "Giant Treasure"]
    for q in titles:
        for params in ({"num":"10"}, {"num":"10","udm":"14"}, {"num":"10","gbv":"1"}):
            inspect_query(q,params=params)
        try:
            hits=search_engine_html(q,"google_html",timeout=7)
            print("GOOGLE_REAL_SEARCH",repr(q),"ok",len(hits),flush=True)
        except PublicHtmlUnavailable as exc:
            print("GOOGLE_REAL_SEARCH",repr(q),"unavailable",str(exc)[:100],flush=True)
        except Exception as exc:
            print("GOOGLE_REAL_SEARCH",repr(q),"error",type(exc).__name__,flush=True)

if __name__=="__main__":
    main()
