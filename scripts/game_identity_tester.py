"""PlayDock 게임 정체 판독기 사용자 검증용 Windows GUI (1~6단계).

테스터는 원본 ZIP/7z/RAR을 변경하거나 게임을 실행하지 않는다.
사용자가 선택한 로컬 파일만 열고, 온라인 모드에서는 게임 제목과 공식 코드
검색어만 외부 검색기에 전달한다. CSV/JSON 저장은 사용자가 명시한 경우만.
"""
from __future__ import annotations

from datetime import datetime
import csv
import io
import json
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.archive_inspector import inspect_archive
from experiments.dlsite_detector.identity_verifier import verify_identity
from experiments.dlsite_detector.internal_metadata import inspect_metadata

VERSION = "0.1-test"
VERDICT_KO = {
    "matched": "일치 확인",
    "likely_candidate": "유력 후보",
    "needs_review": "확인 필요",
    "conflict": "근거 충돌",
    "unclassifiable": "분류 불가",
}
ARCHIVE_TYPES = [
    ("게임 압축파일", "*.zip *.7z *.rar"),
    ("ZIP", "*.zip"), ("7z", "*.7z"), ("RAR", "*.rar"),
]


class IdentityTesterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"PlayDock 게임 정체 판독기 · 검증판 {VERSION}")
        self.geometry("1050x700")
        self.minsize(820, 530)
        self.configure(bg="#101923")
        self.paths: list[Path] = []
        self.rows: list[dict] = []
        self.queue: Queue = Queue()
        self.thread: threading.Thread | None = None
        self.stop_requested = threading.Event()
        self.online = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="게임 압축파일을 선택한 뒤 분석 시작을 누르세요.")
        self.progress = tk.StringVar(value="선택된 파일 없음")
        self._style()
        self._layout()
        self.after(100, self._drain_queue)

    def _style(self) -> None:
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", font=("Malgun Gothic", 10))
        st.configure("Frame.TFrame", background="#101923")
        st.configure("TLabel", background="#101923", foreground="#e9eef6")
        st.configure("Title.TLabel", font=("Malgun Gothic", 17, "bold"))
        st.configure("Hint.TLabel", font=("Malgun Gothic", 9),
                     foreground="#9aaebe")
        st.configure("TButton", padding=(12, 8))
        st.configure("TCheckbutton", background="#101923", foreground="#e9eef6")
        st.configure("Treeview", rowheight=30, background="#192532",
                     foreground="#eff4fa", fieldbackground="#192532",
                     borderwidth=0, font=("Malgun Gothic", 10))
        st.configure("Treeview.Heading", background="#304356",
                     foreground="#e9eef6", font=("Malgun Gothic", 10, "bold"))
        st.map("Treeview", background=[("selected", "#285479")])
        st.configure("TProgressbar", troughcolor="#243447",
                     background="#368dd0")

    def _layout(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="게임 정체 판독기 · 사용자 검증판",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="선택한 ZIP / 7z / RAR만 분석 · 게임 실행/압축 전체 해제/원본 변경 없음",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 14))

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 8))
        self.choose_button = ttk.Button(
            toolbar, text="압축파일 선택 (여러 개 가능)", command=self.choose_files
        )
        self.choose_button.pack(side="left", padx=(0, 8))
        self.clear_button = ttk.Button(
            toolbar, text="목록 초기화", command=self.clear_files
        )
        self.clear_button.pack(side="left", padx=(0, 8))
        self.start_button = ttk.Button(
            toolbar, text="판독 시작", command=self.start
        )
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(
            toolbar, text="다음 파일부터 중지", command=self.request_stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(0, 8))
        self.save_button = ttk.Button(
            toolbar, text="결과 저장", command=self.save_report, state="disabled",
        )
        self.save_button.pack(side="right")

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            options,
            text="인터넷에서 작품 검색 + 1~6단계 교차검증",
            variable=self.online,
        ).pack(side="left")
        ttk.Label(
            options,
            text="끄면 인터넷 없이 내부 목록·소형 설정만 확인 (최종 작품 판정 없음)",
            style="Hint.TLabel",
        ).pack(side="left", padx=(14, 0))

        ttk.Label(outer, textvariable=self.progress,
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 5))
        columns = ("file", "verdict", "title", "encryption", "scan")
        self.tree = ttk.Treeview(outer, columns=columns, show="headings", height=9)
        for key, text, width in (
            ("file", "압축파일", 300),
            ("verdict", "판정", 115),
            ("title", "게임명 후보", 255),
            ("encryption", "암호화", 95),
            ("scan", "내부 확인", 120),
        ):
            self.tree.heading(key, text=text)
            self.tree.column(key, minwidth=85, width=width, stretch=key in ("file", "title"))
        self.tree.pack(fill="both", expand=True, pady=(0, 10))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        ttk.Label(outer, text="선택한 파일의 판정 근거 및 주의 사항").pack(anchor="w")
        self.detail = tk.Text(
            outer, height=11, bg="#14212f", fg="#e2ebf6",
            insertbackground="white", borderwidth=0, padx=12, pady=10,
            font=("Consolas", 10), wrap="word",
        )
        self.detail.pack(fill="both", expand=True, pady=(5, 9))
        self.detail.insert("1.0", "아직 분석 결과가 없습니다.")
        self.detail.configure(state="disabled")
        self.bar = ttk.Progressbar(outer, maximum=1, value=0)
        self.bar.pack(fill="x", pady=(0, 7))
        ttk.Label(outer, textvariable=self.status,
                  style="Hint.TLabel").pack(anchor="w")

    def choose_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="검증할 게임 압축파일 선택", filetypes=ARCHIVE_TYPES,
        )
        if not files:
            return
        seen = {str(p).casefold() for p in self.paths}
        for raw in files:
            path = Path(raw)
            if path.suffix.casefold() not in {".zip", ".7z", ".rar"}:
                continue
            if str(path).casefold() not in seen:
                self.paths.append(path)
                seen.add(str(path).casefold())
        self._render_files()

    def clear_files(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.paths.clear()
        self.rows.clear()
        self.tree.delete(*self.tree.get_children())
        self.progress.set("선택된 파일 없음")
        self.save_button.configure(state="disabled")
        self._set_detail("아직 분석 결과가 없습니다.")

    def _render_files(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        for idx, path in enumerate(self.paths):
            self.tree.insert("", "end", iid=str(idx),
                             values=(path.name, "대기", "-", "-", "-"))
        self.progress.set(f"{len(self.paths)}개 파일 선택됨")
        self.save_button.configure(state="disabled")

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        if not self.paths:
            messagebox.showwarning("파일 선택", "검증할 압축파일을 먼저 선택하세요.")
            return
        mode = self.online.get()
        if mode:
            approved = messagebox.askokcancel(
                "인터넷 검색 안내",
                "선택한 압축파일의 이름에서 추출한 작품명·품번을 "
                "DLsite, Steam 및 일반 웹 검색에 전송합니다.\n\n"
                "전체 로컬 경로·압축파일 내용은 전송하지 않습니다.\n"
                "네트워크 접속이 차단되면 '확인 필요' 또는 '분류 불가'로 "
                "남을 수 있습니다. 계속할까요?",
            )
            if not approved:
                return
        self.rows.clear()
        self._render_files()
        self.stop_requested.clear()
        self.bar.configure(maximum=len(self.paths), value=0)
        for ctl in (self.choose_button, self.clear_button, self.start_button):
            ctl.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.save_button.configure(state="disabled")
        self.status.set("분석 중… (대용량 압축 목록이나 인터넷 검색은 오래 걸릴 수 있습니다)")
        paths = tuple(self.paths)
        self.thread = threading.Thread(
            target=self._worker, args=(paths, mode), daemon=True,
        )
        self.thread.start()

    def request_stop(self) -> None:
        self.stop_requested.set()
        self.status.set("중단 요청됨. 진행 중인 파일이 완료되면 다음 파일부터 중지합니다.")

    def _worker(self, paths: tuple[Path, ...], online: bool) -> None:
        try:
            for idx, path in enumerate(paths):
                if self.stop_requested.is_set():
                    break
                self.queue.put(("progress", idx, path.name))
                try:
                    if not path.is_file() or path.is_symlink():
                        raise ValueError("일반 로컬 파일이 아니거나 파일을 찾을 수 없습니다.")
                    if online:
                        stages = identify_archive(path, allow_metadata=True)
                        verified = verify_identity(stages)
                        data = {
                            "mode": "stages_1_to_6",
                            "archive_name": path.name,
                            "stages_1_to_5": stages.to_dict(),
                            "verification": verified.to_dict(),
                        }
                        result = {
                            "name": path.name,
                            "verdict": verified.label,
                            "title": verified.proposed_title or (
                                " / ".join(verified.candidate_titles) or "-"
                            ),
                            "encryption": verified.encryption_state,
                            "scan": verified.inspection_state,
                            "detail": self._format_verification(verified, stages),
                            "payload": data,
                        }
                    else:
                        index = inspect_archive(path)
                        meta = inspect_metadata(path)
                        data = {
                            "mode": "offline_metadata_only",
                            "archive_name": path.name,
                            "inspection": index.to_dict(),
                            "metadata": meta.to_dict(),
                        }
                        result = {
                            "name": path.name,
                            "verdict": "내부 근거만",
                            "title": " / ".join(meta.title_candidates) or "-",
                            "encryption": "encrypted" if index.encrypted else "미확인" if index.state == "unavailable" else "clear",
                            "scan": index.state,
                            "detail": self._format_offline(index, meta),
                            "payload": data,
                        }
                except Exception as exc:
                    result = {
                        "name": path.name, "verdict": "오류", "title": "-",
                        "encryption": "-", "scan": "실패",
                        "detail": f"파일 분석 오류: {type(exc).__name__}: {exc}",
                        "payload": {"mode": "error", "archive_name": path.name,
                                    "error": type(exc).__name__},
                    }
                self.queue.put(("result", idx, result))
        finally:
            self.queue.put(("done",))

    @staticmethod
    def _format_verification(verified, stages) -> str:
        out = [
            f"판정: {verified.label}",
            f"게임명 후보: {verified.proposed_title or ', '.join(verified.candidate_titles) or '없음'}",
            f"암호화: {verified.encryption_state}",
            f"파일 구성: {verified.package_assessment}",
            f"한국어 근거: {verified.localization_assessment}",
            f"내부 목록: {verified.inspection_state}",
            f"메타데이터: {verified.metadata_state}",
            "",
            "[적용된 규칙]",
            *[f"  • {x}" for x in verified.matched_rules],
            "[판정 보류·충돌 사유]",
            *[f"  • {x}" for x in verified.blockers],
            "[아직 확인할 수 없는 사항]",
            *[f"  • {x}" for x in verified.limitations],
            "",
            "[근거 일부 (최대 30개)]",
        ]
        out.extend(
            f"  {e.strength} / {e.kind} / {e.origin} / {e.value} "
            f"({e.member or e.field or e.parser})"
            for e in verified.evidence[:30]
        )
        out.append("")
        out.append("※ 자동 분류는 원본 파일이나 PlayDock 라이브러리를 수정하지 않습니다.")
        return "\n".join(out)

    @staticmethod
    def _format_offline(inspection, meta) -> str:
        out = [
            f"인터넷 검색 없는 내부 조사 (작품 정체 확정 아님)",
            f"압축 내부 목록: {inspection.state} / {inspection.member_count}개 항목",
            f"암호화 표시: {inspection.encrypted}",
            f"메타데이터: {meta.state} / {meta.inspected_files}개 파일 읽음",
            f"게임명 후보: {', '.join(meta.title_candidates) or '없음'}",
            f"DLsite 코드: {', '.join(meta.product_codes) or '없음'}",
            f"Steam ID: {', '.join(meta.steam_app_ids) or '없음'}",
            f"엔진: {', '.join(inspection.engine_hints) or '미확인'}",
            "",
            "[내부 근거]",
        ]
        out.extend(
            f"  {e.strength} / {e.kind} / {e.candidate_title} "
            f"({e.member}, {e.field})"
            for e in meta.evidence[:30]
        )
        return "\n".join(out)

    def _drain_queue(self) -> None:
        try:
            while True:
                event = self.queue.get_nowait()
                if event[0] == "progress":
                    _, idx, name = event
                    self.status.set(f"분석 중 {idx + 1}/{len(self.paths)}: {name}")
                elif event[0] == "result":
                    _, idx, row = event
                    self.rows.append(row)
                    if self.tree.exists(str(idx)):
                        self.tree.item(str(idx), values=(
                            row["name"], row["verdict"], row["title"],
                            row["encryption"], row["scan"],
                        ))
                        self.tree.selection_set(str(idx))
                    self.bar.configure(value=len(self.rows))
                    self._set_detail(row["detail"])
                    self.progress.set(f"{len(self.rows)} / {len(self.paths)}개 검사 완료")
                    self.save_button.configure(state="normal")
                elif event[0] == "done":
                    for ctl in (self.choose_button, self.clear_button, self.start_button):
                        ctl.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    suffix = " (사용자 중지)" if self.stop_requested.is_set() else ""
                    self.status.set(f"{len(self.rows)}개 파일 처리 완료{suffix}. 필요하면 결과 저장을 누르세요.")
        except Empty:
            pass
        self.after(100, self._drain_queue)

    def _on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        index = int(selected[0])
        # 행이 순서대로 끝나지 않을 수 있으므로 선택 ID와 결과의 파일명을 비교.
        if index >= len(self.paths):
            return
        name = self.paths[index].name
        for row in self.rows:
            if row["name"] == name:
                self._set_detail(row["detail"])
                return

    def _set_detail(self, value: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", value)
        self.detail.configure(state="disabled")

    def save_report(self) -> None:
        if not self.rows:
            return
        path = filedialog.asksaveasfilename(
            title="판독 결과 저장", defaultextension=".json",
            filetypes=[("JSON 보고서", "*.json"), ("CSV 요약", "*.csv")],
            initialfile="PlayDock_Identity_Test_Results.json",
        )
        if not path:
            return
        try:
            target = Path(path)
            if target.suffix.casefold() == ".csv":
                with target.open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.DictWriter(
                        stream, fieldnames=("name", "verdict", "title", "encryption", "scan"),
                    )
                    writer.writeheader()
                    writer.writerows([
                        {key: row[key] for key in writer.fieldnames}
                        for row in self.rows
                    ])
            else:
                document = {
                    "program": "PlayDock Identity Tester",
                    "version": VERSION,
                    "created_at_local": datetime.now().astimezone().isoformat(),
                    "files": [row["payload"] for row in self.rows],
                    "notice": "선택한 파일만 읽기 전용으로 분석. 정체 판정은 게임 진위 보증이 아님.",
                }
                target.write_text(json.dumps(
                    document, ensure_ascii=False, indent=2,
                ), encoding="utf-8")
            messagebox.showinfo("저장 완료", f"보고서를 저장했습니다:\n{path}")
        except OSError as exc:
            messagebox.showerror("저장 오류", str(exc))


def self_test() -> int:
    """배포 EXE에 실제 판독 모듈/ZIP 처리 코드가 포함됐는지 오프라인 확인."""
    from tempfile import TemporaryDirectory
    import zipfile

    from experiments.dlsite_detector.pipeline import SearchDecision
    with TemporaryDirectory(prefix="playdock-identity-selftest-") as tmp:
        path = Path(tmp) / "Tester Sample.zip"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("Game/Game.ini", "Title=Sample Test Game\n")
            z.writestr("Game/steam_appid.txt", "1621540\n")
            z.writestr("Game/Tester.exe", b"SAMPLE, NOT EXECUTABLE")
            z.writestr("Game/game/archive.rpa", b"SAMPLE DATA")
        def offline_mock(_):
            return SearchDecision(
                "platform_confirmed_game", "Sample Test Game",
                proposed_title="Sample Test Game",
                source_platform="steam", source_id="1621540",
            )
        result = identify_archive(
            path, classifier=offline_mock, allow_metadata=True,
        )
        verified = verify_identity(result)
        assert result.completed_steps == (1, 2, 3, 4, 5)
        assert verified.verdict == "matched", verified.verdict
        assert not verified.automatic_binding_allowed
    return 0


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    IdentityTesterApp().mainloop()
