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

from experiments.dlsite_detector.research_handoff import (
    research_export, research_prompt, read_ai_response,
    excluded_from_results, load_previous_excluded,
)
from scripts.research_review_window import ResearchReview

from experiments.dlsite_detector.code_only import (
    MAX_BATCH, Result, Work, check, codes_in, steam_ids_in, folder_archives, inputs,
    selected_archives,
)

STATUSES = {
    "confirmed": "공식 이름 확인", "partial": "일부 확인",
    "excluded": "제외 · 확인되지 않음",
}


class CodeChecker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PlayDock — DLsite 우선 / Steam 품번 확인기")
        self.geometry("1100x710")
        self.minsize(830, 520)
        self.queue: Queue = Queue()
        self.cancel = Event()
        self.busy = False
        self.files: list[str] = []
        # Only stored in memory on the local PC. Never exported or sent to stores/AI.
        self.file_paths: list[Path] = []
        self.results: list[Result] = []
        self.item_urls: dict[str, str] = {}
        self.item_details: dict[str, str] = {}

        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="PlayDock — DLsite → Steam 식별번호 확인기",
                  font=("맑은 고딕", 17, "bold")).pack(anchor="w")
        ttk.Label(root, text="DLsite 품번 먼저 확인 → 실패하거나 없으면 Steam App ID 확인 → 둘 다 실패하면 제외.").pack(
            anchor="w", pady=(4, 3))
        ttk.Label(root, text="RJ·VJ·BJ·EJ / Steam 1091500 / AppID=1091500 · 제목 검색과 압축파일 내부 검사는 하지 않습니다.",
                  foreground="#555").pack(anchor="w", pady=(0, 10))

        ttk.Label(root, text="DLsite 품번 또는 Steam App ID 직접 입력 (한 줄에 하나) / 식별번호가 포함된 파일명").pack(anchor="w")
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
        self.start = ttk.Button(controls, text="DLsite → Steam 확인 시작", command=self.start_check)
        self.start.pack(side="left")
        self.stop = ttk.Button(controls, text="중단", command=self.cancel.set, state="disabled")
        self.stop.pack(side="left", padx=6)
        self.clear = ttk.Button(controls, text="입력 지우기", command=self.clear_inputs)
        self.clear.pack(side="left", padx=6)
        self.csvbtn = ttk.Button(controls, text="CSV 저장", command=self.save_csv, state="disabled")
        self.csvbtn.pack(side="right")

        research = ttk.Frame(root)
        research.pack(fill="x", pady=(0, 6))
        self.load_scan_btn = ttk.Button(
            research, text="이전 검사 JSON에서 제외 목록 가져오기", command=self.load_previous_scan)
        self.load_scan_btn.pack(side="left")
        self.export_ai_btn = ttk.Button(
            research, text="제외 목록 + AI 조사 프롬프트 내보내기",
            command=self.export_research, state="disabled")
        self.export_ai_btn.pack(side="left", padx=5)
        self.copy_prompt_btn = ttk.Button(
            research, text="AI 조사 프롬프트 복사", command=self.copy_research_prompt)
        self.copy_prompt_btn.pack(side="left")
        self.import_ai_btn = ttk.Button(
            research, text="AI 조사 결과 JSON 가져오기 · 이름 변경 검토",
            command=self.import_research)
        self.import_ai_btn.pack(side="right")
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
            ("title", "공식 작품명 (DLsite / Steam)", 410),
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

        ttk.Label(root, text="상세 정보 · 확인된 행 더블클릭 시 해당 공식 스토어 페이지로 이동").pack(
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
        self.append_files(paths)

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
            self.append_files([str(Path(directory) / name) for name in names])

    def append_files(self, paths):
        """Only basename is used for lookup; absolute paths stay in this GUI."""
        if self.busy:
            return
        selected = [(Path(p), Path(p).name) for p in paths
                    if Path(p).is_file() and Path(p).suffix.casefold() in (".zip", ".7z", ".rar")]
        if len(self.files) + len(selected) > MAX_BATCH:
            messagebox.showwarning("선택 제한", f"최대 {MAX_BATCH}개까지 선택할 수 있습니다.")
            return
        known = set(str(p) for p in self.file_paths)
        for path, name in selected:
            if str(path) in known:
                continue
            self.files.append(name)
            self.file_paths.append(path)
            self.filelist.insert("end", name)
            known.add(str(path))
        self.filecount.set(f"선택한 파일: {len(self.files)}개")

    def local_path_changed(self, original: Path, changed: Path):
        """Update local file binding without changing exported research history."""
        for i, path in enumerate(self.file_paths):
            if Path(path) == Path(original):
                self.file_paths[i] = Path(changed)
                self.files[i] = Path(changed).name
                self.filelist.delete(i)
                self.filelist.insert(i, self.files[i])
        self.filecount.set(f"선택한 파일: {len(self.files)}개")

    def remove_selected(self):
        if self.busy:
            return
        for index in reversed(self.filelist.curselection()):
            self.filelist.delete(index)
            del self.files[index]
            del self.file_paths[index]
        self.filecount.set(f"선택한 파일: {len(self.files)}개")

    def clear_inputs(self):
        if self.busy:
            return
        self.input.delete("1.0", "end")
        self.filelist.delete(0, "end")
        self.files.clear()
        self.file_paths.clear()
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
        self.export_ai_btn.configure(state="disabled")
        self.load_scan_btn.configure(state="disabled")
        self.import_ai_btn.configure(state="disabled")
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
                    self.status.set(f"{index}/{total}개 처리 · {STATUSES.get(result.status, result.status)}")
                    works = result.works or (None,)
                    for work in works:
                        iid = str(len(self.item_urls))
                        url = work.url if work else ""
                        self.item_urls[iid] = url
                        self.item_details[iid] = (
                            f"입력: {result.query}\n"
                            f"입력 유형: {result.input_origin}\n"
                            f"상태: {STATUSES.get(result.status, result.status)}\n"
                            f"우선 확인한 스토어: {result.selected_store or '없음'}\n"
                            f"조회 순서: {', '.join(result.attempted_stores) or '식별번호 없음'}\n"
                            + (f"스토어: {work.store}\n식별번호: {work.code}\n공식 작품명: {work.title or '(확인 불가)'}\n"
                               f"공식 페이지: {work.url or '(확인 불가)'}\n" if work else "")
                            + ("\n".join(result.warnings) if result.warnings else "")
                        )
                        self.table.insert("", "end", iid=iid, values=(
                            result.query, (
                                f"{work.store.upper()} 확인" if work and work.status == "verified"
                                else f"{work.store.upper()} 조회 불가" if work
                                else STATUSES.get(result.status, result.status)),
                            work.code if work else "-", work.title if work else "-",
                            (work.store.upper() + " 공식 HTML") if work and work.status == "verified" else "-",
                        ))
                elif item[0] == "done":
                    self.busy = False
                    for btn in (self.pick_files, self.pick_folder, self.remove_files, self.clear, self.start):
                        btn.configure(state="normal")
                    self.stop.configure(state="disabled")
                    self.jsonbtn.configure(state="normal" if self.results else "disabled")
                    self.csvbtn.configure(state="normal" if self.results else "disabled")
                    self.export_ai_btn.configure(state="normal" if excluded_from_results(self.results) else "disabled")
                    self.load_scan_btn.configure(state="normal")
                    self.import_ai_btn.configure(state="normal")
                    total = len(self.results)
                    verified = sum(r.status in ("confirmed", "partial") for r in self.results)
                    excluded = sum(r.status == "excluded" for r in self.results)
                    self.status.set(f"완료 {total}개 · 공식 확인 {verified}개 · 제외 {excluded}개"
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
        if chosen:
            url = self.item_urls.get(chosen[0], "")
            if (url.startswith("https://www.dlsite.com/") or
                    url.startswith("https://store.steampowered.com/app/")):
                webbrowser.open(url)

    def load_previous_scan(self):
        """Load excluded rows from old v8/v9 JSON; does NOT bind local file paths."""
        if self.busy:
            return
        path = filedialog.askopenfilename(
            title="이전 PlayDock 검사 JSON 선택",
            filetypes=[("PlayDock JSON", "*.json")])
        if not path:
            return
        try:
            rows = load_previous_excluded(path)
        except (ValueError, OSError, UnicodeError) as exc:
            messagebox.showerror("불러오기 실패", str(exc))
            return
        if not rows:
            messagebox.showinfo("제외 목록 없음", "검사 결과에 제외된 파일이 없습니다.")
            return
        self.results = rows
        self.item_urls.clear()
        self.item_details.clear()
        for old in self.table.get_children():
            self.table.delete(old)
        for i, r in enumerate(rows):
            key = str(i)
            self.item_urls[key] = ""
            self.item_details[key] = (f"입력: {r.query}\n상태: 제외\n"
                                      "이전 JSON에서 파일명만 가져왔습니다.\n"
                                      "실제 파일명 변경을 하려면 압축파일을 별도로 연결하세요.")
            self.table.insert("", "end", iid=key,
                              values=(r.query, "제외 · 조사 대상", "-", "-", "-"))
        self.export_ai_btn.configure(state="normal")
        self.jsonbtn.configure(state="normal")
        self.csvbtn.configure(state="normal")
        self.status.set(f"이전 JSON에서 제외 목록 {len(rows)}개 불러옴 · 로컬 파일은 별도 연결 필요")

    def copy_research_prompt(self):
        prompt = research_prompt()
        self.clipboard_clear()
        self.clipboard_append(prompt)
        self.update()
        self.status.set("AI 조사 프롬프트 복사 완료 · 제외 목록 JSON도 함께 첨부하세요")

    def export_research(self):
        """Write only excluded filenames and investigation instructions."""
        excluded = excluded_from_results(self.results)
        if not excluded:
            messagebox.showinfo("제외 목록 없음",
                                "먼저 검사를 실행하거나 이전 검사 JSON을 가져오세요.")
            return
        chosen = filedialog.asksaveasfilename(
            title="AI에 전달할 제외 목록 JSON 저장", defaultextension=".json",
            initialfile="PlayDock_Excluded_Research.json",
            filetypes=[("JSON", "*.json")])
        if not chosen:
            return
        path = Path(chosen)
        prompt_path = path.with_name(path.stem + "_AI_Prompt.txt")
        if (prompt_path.exists() and not messagebox.askyesno(
                "프롬프트 파일 덮어쓰기",
                f"{prompt_path.name} 파일이 존재합니다. 덮어쓸까요?")):
            return
        try:
            path.write_text(json.dumps(research_export(self.results),
                                       ensure_ascii=False, indent=2),
                            encoding="utf-8")
            prompt_path.write_text(research_prompt(), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("내보내기 오류", str(exc))
            return
        self.status.set(f"AI 조사자료 내보냄: 제외 {len(excluded)}개 · "
                        f"{path.name} / {prompt_path.name}")
        messagebox.showinfo(
            "AI 조사자료 저장 완료",
            "제외 목록 JSON과 AI 조사 프롬프트 TXT 파일을 저장했습니다.\n"
            "두 파일을 AI에 제공하고, AI가 만든 결과 JSON을 다시 가져오세요.\n"
            "실제 파일 경로는 어느 파일에도 포함되지 않습니다.")

    def import_research(self):
        if self.busy:
            return
        allowed = [r["original_filename"] for r in excluded_from_results(self.results)]
        if not allowed:
            messagebox.showinfo("제외 목록 없음",
                                "먼저 검사하거나 이전 검사 JSON에서 제외 목록을 가져오세요.")
            return
        path = filedialog.askopenfilename(
            title="AI가 작성한 조사 결과 JSON 선택",
            filetypes=[("AI 조사 결과 JSON", "*.json")])
        if not path:
            return
        try:
            suggestions, errors = read_ai_response(path, allowed)
        except (ValueError, OSError, UnicodeError) as exc:
            messagebox.showerror("AI JSON 검증 실패", str(exc))
            return
        if not suggestions:
            messagebox.showinfo(
                "유효한 조사 후보 없음",
                "가져온 JSON에 검사 가능한 공식 식별번호가 없습니다.\n"
                + "\n".join(errors[:6]))
            return
        ResearchReview(self, suggestions, errors)

    def save_json(self):
        if not self.results:
            return
        path = filedialog.asksaveasfilename(
            title="품번 조회 결과 저장", defaultextension=".json",
            initialfile="PlayDock_DLsite_Steam_Results.json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        obj = {"program": "PlayDock DLsite → Steam Code Checker", "mode": "dlsite_steam_code_only",
               "created_at_local": datetime.now().astimezone().isoformat(),
               "api_used": any("steam" in r.attempted_stores for r in self.results),
               "api_key_used": False, "archive_contents_inspected": False,
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
            initialfile="PlayDock_DLsite_Steam_Results.csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("파일명/입력", "입력 유형", "최종 분류", "선택 사이트",
                                 "조회 사이트", "식별번호", "공식 작품명", "공식 URL", "세부 상태", "경고"))
                for result in self.results:
                    for work in result.works or (None,):
                        writer.writerow((
                            result.query, result.input_origin, result.status,
                            result.selected_store,
                            work.store if work else "", work.code if work else "",
                            work.title if work else "", work.url if work else "",
                            work.status if work else "", " / ".join(result.warnings),
                        ))
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))


def main():
    if "--self-test" in sys.argv:
        from experiments.dlsite_detector.code_only import InputItem
        assert codes_in("foo [RJ123456].zip") == ("RJ123456",)
        assert check(InputItem("missing.zip", "archive")).status == "excluded"
        assert steam_ids_in("game [SteamAppID=1091500].zip") == ("1091500",)
        print("PlayDock code-only self-test: PASS")
        return
    app = CodeChecker()
    app.mainloop()
