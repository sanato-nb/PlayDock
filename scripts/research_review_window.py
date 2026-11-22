"""PlayDock 제외된 작품 → AI 조사 결과 검토 → 공식 재검증 → 사용자 승인 후 변경.

Never sends local paths to an AI. Never renames an archive automatically.
Local full paths are used only after the person explicitly selects files.
"""
from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from experiments.dlsite_detector.research_handoff import (
    ResearchSuggestion, VerifiedSuggestion, default_journal,
    proposed_filename, reverify, safe_rename, undo_last,
)


class ResearchReview(tk.Toplevel):
    def __init__(self, master, suggestions: list[ResearchSuggestion],
                 parsing_warnings: list[str]):
        super().__init__(master)
        self.master_window = master
        self.suggestions = suggestions
        self.verifications: dict[int, VerifiedSuggestion] = {}
        self.proposals: dict[int, str] = {}
        self.applied: set[int] = set()
        self.queue: Queue = Queue()
        self.working = False
        self.title("PlayDock — AI 조사 결과 검토 · 공식 재확인 · 파일명 변경")
        self.geometry("1240x700")
        self.minsize(940, 530)

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="AI 조사 결과 — 검토 후 필요한 항목만 이름 변경",
                  font=("맑은 고딕", 15, "bold")).pack(anchor="w")
        ttk.Label(body, text=(
            "AI가 제안한 품번은 신뢰하지 않습니다. [공식 재검증] 후,"
            " 사용자가 선택한 로컬 파일만 이름을 바꿀 수 있습니다."
        ), foreground="#555").pack(anchor="w", pady=(3, 8))
        top = ttk.Frame(body)
        top.pack(fill="x", pady=(0, 7))
        self.verify_button = ttk.Button(top, text="공식 재검증 (전체)",
                                        command=self.verify_all)
        self.verify_button.pack(side="left")
        self.verify_selected_button = ttk.Button(top, text="공식 재검증 (선택)",
                                                 command=self.verify_selected)
        self.verify_selected_button.pack(side="left", padx=5)
        self.edit_button = ttk.Button(top, text="변경할 파일명 편집",
                                      command=self.edit_name)
        self.edit_button.pack(side="left")
        self.rename_button = ttk.Button(top, text="선택한 파일명 변경",
                                        command=self.rename_selected)
        self.rename_button.pack(side="left", padx=5)
        self.undo_button = ttk.Button(top, text="최근 변경 원상복구",
                                      command=self.undo_rename)
        self.undo_button.pack(side="left")
        self.link_button = ttk.Button(top, text="실제 압축파일 연결",
                                      command=self.link_files)
        self.link_button.pack(side="right")

        columns = ("name", "store", "id", "ai", "official", "local", "proposed")
        self.table = ttk.Treeview(body, columns=columns, show="headings",
                                  selectmode="extended")
        for col, label, width in (
            ("name", "원본 파일명", 230),
            ("store", "스토어", 75),
            ("id", "품번 / App ID", 115),
            ("ai", "AI 의견", 110),
            ("official", "공식 재검증", 125),
            ("local", "실제 파일 연결", 125),
            ("proposed", "변경 제안 파일명 (기존 태그 유지)", 340),
        ):
            self.table.heading(col, text=label)
            self.table.column(col, width=width, minwidth=70)
        area = ttk.Frame(body)
        area.pack(fill="both", expand=True)
        self.table.pack(in_=area, side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(area, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self.show_detail)

        ttk.Label(body, text="상세 검증 정보 · 실제 파일이 연결되지 않은 항목은 이름을 바꿀 수 없습니다.").pack(
            anchor="w", pady=(8, 1))
        self.details = tk.Text(body, height=6, wrap="word", state="disabled")
        self.details.pack(fill="x")
        self.status = tk.StringVar(value=(
            f"AI 결과 {len(suggestions)}개 · 가져오기 경고 {len(parsing_warnings)}개 · "
            "공식 검증 전"
        ))
        ttk.Label(body, textvariable=self.status).pack(anchor="w", pady=(5, 0))

        for i, s in enumerate(self.suggestions):
            try:
                self.proposals[i] = proposed_filename(s.original_filename, s.store, s.code)
            except ValueError:
                self.proposals[i] = s.original_filename
            self.table.insert("", "end", iid=str(i))
            self.update_row(i)
        if parsing_warnings:
            messagebox.showwarning(
                "가져오기 중 일부 항목 제외",
                f"{len(parsing_warnings)}개 오류가 있습니다.\n"
                + "\n".join(parsing_warnings[:12]),
                parent=self,
            )
        self.after(150, self.poll)

    def connected_paths(self, original_filename: str) -> list[Path]:
        paths = getattr(self.master_window, "file_paths", [])
        # Use exact basename, no path from AI or JSON is allowed.
        return [Path(p) for p in paths
                if Path(p).name == original_filename and Path(p).is_file()]

    def update_row(self, i: int):
        s = self.suggestions[i]
        verified = self.verifications.get(i)
        official = (
            "변경 완료" if i in self.applied
            else "공식 확인 · 승인 필요" if verified and verified.verified
            else ("재검증 실패" if verified else "아직 확인 안 함")
        )
        n = len(self.connected_paths(s.original_filename))
        linked = "미연결" if n == 0 else ("1개 연결" if n == 1 else f"{n}개 동명 파일")
        self.table.item(str(i), values=(
            s.original_filename, s.store.upper(), s.code,
            s.verification, official, linked, self.proposals[i],
        ))

    def refresh_links(self):
        for i in range(len(self.suggestions)):
            self.update_row(i)

    def link_files(self):
        if self.working:
            return
        # The main program remembers full paths *locally* for rename.
        self.master_window.choose_files()
        self.refresh_links()
        count = sum(bool(self.connected_paths(x.original_filename))
                    for x in self.suggestions)
        self.status.set(f"실제 로컬 압축파일 연결: {count}/{len(self.suggestions)}개")

    def show_detail(self, _event=None):
        selected = self.table.selection()
        if not selected:
            return
        i = int(selected[0])
        s = self.suggestions[i]
        verified = self.verifications.get(i)
        lines = [
            f"원본: {s.original_filename}",
            f"AI 조사 제안: {s.store} {s.code}",
            f"AI가 기록한 공식 제목: {s.official_title or '(없음)'}",
            f"AI가 기록한 공식 URL: {s.official_url or '(없음)'}",
            f"판별 근거: {s.note or '(없음)'}",
            f"참고 URL: {s.evidence_url or '(없음)'}",
            f"공식 재검증: {verified.reason if verified else '미실행'}",
        ]
        if verified and verified.verified:
            lines.extend([
                f"실제 공식 작품명: {verified.official_title}",
                f"실제 공식 URL: {verified.official_url}",
            ])
        lines.extend([
            f"변경 예정 파일명: {self.proposals[i]}",
            f"로컬 실제 파일 연결: {len(self.connected_paths(s.original_filename))}개",
            "주의: 공식 식별번호 확인은 압축파일 내부 게임의 동일성을 증명하지 않습니다.",
        ])
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")

    def verify_all(self):
        self.begin_verify(list(range(len(self.suggestions))))

    def verify_selected(self):
        self.begin_verify([int(i) for i in self.table.selection()])

    def begin_verify(self, indices: list[int]):
        if self.working:
            return
        if not indices:
            messagebox.showinfo("선택 없음", "재검증할 항목을 선택하세요.", parent=self)
            return
        self.working = True
        self.verify_button.configure(state="disabled")
        self.verify_selected_button.configure(state="disabled")
        self.rename_button.configure(state="disabled")
        self.status.set(f"{len(indices)}개 공식 사이트 재조회 중")
        Thread(target=self.worker, args=(indices,), daemon=True).start()

    def worker(self, indices):
        for i in indices:
            try:
                result = reverify(self.suggestions[i])
            except Exception as exc:
                result = VerifiedSuggestion(
                    self.suggestions[i], False,
                    reason=f"재검증 실패: {type(exc).__name__}",
                )
            self.queue.put(("verified", i, result))
        self.queue.put(("done",))

    def poll(self):
        try:
            while True:
                action = self.queue.get_nowait()
                if action[0] == "verified":
                    _, i, result = action
                    self.verifications[i] = result
                    self.update_row(i)
                elif action[0] == "done":
                    self.working = False
                    self.verify_button.configure(state="normal")
                    self.verify_selected_button.configure(state="normal")
                    self.rename_button.configure(state="normal")
                    verified = sum(r.verified for r in self.verifications.values())
                    self.status.set(f"공식 재확인 {verified}개 · 검증 실패/검토 필요 "
                                    f"{len(self.verifications)-verified}개")
                    self.show_detail()
        except Empty:
            pass
        if self.winfo_exists():
            self.after(150, self.poll)

    def edit_name(self):
        chosen = self.table.selection()
        if len(chosen) != 1:
            messagebox.showinfo("하나 선택", "파일 한 개를 선택해 주세요.", parent=self)
            return
        i = int(chosen[0])
        current = self.proposals[i]
        value = simpledialog.askstring(
            "변경할 이름 편집", "기존 버전·패치 정보와 확장자를 보존하세요.\n"
            "변경은 [선택한 파일명 변경] 버튼을 누르고 승인해야 실제로 적용됩니다.",
            initialvalue=current, parent=self,
        )
        if value is None:
            return
        value = value.strip()
        # Validate without accessing the filesystem.
        from experiments.dlsite_detector.research_handoff import _safe_name
        if (not _safe_name(value) or
                Path(value).suffix.casefold() !=
                Path(self.suggestions[i].original_filename).suffix.casefold()):
            messagebox.showerror("이름 오류",
                                 "허용되지 않은 파일명 또는 원본 압축 확장자 변경입니다.",
                                 parent=self)
            return
        self.proposals[i] = value
        self.update_row(i)

    def rename_selected(self):
        if self.working:
            return
        choices = [int(i) for i in self.table.selection()]
        if not choices:
            messagebox.showinfo("선택 없음", "변경할 행을 선택하세요.", parent=self)
            return
        prepared, blocked = [], []
        for i in choices:
            s = self.suggestions[i]
            verified = self.verifications.get(i)
            paths = self.connected_paths(s.original_filename)
            if i in self.applied:
                blocked.append(f"{s.original_filename}: 이미 변경됨")
            elif not verified or not verified.verified:
                blocked.append(f"{s.original_filename}: 공식 재검증 필요")
            elif len(paths) != 1:
                blocked.append(f"{s.original_filename}: 실제 파일 미연결/동명이름 중복")
            elif self.proposals[i] == paths[0].name:
                blocked.append(f"{s.original_filename}: 변경할 이름이 기존과 동일")
            else:
                prepared.append((i, paths[0], self.proposals[i]))
        if blocked:
            messagebox.showwarning("변경할 수 없는 항목",
                                   "\n".join(blocked[:10]), parent=self)
        if not prepared:
            return
        summary = "\n".join(f"{old.name}\n  → {name}"
                            for _, old, name in prepared[:8])
        if len(prepared) > 8:
            summary += f"\n... 외 {len(prepared)-8}개"
        if not messagebox.askyesno(
            "실제 파일명 변경 승인",
            f"공식 식별번호를 재확인한 {len(prepared)}개 압축파일명을"
            f" 실제로 변경합니다.\n기존 파일 내용은 건드리지 않습니다.\n\n"
            f"{summary}\n\n승인하시겠습니까?",
            parent=self,
        ):
            return
        ok, failed = 0, []
        for i, old, name in prepared:
            try:
                dest, _ = safe_rename(old, name, default_journal())
                self.master_window.local_path_changed(old, dest)
                self.applied.add(i)
                self.update_row(i)
                ok += 1
            except (OSError, ValueError) as exc:
                failed.append(f"{old.name}: {exc}")
        self.status.set(f"파일명 변경 {ok}개 완료 · 실패 {len(failed)}개")
        if failed:
            messagebox.showwarning("일부 변경 실패", "\n".join(failed[:15]),
                                   parent=self)

    def undo_rename(self):
        if self.working:
            return
        if not messagebox.askyesno(
            "원상복구 확인",
            "이 프로그램이 기록한 가장 최근의 파일명 변경 1건을"
            " 원래 이름으로 복구할까요?\n"
            "원본 이름에 다른 파일이 있으면 덮어쓰지 않고 중단합니다.",
            parent=self,
        ):
            return
        try:
            after, before = undo_last(default_journal())
            self.master_window.local_path_changed(after, before)
        except (OSError, ValueError, FileExistsError) as exc:
            messagebox.showerror("원상복구 실패", str(exc), parent=self)
            return
        for i, s in enumerate(self.suggestions):
            if s.original_filename == before.name:
                self.applied.discard(i)
                self.update_row(i)
        self.status.set(f"원상복구 완료: {before.name}")
