"""두 개의 PlayDock 독립 검색기에서 공유하는 Tkinter UI. API/키/압축 검사 없음."""
from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
from urllib.parse import urlencode

from experiments.dlsite_detector.detector import EXACT_CODE
from experiments.dlsite_detector.search_terms import cleaned_search_title

from experiments.dlsite_detector.reverse_lookup import (
    Lookup, lookup_code, lookup_title, parse_catalog_links,
)


STATUS_KO = {
    "confirmed": "공식 확인", "candidates": "후보 · 확인 필요",
    "no_candidate": "후보 없음", "unavailable": "조회 실패",
    "invalid": "입력 오류",
}
CONFIDENCE_KO = {
    "exact_title": "공식 제목 일치", "official_code": "공식 품번 확인",
    "search_candidate": "검색 링크 후보",
}
CONFIG = {
    "title_to_code": (
        "PlayDock — 이름으로 DLsite 품번 찾기",
        "게임 이름을 한 줄에 하나씩 입력하세요. 파일명(.zip/.7z/.rar)도 가능합니다.",
        "예: 작품명 또는 Game Name [v1.2].zip",
    ),
    "code_to_title": (
        "PlayDock — DLsite 품번으로 이름 찾기",
        "DLsite RJ/VJ/BJ/EJ 품번을 한 줄에 하나씩 입력하세요.",
        "예: RJ12345678",
    ),
}


class LookupWindow(tk.Tk):
    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode
        heading, hint, example = CONFIG[mode]
        self.title(heading + " (API 없음)")
        self.geometry("1160x720")
        self.minsize(850, 500)
        self.messages = Queue()
        self.cancel = Event()
        self.results: list[Lookup] = []
        self.busy = False
        self.selection_urls: dict[str, str] = {}

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=heading, font=("맑은 고딕", 16, "bold")).pack(anchor="w")
        ttk.Label(outer, text=hint).pack(anchor="w", pady=(4, 2))
        ttk.Label(outer, text="공개 HTML 웹페이지 조회만 수행 · API 키 불필요 · 후보와 공식 확인 구별",
                  foreground="#555").pack(anchor="w", pady=(0, 8))
        self.input = tk.Text(outer, height=5, undo=True, wrap="none")
        self.input.pack(fill="x")
        self.input.insert("1.0", "")
        self.input.configure(font=("맑은 고딕", 10))
        ttk.Label(outer, text=example, foreground="#666").pack(anchor="w", pady=(3, 8))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 6))
        self.start = ttk.Button(controls, text="검색 시작", command=self.run_search)
        self.start.pack(side="left")
        self.stop = ttk.Button(controls, text="중단", command=self.cancel.set, state="disabled")
        self.stop.pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="입력 지우기",
                   command=lambda: self.input.delete("1.0", "end")).pack(side="left", padx=6)
        ttk.Button(controls, text="브라우저에서 직접 찾기",
                   command=self.open_browser_search).pack(side="left", padx=6)
        self.json_btn = ttk.Button(controls, text="JSON 저장", command=self.save_json, state="disabled")
        self.json_btn.pack(side="right")
        self.csv_btn = ttk.Button(controls, text="CSV 저장", command=self.save_csv, state="disabled")
        self.csv_btn.pack(side="right", padx=6)
        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(2, 4))
        self.status = tk.StringVar(value="검색할 내용을 입력하세요.")
        ttk.Label(outer, textvariable=self.status).pack(anchor="w", pady=(0, 6))

        columns = ("query", "status", "code", "title", "confidence", "source")
        self.table = ttk.Treeview(outer, columns=columns, show="headings", selectmode="browse")
        labels = ("입력", "상태", "품번", "공식 이름 / 검색 후보", "검증 수준", "근거")
        widths = (170, 125, 125, 350, 145, 150)
        for key, label, width in zip(columns, labels, widths):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=80)
        frame = ttk.Frame(outer)
        frame.pack(fill="both", expand=True)
        self.table.pack(in_=frame, side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self._on_select)
        self.table.bind("<Double-1>", self._open_page)
        ttk.Label(outer, text="상세 근거 · 항목을 더블클릭하면 DLsite 작품 페이지를 엽니다.").pack(
            anchor="w", pady=(8, 2))
        self.details = tk.Text(outer, height=6, state="disabled", wrap="word")
        self.details.pack(fill="x")
        self.after(100, self._poll)

    def run_search(self):
        if self.busy:
            return
        lines = [v.strip() for v in self.input.get("1.0", "end").splitlines() if v.strip()]
        if not lines:
            messagebox.showwarning("검색어 없음", "이름이나 품번을 입력하세요.")
            return
        if len(lines) > 100:
            messagebox.showwarning("입력 제한", "한 번에 최대 100개까지 검사할 수 있습니다.")
            return
        self.results.clear()
        self.selection_urls.clear()
        for row in self.table.get_children():
            self.table.delete(row)
        self.progress.configure(value=0)
        self.cancel.clear()
        self.busy = True
        self.start.configure(state="disabled")
        self.stop.configure(state="normal")
        self.json_btn.configure(state="disabled")
        self.csv_btn.configure(state="disabled")
        Thread(target=self._search_worker, args=(lines,), daemon=True).start()

    def _search_worker(self, lines: list[str]):
        for i, value in enumerate(lines):
            if self.cancel.is_set():
                break
            try:
                result = lookup_title(value) if self.mode == "title_to_code" else lookup_code(value)
            except Exception as exc:
                result = Lookup(self.mode, value, "unavailable",
                                warnings=("처리 오류: " + type(exc).__name__,))
            self.messages.put(("result", result, i + 1, len(lines)))
        self.messages.put(("done",))

    def _poll(self):
        try:
            while True:
                msg = self.messages.get_nowait()
                if msg[0] == "result":
                    _, result, index, total = msg
                    self.results.append(result)
                    self.progress.configure(value=100 * index / total)
                    self.status.set(f"{index}/{total}개 검사 완료 · {STATUS_KO.get(result.status, result.status)}")
                    for candidate in result.matches:
                        iid = str(len(self.selection_urls))
                        self.selection_urls[iid] = candidate.url
                        self.table.insert("", "end", iid=iid, values=(
                            result.query, STATUS_KO.get(result.status, result.status),
                            candidate.code, candidate.title,
                            CONFIDENCE_KO.get(candidate.confidence, candidate.confidence),
                            candidate.source,
                        ), tags=("verified",) if candidate.confidence != "search_candidate" else ())
                    if not result.matches:
                        iid = str(len(self.selection_urls))
                        self.selection_urls[iid] = ""
                        self.table.insert("", "end", iid=iid, values=(
                            result.query, STATUS_KO.get(result.status, result.status),
                            "-", "-", "-", "-",
                        ))
                elif msg[0] == "done":
                    self.busy = False
                    self.start.configure(state="normal")
                    self.stop.configure(state="disabled")
                    self.json_btn.configure(state="normal" if self.results else "disabled")
                    self.csv_btn.configure(state="normal" if self.results else "disabled")
                    self.status.set(f"검색 완료: {len(self.results)}개 · "
                                    f"공식 제목 일치 {sum(any(m.confidence in ('exact_title', 'official_code') for m in r.matches) for r in self.results)}개"
                                    + (" · 중단됨" if self.cancel.is_set() else ""))
        except Empty:
            pass
        self.after(100, self._poll)

    def _on_select(self, _event=None):
        item = self.table.selection()
        if not item:
            return
        values = self.table.item(item[0], "values")
        match = next((m for r in self.results for m in r.matches
                      if m.code == values[2] and m.title == values[3]), None)
        record = next((r for r in self.results if r.query == values[0]), None)
        lines = [f"입력: {values[0]}", f"상태: {values[1]}"]
        if match:
            lines += [f"품번: {match.code}", f"제목: {match.title}",
                      f"검증: {CONFIDENCE_KO.get(match.confidence, match.confidence)}",
                      f"설명: {match.note}", f"URL: {match.url}"]
        if record and record.warnings:
            lines += ["", "조회 경고:", *record.warnings]
        if record and record.providers:
            lines += ["", "검색 사이트:", *(str(p) for p in record.providers)]
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")

    def _open_page(self, _event=None):
        selection = self.table.selection()
        if selection:
            link = self.selection_urls.get(selection[0], "")
            if link.startswith("https://www.dlsite.com/"):
                webbrowser.open(link)

    def open_browser_search(self):
        """HTML 자동 검색이 차단될 때 사용자 브라우저로 일반 페이지를 엶."""
        selection = self.table.selection()
        if selection:
            values = self.table.item(selection[0], "values")
            value = str(values[0]) if values else ""
        else:
            value = next((line.strip() for line in self.input.get("1.0", "end").splitlines()
                          if line.strip()), "")
        if not value:
            messagebox.showwarning("입력 없음", "먼저 게임 이름이나 품번을 입력하세요.")
            return
        if self.mode == "title_to_code":
            query = cleaned_search_title(value)
            if not query:
                messagebox.showwarning("검색어 없음", "게임 이름을 입력하세요.")
                return
            url = "https://www.google.com/search?" + urlencode({
                "q": 'site:dlsite.com "' + query + '"'
            })
        else:
            code = value.upper()
            if not EXACT_CODE.fullmatch(code):
                messagebox.showwarning("품번 형식 오류", "RJ/VJ/BJ/EJ + 숫자 6~8자리로 입력하세요.")
                return
            section = {"RJ": "maniax", "VJ": "soft", "BJ": "girls",
                       "EJ": "girls"}.get(code[:2], "maniax")
            url = (f"https://www.dlsite.com/{section}/work/=/product_id/{code}.html")
        webbrowser.open(url)

    def save_json(self):
        if not self.results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile="PlayDock_" + self.mode + "_no_api.json")
        if path:
            payload = {"program": "PlayDock " + self.mode, "mode": self.mode,
                       "created_at_local": datetime.now().astimezone().isoformat(),
                       "api_used": False, "results": [r.to_dict() for r in self.results],
                       "notice": "HTML 검증 결과이며 로컬 게임 파일 내용은 검사하지 않았습니다."}
            try:
                Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("저장 실패", str(exc))

    def save_csv(self):
        if not self.results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile="PlayDock_" + self.mode + "_no_api.csv")
        if path:
            try:
                with open(path, "w", encoding="utf-8-sig", newline="") as fp:
                    writer = csv.writer(fp)
                    writer.writerow(["입력", "상태", "품번", "상품명", "검증 수준", "출처", "URL", "경고"])
                    for r in self.results:
                        for m in r.matches or (None,):
                            writer.writerow([r.query, r.status,
                                             m.code if m else "", m.title if m else "",
                                             m.confidence if m else "",
                                             m.source if m else "", m.url if m else "",
                                             " / ".join(r.warnings)])
            except OSError as exc:
                messagebox.showerror("저장 실패", str(exc))


def self_test(mode: str) -> int:
    """빌드 EXE 자체 확인: 인터넷 접속하지 않음."""
    assert mode in CONFIG
    assert lookup_code("RJINVALID").status == "invalid"
    sample = ('<a href="/maniax/work/=/product_id/RJ123456.html">'
              '<img alt="Example Work"></a>')
    items = parse_catalog_links(sample, "https://www.dlsite.com/maniax/fsr/=/")
    assert items[0]["code"] == "RJ123456"
    assert items[0]["title"] == "Example Work"
    print("PlayDock " + mode + " offline self-test OK", flush=True)
    return 0


def main(mode: str):
    if "--self-test" in sys.argv:
        sys.exit(self_test(mode))
    LookupWindow(mode).mainloop()
