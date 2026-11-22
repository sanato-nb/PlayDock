"""PlayDock — DLsite 품번 전용 경량 Windows GUI. Tkinter 표준 라이브러리만 사용."""
from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
from queue import Queue, Empty
import sys
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from experiments.dlsite_detector.code_only import (
    MAX_BATCH, Result, Work, check, codes_in, folder_archives, inputs,
    selected_archives,
)

STATUSES = {
    "confirmed": "공식 이름 확인", "partial": "일부 확인",
    "unavailable": "조회 불가", "no_code": "품번 없음 · 건너뜀",
}


class CodeChecker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PlayDock — DLsite 품번 확인기 (API 키 불필요)")
        self.geometry("1100x710")
        self.minsize(830, 520)
        self.queue: Queue = Queue()
        self.cancel = Event()
        self.busy = False
        self.files: list[str] = []
        self.results: list[Result] = []
        self.item_urls: dict[str, str] = {}
        self.item_details: dict[str, str] = {}

        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="PlayDock — DLsite 품번 확인기",
                  font=("맑은 고딕", 17, "bold")).pack(anchor="w")
        ttk.Label(root, text="RJ·VJ·BJ·EJ 품번만 직접 조회합니다. 제목 검색·DDGS·Bing RSS는 사용하지 않습니다.").pack(
            anchor="w", pady=(4, 3))
        ttk.Label(root, text="압축파일은 열지 않고 이름만 읽습니다. 품번이 없는 파일은 인터넷 검색 없이 건너뜁니다.",
                  foreground="#555").pack(anchor="w", pady=(0, 10))

        ttk.Label(root, text="품번 직접 입력 (한 줄에 하나, 복수 입력 가능) 또는 품번이 포함된 파일명").pack(anchor="w")
        self.input = tk.Text(root, height=4, undo=True, wrap="none")
        self.input.pack(fill="x", pady=(3, 8))

        files_bar = ttk.Frame(root)
        files_bar.pack(fill="x", pady=(0, 4))
        self.pick_files = ttk.Button(files_bar, text="압축파일 선택",
                                     command=self.choose_files)
        self.pick_files.pack(side="left")
        self.pick_folder = ttk.Button(files_bar, text="폴더의 압축파일 선택",
                                      command=self.choose_folder)
        self.pick_folder.pack(side="left", padx=6)
        self.remove_files = ttk.Button(files_bar, text="선택 파일 제거",
                                       command=self.remove_selected)
        self.remove_files.pack(side="left")
        self.filecount = tk.StringVar(value="선택한 파일: 0개")
        ttk.Label(files_bar, textvariable=self.filecount).pack(side="right")
        self.filelist = tk.Listbox(root, height=4, selectmode="extended",
                                   exportselection=False)
        self.filelist.pack(fill="x", pady=(0, 7))

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0, 6))
        self.start = ttk.Button(controls, text="품번 확인 시작", command=self.start_check)
        self.start.pack(side="left")
        self.stop = ttk.Button(controls, text="중단", command=self.cancel.set, state="disabled")
        self.stop.pack(side="left", padx=6)
        self.clear = ttk.Button(controls, text="입력 지우기", command=self.clear_inputs)
        self.clear.pack(side="left", padx=6)
        self.csvbtn = ttk.Button(controls, text="CSV 저장", command=self.save_csv, state="disabled")
        self.csvbtn.pack(side="right")
        self.jsonbtn = ttk.Button(controls, text="JSON 저장", command=self.save_json, state="disabled")
        self.jsonbtn.pack(side="right", padx=6)

        self.progress = ttk.Progressbar(root, maximum=100, mode="determinate")
        self.progress.pack(fill="x", pady=(2, 5))
        self.status = tk.StringVar(value="압축파일을 선택하거나 품번을 입력하세요.")
        ttk.Label(root, textvariable=self.status).pack(anchor="w", pady=(0, 6))

        columns = ("file", "status", "code", "title", "source")
        self.table = ttk.Treeview(root, columns=columns, show="headings",
                                  selectmode="browse")
        for col, name, width in (
            ("file", "입력 파일명 / 품번", 260),
            ("status", "처리 상태", 150),
            ("code", "품번", 140),
            ("title", "DLsite 공식 작품명", 410),
            ("source", "확인 경로", 130),
        ):
            self.table.heading(col, text=name)
            self.table.column(col, width=width, minwidth=80)
        area = ttk.Frame(root)
        area.pack(fill="both", expand=True)
        self.table.pack(in_=area, side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(area, orient="vertical", command=self.table.yview)
        scrollbar.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind("<<TreeviewSelect>>", self.on_select)
        self.table.bind("<Double-1>", self.open_official)

        ttk.Label(root, text="상세 정보 · 공식 확인된 행을 더블클릭하면 DLsite 페이지로 이동").pack(
            anchor="w", pady=(8, 2))
        self.detail = tk.Text(root, height=5, state="disabled", wrap="word")
        self.detail.pack(fill="x")
        self.after(100, self.poll)

    def choose_files(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(
            title="품번을 확인할 압축파일 선택",
            filetypes=[("게임 압축파일", "*.zip *.7z *.rar")])
        self.append_files(selected_archives(paths))

    def choose_folder(self):
        if self.busy:
            return
        directory = filedialog.askdirectory(title="압축파일이 있는 폴더 선택")
        if directory:
            try:
                names = folder_archives(directory)
            except OSError as exc:
                messagebox.showerror("폴더 읽기 오류", str(exc))
                return
            if not names:
                messagebox.showinfo("압축파일 없음", "폴더 바로 아래에 ZIP/7z/RAR이 없습니다.")
                return
            self.append_files(names)

    def append_files(self, names):
        if self.busy:
            return
        if len(self.files) + len(names) > MAX_BATCH:
            messagebox.showwarning("선택 제한", f"최대 {MAX_BATCH}개까지 선택할 수 있습니다.")
            return
        for name in names:
            self.files.append(name)
            self.filelist.insert("end", name)
        self.filecount.set(f"선택한 파일: {len(self.files)}개")

    def remove_selected(self):
        if self.busy:
            return
        for index in reversed(self.filelist.curselection()):
            self.filelist.delete(index)
            del self.files[index]
        self.filecount.set(f"선택한 파일: {len(self.files)}개")

    def clear_inputs(self):
        if self.busy:
            return
        self.input.delete("1.0", "end")
        self.filelist.delete(0, "end")
        self.files.clear()
        self.filecount.set("선택한 파일: 0개")

    def start_check(self):
        if self.busy:
            return
        try:
            items = inputs(self.input.get("1.0", "end"), self.files)
        except ValueError as exc:
            messagebox.showwarning("입력 제한", str(exc))
            return
        if not items:
            messagebox.showwarning("입력 없음", "품번을 입력하거나 압축파일을 선택하세요.")
            return
        self.results.clear()
        self.item_urls.clear()
        self.item_details.clear()
        for row in self.table.get_children():
            self.table.delete(row)
        self.progress.configure(value=0)
        self.cancel.clear()
        self.busy = True
        for btn in (self.pick_files, self.pick_folder, self.remove_files, self.clear, self.start):
            btn.configure(state="disabled")
        self.stop.configure(state="normal")
        self.jsonbtn.configure(state="disabled")
        self.csvbtn.configure(state="disabled")
        Thread(target=self.worker, args=(items,), daemon=True).start()

    def worker(self, items):
        cache: dict[str, Work] = {}
        for i, item in enumerate(items):
            if self.cancel.is_set():
                break
            try:
                result = check(item, cache=cache)
            except Exception as exc:
                result = Result(item.label, item.origin, "unavailable",
                                warnings=(f"조회 중 예외: {type(exc).__name__}",))
            self.queue.put(("result", result, i + 1, len(items)))
        self.queue.put(("done",))

    def poll(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item[0] == "result":
                    _, result, index, total = item
                    self.results.append(result)
                    self.progress.configure(value=100 * index / total)
                    self.status.set(f"{index}/{total}개 처리 · {STATUSES[result.status]}")
                    works = result.works or (None,)
                    for work in works:
                        iid = str(len(self.item_urls))
                        url = work.url if work else ""
                        self.item_urls[iid] = url
                        self.item_details[iid] = (
                            f"입력: {result.query}\n"
                            f"입력 유형: {result.input_origin}\n"
                            f"상태: {STATUSES[result.status]}\n"
                            + (f"품번: {work.code}\n공식 작품명: {work.title or '(확인 불가)'}\n"
                               f"공식 페이지: {work.url or '(확인 불가)'}\n" if work else "")
                            + ("\n".join(result.warnings) if result.warnings else "")
                        )
                        self.table.insert("", "end", iid=iid, values=(
                            result.query, STATUSES[result.status],
                            work.code if work else "-", work.title if work else "-",
                            "DLsite 공식 HTML" if work and work.status == "verified" else "-",
                        ))
                elif item[0] == "done":
                    self.busy = False
                    for btn in (self.pick_files, self.pick_folder, self.remove_files, self.clear, self.start):
                        btn.configure(state="normal")
                    self.stop.configure(state="disabled")
                    self.jsonbtn.configure(state="normal" if self.results else "disabled")
                    self.csvbtn.configure(state="normal" if self.results else "disabled")
                    total = len(self.results)
                    verified = sum(r.status == "confirmed" for r in self.results)
                    missing = sum(r.status == "no_code" for r in self.results)
                    self.status.set(f"완료 {total}개 · 공식 확인 {verified}개 · 품번 없어 건너뜀 {missing}개"
                                    + (" · 사용자가 중단함" if self.cancel.is_set() else ""))
        except Empty:
            pass
        self.after(100, self.poll)

    def on_select(self, _event=None):
        chosen = self.table.selection()
        if not chosen:
            return
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", self.item_details.get(chosen[0], ""))
        self.detail.configure(state="disabled")

    def open_official(self, _event=None):
        chosen = self.table.selection()
        if chosen and self.item_urls.get(chosen[0], "").startswith("https://www.dlsite.com/"):
            webbrowser.open(self.item_urls[chosen[0]])

    def save_json(self):
        if not self.results:
            return
        path = filedialog.asksaveasfilename(
            title="품번 조회 결과 저장", defaultextension=".json",
            initialfile="PlayDock_DLsite_Code_Results.json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        obj = {"program": "PlayDock DLsite Code Checker", "mode": "code_only",
               "created_at_local": datetime.now().astimezone().isoformat(),
               "api_used": False, "archive_contents_inspected": False,
               "results": [r.to_dict() for r in self.results]}
        try:
            Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))

    def save_csv(self):
        if not self.results:
            return
        path = filedialog.asksaveasfilename(
            title="품번 조회 결과 CSV", defaultextension=".csv",
            initialfile="PlayDock_DLsite_Code_Results.csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("파일명/입력", "입력 유형", "상태", "품번", "공식 작품명",
                                 "DLsite URL", "세부 상태", "경고"))
                for result in self.results:
                    for work in result.works or (None,):
                        writer.writerow((
                            result.query, result.input_origin, result.status,
                            work.code if work else "",
                            work.title if work else "", work.url if work else "",
                            work.status if work else "",
                            " / ".join(result.warnings),
                        ))
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))


def main():
    if "--self-test" in sys.argv:
        from experiments.dlsite_detector.code_only import InputItem
        assert codes_in("foo [RJ123456].zip") == ("RJ123456",)
        assert check(InputItem("missing.zip", "archive")).status == "no_code"
        print("PlayDock code-only self-test: PASS")
        return
    app = CodeChecker()
    app.mainloop()
