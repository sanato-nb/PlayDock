"""DLsite 일반 검색 HTML의 실제 결과 카드만 추출.

2026-11-21 Windows 실제 HTML 확인:
  div#search_result_list > ul.n_worklist#search_result_img_box
    > li.search_result_img_box_inner > dd.work_name / div.multiline_truncate.
같은 카드의 '즐겨찾기', '장바구니', 추천 작품/광고 링크는 작품명이 아니다.
원문 전체의 DLsite 링크를 훑지 않는다. 구조가 달라지면 조용히 0건으로
처리하지 않고 UnknownSearchLayout을 발생시켜 진단을 요구한다.
"""
from __future__ import annotations

from html.parser import HTMLParser
from html import unescape
import re
from urllib.parse import urljoin, urlsplit

from .detector import product_page_candidate

MAX_CARDS = 40
# HTML void elements have no end-tag. Keeping them in the ancestor stack
# would make the following work-title </a> appear at the wrong depth.
VOID_TAGS = frozenset({"area","base","br","col","embed","hr","img","input",
                       "link","meta","param","source","track","wbr"})


class UnknownSearchLayout(RuntimeError):
    pass


class SearchCardParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.stack: list[tuple[str, frozenset[str], str]] = []
        self.anchor: dict | None = None
        self.rows: list[dict] = []
        self.cards = 0
        self.found_list = False

    def _has(self, token: str) -> bool:
        return any(token in classes or token == ident for _, classes, ident in self.stack)

    def handle_starttag(self, tag: str, attrs):
        data = dict(attrs)
        classes = frozenset((data.get("class") or "").split())
        ident = data.get("id") or ""
        # Detect result-list roots even if an empty search has no <li> cards.
        if ("n_worklist" in classes and
                ("search_result_img_box" == ident or "search_result_list" == ident or
                 self._has("search_result_list") or "search_result_img_box" in classes)):
            self.found_list = True
        self.stack.append((tag, classes, ident))
        if tag == "li" and "search_result_img_box_inner" in classes and self._has("n_worklist"):
            self.cards += 1
        if tag == "a" and self._has("search_result_img_box_inner") and self._has("n_worklist"):
            # Titles are in the work_name block; do not accept controls/related links.
            if self._has("work_name") or self._has("multiline_truncate"):
                href = urljoin(self.base_url, unescape(data.get("href") or ""))
                if product_page_candidate(href) is not None:
                    self.anchor = {"depth": len(self.stack), "href": href,
                                   "text": [data.get("title") or ""]}
        elif tag == "img" and self.anchor is not None:
            self.anchor["text"].append(data.get("alt") or "")
        if tag in VOID_TAGS:
            self.stack.pop()

    def handle_startendtag(self, tag: str, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, value: str):
        if self.anchor is not None:
            self.anchor["text"].append(value)

    def handle_endtag(self, tag: str):
        # HTML anchor, alt, and nested spans are part of one title.
        if tag == "a" and self.anchor is not None and self.anchor["depth"] == len(self.stack):
            href = self.anchor["href"]
            code_category = product_page_candidate(href)
            if code_category is not None:
                code, category = code_category
                title = re.sub(r"\s+", " ", " ".join(self.anchor["text"])).strip()[:240]
                if title:
                    self.rows.append({
                        "code": code, "category": category, "title": title,
                        "url": href, "scope": "search_result",
                    })
            self.anchor = None
        # Recover from malformed HTML while preserving the scoped card context.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def parse_search_cards(html: str, base_url: str) -> list[dict]:
    if (urlsplit(base_url).hostname or "").casefold() != "www.dlsite.com":
        raise UnknownSearchLayout("DLsite 공식 호스트가 아닙니다")
    parser = SearchCardParser(base_url)
    parser.feed(html)
    # An empty actual search page can have no result <li>s; do not misclassify
    # navigational/recommended product links as search hits.
    if parser.cards and not parser.rows:
        raise UnknownSearchLayout("검색 결과 카드가 있으나 작품명 링크 추출 실패")
    # Search results markup unexpectedly moved: fail closed instead of pretending 0.
    if not parser.found_list and (
        "search_result_img_box_inner" in html or "n_worklist" in html):
        raise UnknownSearchLayout("DLsite 검색 결과 목록 구조 변경")
    unique: dict[str, dict] = {}
    for row in parser.rows:
        if row["code"] not in unique:
            unique[row["code"]] = row
        if len(unique) >= MAX_CARDS:
            break
    return list(unique.values())
