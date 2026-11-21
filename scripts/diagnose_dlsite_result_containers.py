"""DLsite 공개 검색 HTML의 '검색 결과 카드' 식별 근거 조사.
원문/작품명/개인 검색어를 기록하지 않고 태그와 class/id 통계만 출력.
"""
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import quote

from experiments.dlsite_detector.no_api_html import _fetch_html, PublicHtmlUnavailable
from experiments.dlsite_detector.detector import product_page_candidate

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.links = []
        self.tags = Counter()
        self.blocks = Counter()
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        tokens = (d.get("class") or "").split()
        identifier = d.get("id") or ""
        self.stack.append((tag, tokens, identifier))
        if tag in ("ul","ol","table","div","section","li","article") and (identifier or tokens):
            for text in tokens[:6]:
                self.blocks[(tag,"class",text)] += 1
            if identifier:
                self.blocks[(tag,"id",identifier)] += 1
        if tag=="a":
            url = d.get("href") or ""
            if product_page_candidate(url) or "/product_id/" in url:
                nearest=[(t,".".join(cls[:3]),idv[:60]) for t,cls,idv in self.stack if cls or idv][-6:]
                self.links.append((url,nearest))
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs); self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:]
                break

def main():
    for q in ("RPG", "Stardew Valley", "AnUnlistedPlayDockFiction2026"):
        url="https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/"+quote(q,safe="").replace("%20","+").replace("%2B","%2B")+"/"
        try:
            _,html=_fetch_html(url,timeout=8)
            p=Parser();p.feed(html)
            print("DIAG",ascii(q),"html_length",len(html),"total_links",len(p.links),flush=True)
            print("BLOCKS",p.blocks.most_common(45),flush=True)
            print("PATHS",ascii(q),[x[1] for x in p.links[:12]],flush=True)
        except PublicHtmlUnavailable as e:
            print("DIAG",ascii(q),"unavailable",type(e).__name__,str(e),flush=True)

if __name__=="__main__":
    main()
