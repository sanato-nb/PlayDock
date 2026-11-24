"""Minimal independent PlayDock excluded-game renamer (Tkinter, no AI API)."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from experiments.dlsite_detector.rename_companion import (
    ReviewRow, load_review, manual_rows, write_manual_csv,
)
from experiments.dlsite_detector.research_handoff import (
    VerifiedSuggestion, default_journal, reverify, safe_rename, undo_last,
)

STATUS = {
    "claimed_confirmed": "AI 공식 확인 제안",
    "candidate": "후보 · 수동 확인",
    "identity_ambiguous": "DLC/합본 · 수동 확인",
    "unknown": "미확인 · 수동 검색",
    "invalid": "입력 오류 · 수동 확인",
}
APPROVAL_GUIDE = (
    "정식 품번이 존재한다고 해서 로컬 압축파일도 동일 게임인 것은 아닙니다.\n"
    "한국어 번역명·일본어 원제·제작사·시리즈 번호·본편/DLC 구분을 직접 확인하세요.\n"
    "확인할 수 없으면 변경하지 않고 [수동 처리 목록 저장]으로 남기세요."
)


class SimpleRenamer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PlayDock — 제외 게임 파일명 변경기")
        self.geometry("1210x735")
        self.minsize(910, 570)
        self.scan_file: Path | None = None
        self.ai_file: Path | None = None
        self.rows: list[ReviewRow] = []
        self.warnings: list[str] = []
        self.files: dict[str, list[Path]] = {}
        self.verified: dict[int, VerifiedSuggestion] = {}
        self.applied: set[int] = set()
        self.queue: Queue = Queue()
        self.working = False
        self.build()
        self.after(120, self.poll)

    def build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="PlayDock · 제외 게임 파일명 변경기",
                  font=("맑은 고딕", 17, "bold")).pack(anchor="w")
        ttk.Label(root, text="검사 실패 목록 + AI 조사 결과를 가져와서 공식 품번 재확인 → 미리보기 → 승인 후 이름 변경",
                  foreground="#555").pack(anchor="w", pady=(4, 10))
        line = ttk.Frame(root)
        line.pack(fill="x", pady=(0, 6))
        ttk.Button(line, text="1. 제외 목록 JSON", command=self.pick_scan).pack(side="left")
        self.scan_label = ttk.Label(line, text="선택하지 않음")
        self.scan_label.pack(side="left", padx=(5, 15))
        ttk.Button(line, text="2. AI 조사 결과 JSON", command=self.pick_ai).pack(side="left")
        self.ai_label = ttk.Label(line, text="선택하지 않음")
        self.ai_label.pack(side="left", padx=5)
        row = ttk.Frame(root)
        row.pack(fill="x", pady=(0, 6))
        self.load_button = ttk.Button(row, text="3. 두 JSON 대조하여 목록 표시",
                                      command=self.load, state="disabled")
        self.load_button.pack(side="left")
        ttk.Button(row, text="4. 실제 압축파일 선택",
                   command=self.choose_files).pack(side="left", padx=(7, 0))
        ttk.Button(row, text="압축파일 폴더 선택", command=self.choose_folder).pack(side="left", padx=5)
        ttk.Button(row, text="원상복구", command=self.undo).pack(side="right")

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(0, 8))
        self.verify_button = ttk.Button(actions, text="5. 공식 품번 재확인 (선택/전체)",
                                        command=self.verify, state="disabled")
        self.verify_button.pack(side="left")
        self.rename_button = ttk.Button(actions, text="6. 선택한 파일명 변경 승인",
                                        command=self.rename, state="disabled")
        self.rename_button.pack(side="left", padx=6)
        self.manual_button = ttk.Button(actions, text="7. 못 찾은 게임 · 수동 처리 목록 저장",
                                        command=self.export_manual, state="disabled")
        self.manual_button.pack(side="right")

        cols = ("old", "ai", "code", "official", "linked", "new")
        self.table = ttk.Treeview(root, columns=cols, show="headings", selectmode="extended")
        for key, label, width in (
            ("old", "기존 압축파일명", 250),
            ("ai", "AI 조사 상태", 125),
            ("code", "후보 품번 / App ID", 135),
            ("official", "실제 공식 재조회", 140),
            ("linked", "로컬 파일 연결", 110),
            ("new", "미리보기: 변경할 이름", 345),
        ):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=80)
        panel = ttk.Frame(root)
        panel.pack(fill="both", expand=True)
        self.table.pack(in_=panel, side="left", fill="both", expand=True)
        sc = ttk.Scrollbar(panel, orient="vertical", command=self.table.yview)
        sc.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=sc.set)
        self.table.bind("<<TreeviewSelect>>", self.on_select)
        ttk.Label(root, text="선택한 항목 상세 · '공식 재조회 성공'이어도 동일 작품인지 최종 확인 후 변경하세요").pack(anchor="w", pady=(8, 2))
        self.details = tk.Text(root, height=6, state="disabled", wrap="word")
        self.details.pack(fill="x")
        self.info = tk.StringVar(value="제외 목록 JSON 및 AI 조사 결과 JSON을 선택하세요.")
        ttk.Label(root, textvariable=self.info).pack(anchor="w", pady=(6, 0))

    def pick_scan(self):
        file = filedialog.askopenfilename(
            title="PlayDock 검사 결과 또는 제외 목록 JSON 선택",
            filetypes=[("JSON", "*.json")])
        if file:
            self.scan_file = Path(file)
            self.scan_label.configure(text=self.scan_file.name)
            self.load_button.configure(state="normal" if self.ai_file else "disabled")

    def pick_ai(self):
        file = filedialog.askopenfilename(
            title="AI 조사 결과 JSON 선택 (playdock-ai-review-v1)",
            filetypes=[("JSON", "*.json")])
        if file:
            self.ai_file = Path(file)
            self.ai_label.configure(text=self.ai_file.name)
            self.load_button.configure(state="normal" if self.scan_file else "disabled")

    def load(self):
        if self.working or not self.scan_file or not self.ai_file:
            return
        try:
            rows, errors = load_review(self.scan_file, self.ai_file)
        except (ValueError, OSError, UnicodeError) as exc:
            messagebox.showerror("JSON 불러오기 실패", str(exc), parent=self)
            return
        self.rows, self.warnings = rows, errors
        self.verified.clear()
        self.applied.clear()
        for iid in self.table.get_children():
            self.table.delete(iid)
        for i in range(len(rows)):
            self.table.insert("", "end", iid=str(i))
            self.refresh(i)
        self.verify_button.configure(state="normal")
        self.rename_button.configure(state="normal")
        self.manual_button.configure(state="normal")
        hist = Counter(row.ai_status for row in rows)
        self.info.set(
            f"제외 {len(rows)}개 · 일반 확인 제안 {hist['claimed_confirmed']} · "
            f"후보 {hist['candidate']} · DLC/합본 수동 {hist['identity_ambiguous']} · "
            f"미확인 {hist['unknown']} · 오류 {hist['invalid']} · 실제 이름 변경 전"
        )
        if errors:
            messagebox.showwarning("AI JSON 확인 필요",
                                   "\n".join(errors[:10]), parent=self)

    def choose_files(self):
        if self.working:
            return
        selection = filedialog.askopenfilenames(
            title="실제 ZIP/7z/RAR 게임 압축파일을 선택하세요",
            filetypes=[("압축파일", "*.zip *.7z *.rar")])
        self.add_files(selection)

    def choose_folder(self):
        if self.working:
            return
        folder = filedialog.askdirectory(title="게임 압축파일 폴더 선택")
        if not folder:
            return
        try:
            paths = [p for p in Path(folder).iterdir() if p.is_file()
                     and p.suffix.lower() in (".zip", ".7z", ".rar")]
        except OSError as exc:
            messagebox.showerror("폴더 접근 실패", str(exc), parent=self)
            return
        self.add_files(paths)

    def add_files(self, paths):
        known = {str(path) for paths in self.files.values() for path in paths}
        count = 0
        for raw in paths:
            path = Path(raw)
            if str(path) in known or not path.is_file() or path.is_symlink():
                continue
            if path.suffix.casefold() not in (".zip", ".7z", ".rar"):
                continue
            self.files.setdefault(path.name, []).append(path)
            known.add(str(path))
            count += 1
        for i in range(len(self.rows)):
            self.refresh(i)
        self.info.set(f"실제 압축파일 {count}개 추가 연결 · 파일 내용은 읽지 않음")

    def connected(self, name):
        return [p for p in self.files.get(name, []) if p.is_file() and not p.is_symlink()]

    def refresh(self, index):
        row = self.rows[index]
        check = self.verified.get(index)
        official = ("변경 완료" if index in self.applied else
                    "공식 재조회 성공" if check and check.verified else
                    "공식 재조회 실패" if check else
                    "재조회 전" if row.ai_status == "claimed_confirmed" else
                    "사용자 수동 확인")
        n = len(self.connected(row.filename))
        linked = ("미연결" if n == 0 else "연결됨" if n == 1 else "동명이인 파일 중복")
        s = row.suggestion
        self.table.item(str(index), values=(
            row.filename, STATUS.get(row.ai_status, row.ai_status),
            (s.store.upper() + " " + s.code) if s else "-",
            official, linked, row.proposed,
        ))

    def on_select(self, _=None):
        selection = self.table.selection()
        if not selection:
            return
        i = int(selection[0])
        row = self.rows[i]
        s = row.suggestion
        check = self.verified.get(i)
        lines = [
            "원본 압축파일: " + row.filename,
            "AI 조사 상태: " + STATUS.get(row.ai_status, row.ai_status),
            "기존 제외 사유: " + row.exclusion_reason,
            "AI 후보: " + ((s.store + " " + s.code) if s else "없음"),
            "AI 공식 URL: " + (s.official_url if s else "없음"),
            "조사 근거: " + (row.note or "없음"),
            "공식 사이트 재조회: " + (check.reason if check else "미실시"),
            "로컬 파일 연결 수: " + str(len(self.connected(row.filename))),
            "변경 미리보기: " + row.proposed,
            "",
            APPROVAL_GUIDE,
        ]
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")

    def verify(self):
        if self.working or not self.rows:
            return
        selections = [int(i) for i in self.table.selection()]
        target = selections or list(range(len(self.rows)))
        # Candidate/unknown remains manual; do not request official HTTP
        # or accept a merely related product as an automatic match.
        target = [i for i in target if self.rows[i].ai_status == "claimed_confirmed"
                  and self.rows[i].suggestion is not None
                  and i not in self.applied]
        if not target:
            messagebox.showinfo("재조회 대상 없음",
                                "AI에서 '공식 확인'으로 제안한 항목이 없습니다.\n"
                                "후보·미확인은 수동 확인 목록으로 내보내세요.", parent=self)
            return
        self.working = True
        self.verify_button.configure(state="disabled")
        self.rename_button.configure(state="disabled")
        self.info.set(f"공식 DLsite/Steam 재조회 중: {len(target)}개")
        Thread(target=self.worker, args=(target,), daemon=True).start()

    def worker(self, items):
        for i in items:
            try:
                result = reverify(self.rows[i].suggestion)
            except Exception as exc:
                result = VerifiedSuggestion(
                    self.rows[i].suggestion, False,
                    reason=f"공식 재검증 중 오류: {type(exc).__name__}")
            self.queue.put(("checked", i, result))
        self.queue.put(("done",))

    def poll(self):
        try:
            while True:
                action = self.queue.get_nowait()
                if action[0] == "checked":
                    _, i, check = action
                    self.verified[i] = check
                    self.refresh(i)
                    self.on_select()
                elif action[0] == "done":
                    self.working = False
                    self.verify_button.configure(state="normal")
                    self.rename_button.configure(state="normal")
                    good = {self.rows[i].filename for i, v in self.verified.items()
                            if v.verified}
                    self.info.set(f"공식 재확인 성공 {len(good)}개 · 수동 확인 필요 "
                                  f"{len(manual_rows(self.rows, good))}개 "
                                  "· 실제 파일명 변경은 별도 승인 필요")
        except Empty:
            pass
        if self.winfo_exists():
            self.after(120, self.poll)

    def rename(self):
        if self.working:
            return
        selected = [int(i) for i in self.table.selection()]
        if not selected:
            messagebox.showinfo("변경 대상 선택", "변경할 행을 선택하세요.", parent=self)
            return
        prepared = []
        skipped = []
        for i in selected:
            row = self.rows[i]
            verify = self.verified.get(i)
            paths = self.connected(row.filename)
            if i in self.applied:
                skipped.append(f"{row.filename}: 이미 변경됨")
            elif not verify or not verify.verified:
                skipped.append(f"{row.filename}: 공식 재확인 실패/미실시")
            elif len(paths) != 1:
                skipped.append(f"{row.filename}: 로컬 파일 미연결 또는 같은 이름 여러 개")
            elif paths[0].name == row.proposed:
                skipped.append(f"{row.filename}: 이름 변경 불필요")
            else:
                prepared.append((i, paths[0], row.proposed))
        if skipped:
            messagebox.showwarning("변경 제외 사유", "\n".join(skipped[:12]), parent=self)
        if not prepared:
            return
        previews = "\n".join(f"{src.name}\n  → {dest}"
                             for _, src, dest in prepared[:10])
        if len(prepared) > 10:
            previews += f"\n외 {len(prepared)-10}건"
        if not messagebox.askyesno(
            "파일명 변경 최종 승인",
            "다음 파일들의 이름만 바꿉니다. 압축 내용은 읽거나 변경하지 않습니다.\n"
            "AI가 판단한 파일 동일성은 사용자가 직접 확인해야 합니다.\n\n"
            + previews + "\n\n실제로 적용할까요?",
            parent=self):
            return
        success, failed = 0, []
        for i, src, new_name in prepared:
            try:
                path, _ = safe_rename(src, new_name, default_journal())
                self.files[src.name] = [p for p in self.files.get(src.name, [])
                                        if p != src]
                self.files.setdefault(path.name, []).append(path)
                self.applied.add(i)
                self.refresh(i)
                success += 1
            except (OSError, ValueError) as exc:
                failed.append(f"{src.name}: {exc}")
        self.info.set(f"실제 파일명 변경 {success}개 · 실패 {len(failed)}개")
        if failed:
            messagebox.showwarning("일부 변경 불가", "\n".join(failed[:12]), parent=self)

    def undo(self):
        if self.working:
            return
        if not messagebox.askyesno("최근 변경 원상복구",
                                   "가장 최근 파일명 변경 1건을 되돌리겠습니까?\n"
                                   "기존 이름에 파일이 있으면 복구하지 않습니다.", parent=self):
            return
        try:
            after, before = undo_last(default_journal())
        except (OSError, ValueError) as exc:
            messagebox.showerror("원상복구 실패", str(exc), parent=self)
            return
        self.files[after.name] = [p for p in self.files.get(after.name, [])
                                  if p != after]
        self.files.setdefault(before.name, []).append(before)
        for i, row in enumerate(self.rows):
            if row.filename == before.name:
                self.applied.discard(i)
                self.refresh(i)
        self.info.set("원상복구 완료: " + before.name)

    def export_manual(self):
        if not self.rows:
            return
        dest = filedialog.asksaveasfilename(
            title="아직 못 찾은 게임 수동 처리 목록",
            initialfile="PlayDock_Manual_Review.csv",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not dest:
            return
        good = {self.rows[i].filename for i, v in self.verified.items()
                if v.verified}
        try:
            count = write_manual_csv(dest, self.rows, good)
        except OSError as exc:
            messagebox.showerror("수동 목록 저장 실패", str(exc), parent=self)
            return
        messagebox.showinfo(
            "수동 처리 안내",
            f"공식 품번을 재확인하지 못한 {count}개를 CSV로 저장했습니다.\n\n"
            "1. 파일명을 이용해 DLsite 또는 Steam 공식 사이트를 직접 검색하세요.\n"
            "2. 동일 게임인지 제작사·시리즈 번호·본편/DLC를 확인하세요.\n"
            "3. 찾으면 탐색기에서 파일명에 [RJ번호] 또는 [Steam 숫자]를 직접 추가하세요.\n"
            "4. 찾지 못하면 잘못된 번호를 붙이지 말고 파일명 그대로 보존하세요.\n\n"
            "프로그램은 확인되지 않은 게임을 자동 변경하지 않습니다.",
            parent=self,
        )


def main():
    if "--self-test" in __import__("sys").argv:
        from experiments.dlsite_detector.rename_companion import ReviewRow, manual_rows
        assert len(manual_rows([ReviewRow("a.zip", "unknown", None, "a.zip", "", "")])) == 1
        print("PlayDock standalone rename companion self-test PASS")
        return
    app = SimpleRenamer()
    app.mainloop()


if __name__ == "__main__":
    main()
