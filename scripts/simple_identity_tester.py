"""PlayDock v0.10: 게임명·품번 전용 Windows 독립 검증판.

버전·언어·엔진·게임 데이터는 현재 단계에서 분석하지 않음.
인터넷에는 선별된 이름·품번 검색어만 보내고 원본 경로/게임 파일 내용은 제외.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import zipfile

from experiments.dlsite_detector.simple_identity import (
    SimpleResult, SimpleScan, analyze_identity,
)
from experiments.dlsite_detector.search_session import SearchSession
from experiments.dlsite_detector.enhanced_search import (
    fast_enhanced_classify_game, enhanced_classify_game,
)
from experiments.dlsite_detector.pipeline import SearchDecision

VERSION = "0.10.1-test"
ARCHIVE_TYPES = [
    ("게임 압축파일", "*.zip *.7z *.rar"),
    ("ZIP", "*.zip"), ("7z", "*.7z"), ("RAR", "*.rar"),
]
UNRESOLVED = {"likely", "multiple", "unidentified", "search_error"}


def _detail(result: SimpleResult) -> str:
    scan = result.scan
    lines = [
        f"파일명: {result.archive_name}",
        f"판독: {result.label}",
        f"게임 이름: {result.title or '미확인'}",
        f"공식 품번·ID: {result.product_code or '없음 / 미확인'}",
        f"이유: {result.reason}",
        "",
        "[이름과 품번 출처]",
    ]
    lines += [
        f"  · {c.kind} / {c.value} · {c.source}"
        + (f" ({c.detail})" if c.detail else "")
        for c in scan.clues
    ] or ["  · 수집된 이름·품번 없음"]
    lines += [
        "", "[실행파일 이름 확인]",
        "  · " + (", ".join(scan.exe_candidates) or "유력 후보 없음"),
    ]
    if scan.exe_ambiguous:
        lines.append("  · 여러 EXE가 존재하여 어느 것도 게임 제목으로 선택하지 않았습니다.")
    lines += [
        "", "[인터넷 조회]",
        "  · 사용 검색어: " + (", ".join(result.search_queries) or "없음"),
    ]
    for attempt in result.attempts:
        d = attempt.decision
        lines.append(
            f"  · {attempt.query}: {d.status} / "
            f"{d.proposed_title or '-'} / {d.dlsite_code or d.source_id or '-'}"
            + (f" / {d.search_state}" if d.search_state else "")
        )
    if result.alternatives:
        lines += ["", "[추가 후보]"]
        lines.extend("  · " + value for value in result.alternatives)
    if result.notes:
        lines += ["", "[제한·주의사항]"]
        lines.extend("  · " + item for item in result.notes)
    lines += [
        "",
        "[후속 단계에서만 검사]",
        "  · 버전 / 언어 / 한국어 패치 / DLC / 게임 엔진 등은 현재 판정에서 사용하지 않음",
        "  · 공식 작품을 찾았더라도 압축파일 내부 게임의 진위는 인증되지 않음",
        f"  · 소요시간: {result.elapsed_seconds:.2f}초",
    ]
    return "\n".join(lines)


class SimpleIdentityApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PlayDock 게임 정체 판독기 · 간소화 " + VERSION)
        self.geometry("1050x710")
        self.minsize(840, 550)
        self.configure(background="#101923")
        self.paths: list[Path] = []
        self.results: dict[int, SimpleResult] = {}
        self.snapshots: dict[int, tuple[tuple[int, int], object]] = {}
        self.queue: Queue = Queue()
        self.worker: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self.online = tk.BooleanVar(value=True)
        self.fast = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="압축파일을 선택한 다음 시작을 누르세요.")
        self.counter = tk.StringVar(value="선택된 파일 없음")
        self.step = tk.StringVar(value="현재 단계: 대기")
        self._style()
        self._layout()
        self.after(110, self._pump)

    def _style(self) -> None:
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", font=("Malgun Gothic", 10))
        st.configure("TFrame", background="#101923")
        st.configure("TLabel", background="#101923", foreground="#e5eef8")
        st.configure("Hint.TLabel", background="#101923", foreground="#9cb0c3",
                     font=("Malgun Gothic", 9))
        st.configure("Heading.TLabel", background="#101923", foreground="#f3f8ff",
                     font=("Malgun Gothic", 17, "bold"))
        st.configure("TButton", padding=(10, 8))
        st.configure("TCheckbutton", background="#101923", foreground="#e5eef8")
        st.configure("TNotebook", background="#101923")
        st.configure("TNotebook.Tab", padding=(13, 7))
        st.configure("Treeview", rowheight=29, background="#192634",
                     foreground="#eef5fc", fieldbackground="#192634")
        st.configure("Treeview.Heading", background="#304356",
                     foreground="#e5eef8", font=("Malgun Gothic", 10, "bold"))
        st.map("Treeview", background=[("selected", "#275279")])
        st.configure("TProgressbar", troughcolor="#263c50", background="#3589d5")

    def _layout(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="게임 정체 판독기 v0.10.1 · 이름 + 품번",
                  style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            outer, style="Hint.TLabel",
            text="압축파일명·최상위 폴더·주 EXE명·README 라벨만 사용 → 정체 판독 → 미확인 별도 분류",
        ).pack(anchor="w", pady=(4, 12))
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 8))
        self.choose = ttk.Button(toolbar, text="압축파일 선택", command=self.choose_files)
        self.choose.pack(side="left", padx=(0, 7))
        self.clear = ttk.Button(toolbar, text="목록 초기화", command=self.clear_files)
        self.clear.pack(side="left", padx=(0, 7))
        self.start_button = ttk.Button(toolbar, text="판독 시작", command=self.start)
        self.start_button.pack(side="left", padx=(0, 7))
        self.stop_button = ttk.Button(toolbar, text="다음 파일부터 중단",
                                      state="disabled", command=self.stop)
        self.stop_button.pack(side="left", padx=(0, 7))
        self.retry = ttk.Button(toolbar, text="미확인 재검사", command=self.retry_unresolved,
                                state="disabled")
        self.retry.pack(side="left", padx=(0, 7))
        self.save = ttk.Button(toolbar, text="JSON 저장", command=self.save_json,
                               state="disabled")
        self.save.pack(side="right")
        checks = ttk.Frame(outer)
        checks.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(checks, text="인터넷에서 이름·품번 조회", variable=self.online
                        ).pack(side="left")
        ttk.Checkbutton(checks, text="빠른 검색 (기본은 정밀)", variable=self.fast
                        ).pack(side="left", padx=(16, 0))
        ttk.Label(outer, textvariable=self.counter).pack(anchor="w")
        self.bar = ttk.Progressbar(outer, maximum=100, value=0, mode="determinate")
        self.bar.pack(fill="x", pady=(3, 5))
        ttk.Label(outer, textvariable=self.step).pack(anchor="w")
        ttk.Label(outer, textvariable=self.status, style="Hint.TLabel").pack(
            anchor="w", pady=(3, 9))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True, pady=(0, 8))
        self.all_tree = self._new_table(self.tabs, "전체 결과")
        self.pending_tree = self._new_table(self.tabs, "보류·미확인만")
        ttk.Label(outer, text="선택한 파일의 이름·품번 판정 근거").pack(anchor="w")
        self.details = tk.Text(
            outer, height=13, wrap="word", bg="#142330", fg="#edf4fc",
            insertbackground="#ffffff", borderwidth=0, padx=12, pady=9,
            font=("Consolas", 10),
        )
        self.details.pack(fill="both", expand=True, pady=(5, 2))
        self._set_detail("아직 판독 결과가 없습니다.")

    def _new_table(self, notebook, name: str) -> ttk.Treeview:
        page = ttk.Frame(notebook)
        notebook.add(page, text=name)
        cols = ("file", "state", "title", "product", "scan")
        tree = ttk.Treeview(page, columns=cols, show="headings", height=8)
        for field, title, width in (
            ("file", "압축파일", 260),
            ("state", "판독 상태", 150),
            ("title", "게임 이름", 240),
            ("product", "품번", 135),
            ("scan", "내부 이름 검사", 120),
        ):
            tree.heading(field, text=title)
            tree.column(field, width=width, minwidth=85,
                        stretch=field in {"file", "title"})
        tree.tag_configure("found", foreground="#85d7a1")
        tree.tag_configure("pending", foreground="#f0c986")
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        tree.bind("<<TreeviewSelect>>", lambda _, obj=tree: self._on_select(obj))
        return tree

    def choose_files(self) -> None:
        incoming = filedialog.askopenfilenames(
            title="게임 압축파일 선택", filetypes=ARCHIVE_TYPES)
        seen = {str(x).casefold() for x in self.paths}
        for raw in incoming:
            path = Path(raw)
            if (path.suffix.casefold() in {".zip", ".7z", ".rar"}
                    and str(path).casefold() not in seen):
                self.paths.append(path)
                seen.add(str(path).casefold())
        self._render_initial()

    def clear_files(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.paths.clear()
        self.results.clear()
        self.snapshots.clear()
        self._render_initial()
        self._set_detail("아직 판독 결과가 없습니다.")

    def _render_initial(self) -> None:
        for tree in (self.all_tree, self.pending_tree):
            tree.delete(*tree.get_children())
        for idx, path in enumerate(self.paths):
            self.all_tree.insert("", "end", iid=str(idx),
                                 values=(path.name, "대기", "-", "-", "-"))
        for idx, result in sorted(self.results.items()):
            if idx < len(self.paths):
                self._upsert_result(idx, result)
        self.counter.set(f"파일 {len(self.paths)}개 선택됨")
        self.bar.configure(value=0)
        self.step.set("현재 단계: 대기")
        self.retry.configure(state="normal" if any(
            r.is_unresolved for r in self.results.values()
        ) else "disabled")
        self.save.configure(state="normal" if self.results else "disabled")

    def _set_detail(self, value: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", value)
        self.details.configure(state="disabled")

    def _on_select(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if selected:
            idx = int(selected[0])
            self._set_detail(_detail(self.results[idx]) if idx in self.results
                             else "아직 검사 전입니다.")

    def _confirm_online(self) -> bool:
        return (not self.online.get() or messagebox.askokcancel(
            "인터넷 검색 동의",
            "선택된 압축파일명·파일명·README에서 추출한 '게임 이름/품번'만 "
            "외부 공식 상품 조회 및 일반 웹 검색에 사용합니다.\n\n"
            "로컬 전체 경로, EXE 내용, README 원문, 사용자 게임 목록은 "
            "업로드하지 않습니다. 진행할까요?",
        ))

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.paths:
            messagebox.showwarning("압축파일 선택", "먼저 압축파일을 선택해 주세요.")
            return
        if not self._confirm_online():
            return
        self.results.clear()
        self.snapshots.clear()
        self._render_initial()
        self._start_worker(tuple(range(len(self.paths))), retry=False)

    def retry_unresolved(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        targets = tuple(i for i, result in self.results.items()
                        if result.status in UNRESOLVED)
        if not targets:
            messagebox.showinfo("재검사", "재검사할 미확인 파일이 없습니다.")
            return
        if not self._confirm_online():
            return
        self._start_worker(targets, retry=True)

    def _start_worker(self, indices: tuple[int, ...], *, retry: bool) -> None:
        self.stop_flag.clear()
        self._target_total = len(indices)
        for ctl in (self.choose, self.clear, self.start_button, self.retry):
            ctl.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.save.configure(state="disabled")
        self.status.set("이름·품번 판독 중…")
        self.counter.set(f"0 / {self._target_total}개 완료")
        self.bar.configure(value=0)
        self.worker = threading.Thread(
            target=self._worker_run,
            args=(indices, self.online.get(), self.fast.get(), retry),
            daemon=True,
        )
        self.worker.start()

    def stop(self) -> None:
        self.stop_flag.set()
        self.status.set("중단 요청됨: 현재 파일이 끝나면 다음 파일부터 중지합니다.")

    def _worker_run(self, indices: tuple[int, ...], online: bool,
                    fast: bool, retry: bool) -> None:
        search = SearchSession(
            fast_enhanced_classify_game if fast else enhanced_classify_game,
        ) if online else None
        try:
            for complete, idx in enumerate(indices):
                if self.stop_flag.is_set():
                    break
                path = self.paths[idx]
                self.queue.put(("progress", complete, len(indices), path.name))
                def notify(step: str) -> None:
                    self.queue.put(("step", step))
                try:
                    previous = None
                    if retry and idx in self.snapshots:
                        old_stat, old_scan = self.snapshots[idx]
                        st = path.stat()
                        if (st.st_size, st.st_mtime_ns) == old_stat:
                            previous = old_scan
                    result = analyze_identity(
                        path, online=online, classifier=search,
                        scan=previous,
                        max_queries=3 if fast else 6, progress=notify,
                    )
                    st = path.stat()
                    self.queue.put((
                        "result", idx, result, (st.st_size, st.st_mtime_ns),
                    ))
                except Exception as exc:
                    # 파일 열기 실패도 별도 '미확인' 목록과 JSON에 남겨야
                    # 사용자가 추후 수동 검수/재검사를 할 수 있다.
                    scan = SimpleScan(
                        path.name, "unknown", "unavailable", 0, (), (),
                        False, "not_inspected",
                        ("분석 예외: " + type(exc).__name__,),
                    )
                    failed = SimpleResult(
                        path.name, "unidentified", "", "",
                        "압축파일 검사 오류. 수동 재검사가 필요합니다.",
                        scan, (), (), (), scan.notes, 0.0,
                    )
                    self.queue.put(("result", idx, failed, None))
                self.queue.put(("complete", complete+1, len(indices)))
        finally:
            self.queue.put(("done",))

    def _pump(self) -> None:
        try:
            while True:
                event = self.queue.get_nowait()
                if event[0] == "progress":
                    _, current, total, name = event
                    self.counter.set(f"{current}/{total}개 완료 · {name}")
                elif event[0] == "step":
                    self.step.set("현재 단계: " + event[1])
                elif event[0] == "result":
                    _, idx, result, signature = event
                    self.results[idx] = result
                    if signature is not None:
                        self.snapshots[idx] = (signature, result.scan)
                    self._upsert_result(idx, result)
                elif event[0] == "error":
                    _, idx, error = event
                    self.status.set(f"{self.paths[idx].name} 검사 오류: {error}")
                    self.all_tree.item(str(idx), values=(
                        self.paths[idx].name, "검사 오류", "-", "-", "-"
                    ))
                elif event[0] == "complete":
                    _, finished, total = event
                    self.bar.configure(value=finished / max(total, 1) * 100)
                    self.counter.set(f"{finished}/{total}개 완료")
                elif event[0] == "done":
                    for ctl in (self.choose, self.clear, self.start_button):
                        ctl.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.retry.configure(state="normal" if any(
                        r.status in UNRESOLVED for r in self.results.values()
                    ) else "disabled")
                    self.save.configure(state="normal" if self.results else "disabled")
                    count = sum(r.status == "identified" for r in self.results.values())
                    waiting = sum(r.is_unresolved for r in self.results.values())
                    self.status.set(
                        f"완료: 공식 작품 식별 {count}개 · 보류/미확인 {waiting}개 "
                        "(실제 압축파일의 진위는 미인증)"
                    )
                    self.step.set("현재 단계: 판독 완료")
        except Empty:
            pass
        self.after(110, self._pump)

    def _upsert_result(self, idx: int, result: SimpleResult) -> None:
        row = (
            result.archive_name, result.label,
            result.title or "-", result.product_code or "-",
            result.scan.scan_state,
        )
        tag = "found" if not result.is_unresolved else "pending"
        if self.all_tree.exists(str(idx)):
            self.all_tree.item(str(idx), values=row, tags=(tag,))
        else:
            self.all_tree.insert("", "end", iid=str(idx), values=row, tags=(tag,))
        if result.is_unresolved:
            if self.pending_tree.exists(str(idx)):
                self.pending_tree.item(str(idx), values=row, tags=(tag,))
            else:
                self.pending_tree.insert("", "end", iid=str(idx),
                                         values=row, tags=(tag,))
        elif self.pending_tree.exists(str(idx)):
            self.pending_tree.delete(str(idx))
        tree = (self.pending_tree if self.tabs.index(self.tabs.select()) == 1
                else self.all_tree)
        if str(idx) in tree.selection():
            self._set_detail(_detail(result))

    def save_json(self) -> None:
        if not self.results:
            return
        destination = filedialog.asksaveasfilename(
            title="검사 결과 JSON 저장",
            initialfile="PlayDock_Identity_Test_Results_v0.10.1.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not destination:
            return
        ordered = [self.results[idx].to_dict() for idx in sorted(self.results)]
        payload = {
            "program": "PlayDock Identity Tester",
            "version": VERSION,
            "created_at_local": datetime.now().astimezone().isoformat(),
            "files": ordered,
            "unresolved": [
                item for item in ordered if item["is_unresolved"]
            ],
            "statistics": {
                "tested": len(ordered),
                "identified": sum(not r["is_unresolved"] for r in ordered),
                "unresolved": sum(r["is_unresolved"] for r in ordered),
            },
            "privacy": "개인 검사 결과. 공개 GitHub 업로드 대상 아님",
        }
        try:
            Path(destination).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))
            return
        messagebox.showinfo(
            "저장 완료",
            f"전체 {len(ordered)}개, 별도 보류 {len(payload['unresolved'])}개를 "
            "하나의 JSON에 구분해 저장했습니다.",
        )


def self_test() -> int:
    """Windows PyInstaller 패키지 내부에서 무인터넷/무 GUI 기능 자가 검사."""
    try:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "Moon Valley [RJ09999777].zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("Moon Valley/Moon Valley.exe", b"NO-EXEC")
                zf.writestr("Moon Valley/Moon Valley_Data/data.bin", b"data")
                zf.writestr(
                    "Moon Valley/README.txt",
                    "Game Title: Moon Valley\n品番: RJ09999777".encode("utf-8"),
                )
            seen = []
            def fake_search(q: str) -> SearchDecision:
                seen.append(q)
                if q == "RJ09999777":
                    return SearchDecision(
                        "confirmed_game", q, proposed_title="Moon Valley",
                        dlsite_code="RJ09999777",
                    )
                return SearchDecision("lookup_unavailable", q)
            result = analyze_identity(path, classifier=fake_search)
            assert result.status == "identified", result
            assert result.product_code == "RJ09999777"
            assert "Moon Valley" in seen
            assert "RJ09999777" in seen
            assert result.scan.readme_state == "ok"
            assert result.to_dict()["post_identity_checks"] == "deferred"
            multi = root / "Collection.zip"
            with zipfile.ZipFile(multi, "w") as zf:
                zf.writestr("Collection/Game A.exe", b"a")
                zf.writestr("Collection/Game B.exe", b"b")
            scan = analyze_identity(multi, classifier=lambda q: SearchDecision(
                "lookup_unavailable", q,
            ))
            assert scan.scan.exe_ambiguous, scan
            assert not any(c.source == "main_exe" for c in scan.scan.clues)
        print("PlayDock v0.10 self-test: passed", flush=True)
        return 0
    except Exception:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    app = SimpleIdentityApp()
    app.mainloop()
