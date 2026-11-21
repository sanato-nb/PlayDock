"""브라우저 JavaScript로 Google 일반 검색 결과 접근 가능 여부 점검.

Windows GitHub Actions Chrome headless/표준 Selenium만 사용. 개인 계정/쿠키/프록시
CAPTCHA 우회 없음. 결과 URL/원문/개인 검색 기록은 저장하지 않음.
"""
from __future__ import annotations

import time
from urllib.parse import urlencode, urlsplit

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

def main():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    print("GOOGLE_BROWSER starting",flush=True)
    try:
        with webdriver.Chrome(options=options) as browser:
            browser.set_page_load_timeout(18)
            for q in ("Giant Treasure DLsite RJ", "비겁자의 비보 Hero Legend DLsite"):
                try:
                    browser.get("https://www.google.com/search?" + urlencode({"q":q,"num":10}))
                    time.sleep(2.5)
                    text = browser.find_element(By.TAG_NAME, "body").text[:2500].casefold()
                    anchors = browser.find_elements(By.TAG_NAME, "a")
                    hits = sum("www.dlsite.com" in (a.get_attribute("href") or "")
                               for a in anchors)
                    print("GOOGLE_BROWSER",ascii(q),"title",ascii(browser.title[:80]),
                          "links",len(anchors),"dlsite_urls",hits,
                          "need_js","enable javascript" in text,
                          "captcha",("unusual traffic" in text or "captcha" in text),
                          "consent","before you continue" in text,
                          flush=True)
                except Exception as exc:
                    print("GOOGLE_BROWSER",ascii(q),"error",type(exc).__name__,flush=True)
    except Exception as exc:
        print("GOOGLE_BROWSER setup_error",type(exc).__name__,
              ascii(str(exc))[:180],flush=True)

if __name__ == "__main__":
    main()
