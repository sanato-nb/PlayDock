"""실제 검색 결과 카드에 과거 후보 품번이 포함되는지 검증.

로컬 게임 목록·경로·검색 결과 원문을 기록하지 않는다.
단순히 공개 작품번호가 DLsite 검색 결과에 존재하는지와 검색 개수를 기록한다.
"""
from experiments.dlsite_detector.reverse_lookup import search_catalog_html
from experiments.dlsite_detector.no_api_html import fetch_dlsite_html

def main():
    for query, expected in (
        ("BUZAMA 2", "RJ01052720"),
        ("BUZAMA 3", "RJ01305436"),
        ("Project Dungeon", ""),
    ):
        try:
            rows = search_catalog_html(query, "maniax", timeout=7)
            ids = [r["code"] for r in rows]
            print("PRESENCE", repr(query), "scoped_cards", len(ids),
                  "historic_candidate_in_first_page", expected in ids if expected else "unknown",
                  flush=True)
        except Exception as exc:
            print("PRESENCE", repr(query), "error", type(exc).__name__,flush=True)
        if expected:
            try:
                product = fetch_dlsite_html(expected,timeout=4)
                print("PRODUCT",expected,"official_page_title_available",
                      bool(product and product.title),flush=True)
            except Exception as exc:
                print("PRODUCT",expected,"error",type(exc).__name__,flush=True)

if __name__ == "__main__":
    main()
