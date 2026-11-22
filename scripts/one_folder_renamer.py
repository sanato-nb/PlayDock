"""PlayDock: choose one directory, re-verify official IDs, approve, rename.

Works from a user-private PlayDock_Rename_Data.json placed next to the EXE.
The mapping is never included in the public PlayDock GitHub repository.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import csv
import sys
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from experiments.dlsite_detector.folder_rename import (
    DATA_FILENAME, FolderMatch, folder_plan, load_local_mapping, rename_verified,
)
from experiments.dlsite_detector.research_handoff import (
    VerifiedSuggestion, default_journal, reverify, undo_last,
)

STATUS_KO = {
    "ready": "공식 확인 대기",
    "manual": "수동 확인",
    "missing": "선택 폴더에 없음",
    "duplicate": "동일 이름 중복",
    "collision": "파일명 충돌",
}
MANUAL_NOTE = (
    "품번을 끝내 찾지 못했거나 확신이 없으면 파일명은 그대로 두세요.\n"
    "확실한 게임의 경우만 탐색기에서 [RJ품번] 또는 [Steam 숫자]를 직접 추가할 수 있습니다."
)


def companion_location() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / DATA_FILENAME
    return Path.cwd() / DATA_FILENAME


class FolderRenamer(tk.Tk):
    def __init__(self, *, mapping_path: Path | None = None):
        super().__init__()
        self.title("PlayDock — 폴더만 선택하여 게임 파일명 변경")
        self.geometry("1180x675")
        self.minsize(850, 525)
        self.mapping_path = Path(mapping_path) if mapping_path else companion_location()
        self.folder: Path | None = None
        self.rows = []
        self.plan: list[FolderMatch] = []
        self.verified: dict[int, VerifiedSuggestion] = {}
        self.done: set[int] = set()
        self.queue: Queue = Queue()
        self.busy = False
        self.batch = 0
        self.setup()
        try:
            self.rows, warnings = load_local_mapping(self.mapping_path)
            self.info.set(f"조사 결과 준비 완료 · 제외 목록 {len(self.rows)}개 · "
                          "게임 압축파일 폴더만 선택하세요.")
            if warnings:
                self.info.set(self.info.get() + f" · 조사자료 주의 {len(warnings)}건")
        except (OSError, ValueError, UnicodeError) as exc:
            self.info.set(f"조사자료를 읽을 수 없습니다: {exc}")
            self.choose_button.configure(state="disabled")
            self.after(400, lambda: messagebox.showerror(
                "조사자료 파일이 없습니다",
                f"{DATA_FILENAME} 파일을 실행파일과 같은 폴더에 둬야 합니다.\n"
                "제공된 ZIP 전체를 압축 해제해서 실행하세요.\n\n"
                f"자세한 오류: {exc}", parent=self))
        self.after(120, self.poll)

    def setup(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="PlayDock · 게임 파일명 간편 변경",
                  font=("맑은 고딕", 19, "bold")).pack(anchor="w")
        ttk.Label(root, text="압축파일 폴더만 선택하세요. 준비된 조사 결과로 이름 변경 대상을 자동으로 찾아줍니다.",
                  foreground="#555").pack(anchor="w", pady=(4, 12))
        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0, 8))
        self.choose_button = ttk.Button(
            controls, text="📁 게임 압축파일 폴더 선택",
            command=self.choose_folder)
        self.choose_button.pack(side="left")
        self.folder_var = tk.StringVar(value="폴더가 아직 선택되지 않았습니다")
        ttk.Label(controls, textvariable=self.folder_var).pack(
            side="left", padx=12)
        self.progress = ttk.Progressbar(root, orient="horizontal", maximum=100)
        self.progress.pack(fill="x", pady=(0, 6))
        self.info = tk.StringVar(value="조사 결과를 확인하는 중")
        ttk.Label(root, textvariable=self.info).pack(anchor="w", pady=(0, 9))

        bar = ttk.Frame(root)
        bar.pack(fill="x", pady=(0, 7))
        self.rename_button = ttk.Button(
            bar, text="확인된 파일 이름 변경", command=self.apply, state="disabled")
        self.rename_button.pack(side="left")
        self.undo_button = ttk.Button(bar, text="최근 변경 취소", command=self.undo)
        self.undo_button.pack(side="left", padx=(8, 0))
        self.manual_button = ttk.Button(
            bar, text="못 찾은 게임 수동 처리 목록 저장",
            command=self.save_manual, state="disabled")
        self.manual_button.pack(side="right")

        cols = ("original", "id", "status", "new_name")
        self.table = ttk.Treeview(root, columns=cols, show="headings",
                                  selectmode="browse")
        for key, label, width in (
            ("original", "현재 압축파일 이름", 340),
            ("id", "조사된 품번", 150),
            ("status", "확인 결과", 180),
            ("new_name", "바뀔 파일명", 430),
        ):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=85)
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)
        self.table.pack(in_=body, side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.table.yview)
        scrollbar.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind("<<TreeviewSelect>>", self.show_detail)

        ttk.Label(root, text="상세 · 공식 상품번호 확인은 압축파일의 내용까지 증명하지 않으므로 변경 이름을 확인하세요.").pack(
            anchor="w", pady=(10, 3))
        self.detail = tk.Text(root, height=5, state="disabled", wrap="word")
        self.detail.pack(fill="x")

    def choose_folder(self):
        if self.busy:
            return
        path = filedialog.askdirectory(title="게임 ZIP / 7z / RAR이 있는 폴더 선택")
        if not path:
            return
        self.folder = Path(path)
        self.folder_var.set(str(self.folder))
        try:
            self.plan = folder_plan(self.folder, self.rows)
        except (OSError, ValueError) as exc:
            messagebox.showerror("폴더 검사 실패", str(exc), parent=self)
            return
        self.verified.clear()
        self.done.clear()
        self.batch += 1
        for item in self.table.get_children():
            self.table.delete(item)
        for i, row in enumerate(self.plan):
            if row.path is None:
                continue
            self.table.insert("", "end", iid=str(i))
            self.update_row(i)
        ready = sum(x.status == "ready" for x in self.plan)
        manual = sum(x.status in ("manual", "duplicate", "collision") for x in self.plan
                     if x.path or x.status == "duplicate")
        found = sum(x.path is not None or x.status == "duplicate" for x in self.plan)
        self.info.set(f"찾은 압축파일 {found}개 · 공식 재조회 대상 {ready}개 · "
                      f"수동 확인 {manual}개" +
                      (f" · 확인된 품번을 재조회합니다" if ready else " · 파일명 변경 대상 없음"))
        self.manual_button.configure(state="normal")
        self.rename_button.configure(state="disabled")
        self.progress.configure(value=0)
        if ready:
            self.busy = True
            self.choose_button.configure(state="disabled")
            self.batch += 1
            Thread(target=self.worker, args=(self.batch,), daemon=True).start()
        else:
            self.progress.configure(value=100)

    def worker(self, batch: int):
        target = [(i, row) for i, row in enumerate(self.plan)
                  if row.status == "ready"]
        # Parallel checks reduce waiting, without any title/search-engine requests.
        def verify(item):
            i, matched = item
            try:
                proof = reverify(matched.row.suggestion)
            except Exception as exc:
                proof = VerifiedSuggestion(
                    matched.row.suggestion, False,
                    reason=f"공식 확인 중 오류: {type(exc).__name__}")
            return i, proof

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(verify, item) for item in target]
            for future in as_completed(futures):
                i, proof = future.result()
                self.queue.put(("verified", batch, i, proof, len(target)))
        self.queue.put(("done", batch, len(target)))

    def poll(self):
        try:
            while True:
                action = self.queue.get_nowait()
                if action[1] != self.batch:
                    continue
                if action[0] == "verified":
                    _, _, i, proof, total = action
                    self.verified[i] = proof
                    self.progress.configure(value=(100*len(self.verified)/total))
                    self.update_row(i)
                    success = sum(p.verified for p in self.verified.values())
                    self.info.set(f"공식 품번 재조회 {len(self.verified)}/{total} · 성공 {success}")
                elif action[0] == "done":
                    self.busy = False
                    self.choose_button.configure(state="normal")
                    success = sum(p.verified for p in self.verified.values())
                    manual = sum(
                        (item.status != "ready" or
                         not self.verified.get(i) or not self.verified[i].verified)
                        for i, item in enumerate(self.plan)
                        if item.path or item.status == "duplicate")
                    self.info.set(
                        f"공식 조회 성공 {success}개 · 수동 확인 또는 실패 {manual}개 · "
                        "이름 변경 전입니다.")
                    self.rename_button.configure(state="normal" if success else "disabled")
        except Empty:
            pass
        if self.winfo_exists():
            self.after(120, self.poll)

    def status_of(self, i):
        item = self.plan[i]
        if i in self.done:
            return "이름 변경 완료"
        if item.status != "ready":
            return STATUS_KO[item.status]
        proof = self.verified.get(i)
        if proof is None:
            return "공식 재조회 중…"
        return "공식 재확인 성공" if proof.verified else "재조회 실패 · 수동"

    def update_row(self, i):
        item = self.plan[i]
        if item.path is None or not self.table.exists(str(i)):
            return
        s = item.row.suggestion
        code = f"{s.store.upper()} {s.code}" if s else "-"
        self.table.item(str(i), values=(
            item.row.filename, code, self.status_of(i),
            item.row.proposed if item.status == "ready" else "변경하지 않음",
        ))

    def show_detail(self, _event=None):
        sel = self.table.selection()
        if not sel:
            return
        i = int(sel[0])
        item = self.plan[i]
        s = item.row.suggestion
        proof = self.verified.get(i)
        lines = [
            f"선택 파일: {item.row.filename}",
            f"실제 파일 위치: {item.path or '(중복/없음)'}",
            f"확인 상태: {self.status_of(i)}",
            f"조사된 식별번호: {s.store.upper() + ' ' + s.code if s else '(없음)'}",
            f"공식 작품명: {proof.official_title if proof and proof.verified else '(공식 확인 실패/미실시)'}",
            f"변경 예정: {item.row.proposed if item.status == 'ready' else '(변경하지 않음)'}",
            f"메모: {item.row.note or item.detail}",
            "주의: 같은 게임인지 직접 확인하지 못하면 변경 승인하지 마세요.",
        ]
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state="disabled")

    def apply(self):
        if self.busy:
            return
        pending = [(i, item) for i, item in enumerate(self.plan)
                   if (item.status == "ready" and i not in self.done and
                       self.verified.get(i) is not None and self.verified[i].verified)]
        if not pending:
            messagebox.showinfo("변경할 파일 없음",
                                "공식 품번 조회에 성공한 파일이 없습니다.\n"
                                "수동 처리 목록을 저장해 직접 확인하세요.", parent=self)
            return
        preview = "\n".join(f"{x.row.filename}\n  → {x.row.proposed}"
                            for _, x in pending[:7])
        if len(pending) > 7:
            preview += f"\n... 외 {len(pending)-7}개"
        if not messagebox.askyesno(
            "파일명 변경 최종 확인",
            f"공식 조회에 성공한 {len(pending)}개 압축파일의 이름을 변경합니다.\n"
            "실제로 같은 게임인지 확인한 후 진행하세요.\n"
            "파일 내부 내용은 변경하지 않습니다.\n\n"
            + preview + "\n\n변경할까요?", parent=self):
            return
        changed, errors = 0, []
        for i, item in pending:
            try:
                rename_verified(item, self.verified[i])
                self.done.add(i)
                self.update_row(i)
                changed += 1
            except (ValueError, OSError) as exc:
                errors.append(f"{item.row.filename}: {exc}")
        self.info.set(f"변경 완료 {changed}개 · 건너뜀/실패 {len(errors)}개 · "
                      "나머지는 수동 처리할 수 있습니다.")
        if errors:
            messagebox.showwarning("일부 파일은 변경하지 못했습니다",
                                   "\n".join(errors[:10]), parent=self)
        else:
            messagebox.showinfo("이름 변경 완료",
                                f"{changed}개 파일 이름만 변경했습니다.\n"
                                "오류가 있으면 [최근 변경 취소]로 복구할 수 있습니다.",
                                parent=self)

    def undo(self):
        if self.busy:
            return
        journal = default_journal().with_name("folder-rename-history.jsonl")
        if not messagebox.askyesno("이름 변경 복구",
                                   "가장 최근 이름 변경 1건을 취소할까요?",
                                   parent=self):
            return
        try:
            after, before = undo_last(journal)
        except (ValueError, OSError) as exc:
            messagebox.showerror("복구할 수 없습니다", str(exc), parent=self)
            return
        for i, item in enumerate(self.plan):
            if item.path == before:
                self.done.discard(i)
                self.update_row(i)
        self.info.set(f"원상복구 완료 · {before.name}")

    def save_manual(self):
        if not self.plan:
            return
        target = filedialog.asksaveasfilename(
            title="못 찾은 게임 수동 처리 목록", defaultextension=".csv",
            initialfile="PlayDock_Manual_Review.csv",
            filetypes=[("CSV", "*.csv")])
        if not target:
            return
        unresolved = [(i, item) for i, item in enumerate(self.plan)
                      if ((item.path or item.status == "duplicate")
                          and i not in self.done
                          and (item.status != "ready" or
                               not self.verified.get(i) or
                               not self.verified[i].verified))]
        try:
            with open(target, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(("원본 파일명", "상태", "후보 품번", "안내"))
                for i, item in unresolved:
                    s = item.row.suggestion
                    writer.writerow((
                        item.row.filename, self.status_of(i),
                        s.code if s else "",
                        "DLsite 또는 Steam 공식 사이트에서 동일 게임인지 확인하고, "
                        "확실하면 탐색기에서 [RJ번호] 또는 [Steam 번호]를 추가하세요. "
                        "확인할 수 없으면 기존 파일명을 유지하세요.",
                    ))
        except OSError as exc:
            messagebox.showerror("수동 목록 저장 실패", str(exc), parent=self)
            return
        messagebox.showinfo("수동 확인 목록 저장 완료",
                            f"직접 확인할 게임 {len(unresolved)}개를 저장했습니다.\n\n"
                            + MANUAL_NOTE, parent=self)


def main():
    if "--self-test" in sys.argv:
        from experiments.dlsite_detector.folder_rename import DATA_FILENAME
        assert DATA_FILENAME.endswith(".json")
        print("One-folder PlayDock renamer self-test: PASS")
        return
    FolderRenamer().mainloop()


if __name__ == "__main__":
    main()
