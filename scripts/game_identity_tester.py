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
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from experiments.dlsite_detector.archive_identity import (
    identify_archive, recheck_archive_search, search_recheck_needed,
)
from experiments.dlsite_detector.enhanced_search import (
    enhanced_classify_game, fast_enhanced_classify_game,
)
from experiments.dlsite_detector.archive_inspector import inspect_archive
from experiments.dlsite_detector.identity_verifier import verify_identity
from experiments.dlsite_detector.search_session import SearchSession
from experiments.dlsite_detector.internal_metadata import inspect_readme_metadata

VERSION = "0.9-test"
CATALOG_KO = {
    "official_game_found": "공식 작품 발견",
    "web_candidate": "웹 후보",
    "multiple_candidates": "복수 후보",
    "conflicting_official_ids": "공식 ID 충돌",
    "lookup_error": "검색 오류",
    "skipped_due_to_cooldown": "검색 생략 · 재검사",
    "unverified_evidence": "웹 근거 미확인",
    "not_found": "작품 미발견",
    "not_checked": "조회 안 함",
}
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
        # GUI 세션 안에만 보관하는 이전 근거/원본 stat (파일명·메타 데이터 외부 전송 없음).
        self._previous: dict[int, tuple] = {}
        self._last_fast_mode = True
        self.queue: Queue = Queue()
        self.thread: threading.Thread | None = None
        self.stop_requested = threading.Event()
        self.online = tk.BooleanVar(value=True)
        self.fast_mode = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="게임 압축파일을 선택한 뒤 분석 시작을 누르세요.")
        self.progress = tk.StringVar(value="선택된 파일 없음")
        self.stage_status = tk.StringVar(value="현재 단계: 대기")
        self.running_online = True
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
        self.retry_button = ttk.Button(
            toolbar, text="검색 실패 항목 재검사", command=self.retry_search_errors,
            state="disabled",
        )
        self.retry_button.pack(side="left", padx=(0, 8))
        self.save_button = ttk.Button(
            toolbar, text="결과 저장", command=self.save_report, state="disabled",
        )
        self.save_button.pack(side="right")

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            options,
            text="파일명·내부 구조·README 제한 확인 → 통합 검색 → 교차검증",
            variable=self.online,
        ).pack(side="left")
        ttk.Checkbutton(
            options,
            text="빠른 검색 (기본·파일당 최대 3개 검색어)",
            variable=self.fast_mode,
        ).pack(side="left", padx=(14, 0))

        # 진행 표시를 위쪽에 고정: 결과 목록이나 긴 상세 내용에 가려지지 않음.
        ttk.Label(outer, textvariable=self.progress).pack(anchor="w", pady=(3, 3))
        self.bar = ttk.Progressbar(
            outer, maximum=100, value=0, mode="determinate",
        )
        self.bar.pack(fill="x", pady=(0, 5))
        ttk.Label(outer, textvariable=self.stage_status).pack(anchor="w", pady=(0, 2))
        ttk.Label(outer, textvariable=self.status,
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 8))
        columns = ("file", "catalog", "verdict", "title", "encryption", "scan")
        list_frame = ttk.Frame(outer)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        self.tree = ttk.Treeview(
            list_frame, columns=columns, show="headings", height=9,
        )
        for key, text, width in (
            ("file", "압축파일", 270),
            ("catalog", "작품 조회", 130),
            ("verdict", "내부 대조", 100),
            ("title", "게임명 후보", 225),
            ("encryption", "암호화", 95),
            ("scan", "내부 확인", 110),
        ):
            self.tree.heading(key, text=text)
            self.tree.column(key, minwidth=85, width=width, stretch=key in ("file", "title"))
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
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

    def _show_progress(self, complete: int, stage: int = 1) -> None:
        """정확한 완료 파일 비율 + 현재 6단계 진행 위치.

        단계 진행률은 소요시간의 추정치가 아님을 화면에 명시한다.
        """
        total = len(self.paths)
        if total <= 0:
            self.bar.configure(value=0)
            self.progress.set("선택된 파일 없음")
            return
        # 비암호화 파일은 1 → 3 → 4 → 5 → 2 → 6 순서.
        # 기존 단계 번호 순서를 기준으로 계산하면 검색을 시작할 때
        # 진행바가 뒤로 움직이므로 실제 실행 순서로 변환한다.
        stage_positions = {1: 0, 3: 1, 4: 2, 5: 3, 2: 4, 6: 5}
        step_fraction = (
            stage_positions.get(stage, 0) / 6
            if self.running_online else
            (0.5 if stage >= 5 else 0)
        )
        fraction = (complete + (step_fraction if complete < total else 0)) / total
        percent = max(0, min(100, fraction * 100))
        self.bar.configure(value=percent)
        self.progress.set(
            f"{complete} / {total}개 검사 완료  |  전체 약 {percent:.1f}% "
            "(파일 개수·단계 기준, 시간 예측 아님)"
        )

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
        self._previous.clear()
        self.retry_button.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.progress.set("선택된 파일 없음")
        self.stage_status.set("현재 단계: 대기")
        self.bar.configure(value=0)
        self.save_button.configure(state="disabled")
        self._set_detail("아직 분석 결과가 없습니다.")

    def _render_files(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self._previous.clear()
        self.retry_button.configure(state="disabled")
        for idx, path in enumerate(self.paths):
            self.tree.insert("", "end", iid=str(idx),
                             values=(path.name, "대기", "대기", "-", "-", "-"))
        self.progress.set(f"{len(self.paths)}개 파일 선택됨 · 판독 시작 대기")
        self.stage_status.set("현재 단계: 대기")
        self.bar.configure(value=0)
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
                "선택한 압축파일 이름과 내부 근거에서 추출한 작품명·품번을 "
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
        self.running_online = mode
        self.bar.configure(maximum=100, value=0)
        self._show_progress(0, 1)
        for ctl in (self.choose_button, self.clear_button, self.start_button):
            ctl.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.save_button.configure(state="disabled")
        self.status.set("분석 중… (대용량 압축 목록이나 인터넷 검색은 오래 걸릴 수 있습니다)")
        paths = tuple(self.paths)
        fast_mode = self.fast_mode.get()
        self._last_fast_mode = fast_mode
        self.retry_button.configure(state="disabled")
        self.thread = threading.Thread(
            target=self._worker, args=(paths, mode, fast_mode), daemon=True,
        )
        self.thread.start()

    def request_stop(self) -> None:
        self.stop_requested.set()
        self.status.set("중단 요청됨. 진행 중인 파일이 완료되면 다음 파일부터 중지합니다.")

    @staticmethod
    def _online_result(path, stages, verified, session, fast_mode: bool) -> dict:
        data = {
            "mode": "stages_1_to_6",
            "search_mode": "fast" if fast_mode else "detailed",
            "search_session": session.metrics.to_dict(),
            "archive_name": path.name,
            "stages_1_to_5": stages.to_dict(),
            "verification": verified.to_dict(),
        }
        return {
            "name": path.name,
            "catalog": CATALOG_KO.get(
                verified.catalog_status, verified.catalog_status,
            ),
            "verdict": verified.label,
            "title": verified.proposed_title or (
                " / ".join(verified.candidate_titles) or "-"
            ),
            "encryption": verified.encryption_state,
            "scan": verified.inspection_state,
            "detail": IdentityTesterApp._format_verification(verified, stages),
            "payload": data,
        }

    def retry_search_errors(self) -> None:
        """GUI 수동 재검사: 오류/생략 파일만, 내부 목록은 안전할 때 재사용."""
        if self.thread and self.thread.is_alive():
            return
        targets = tuple(
            (idx, self.paths[idx], report, signature)
            for idx, (report, signature) in sorted(self._previous.items())
            if search_recheck_needed(report)
        )
        if not targets:
            messagebox.showinfo("재검사", "추가 검색이 필요한 이전 결과가 없습니다.")
            return
        approved = messagebox.askokcancel(
            "검색 실패 항목 재검사",
            f"{len(targets)}개 파일에서 실패·생략된 작품 검색을 다시 확인합니다.\n"
            "파일 크기와 수정시각이 같으면 이전 내부 근거를 재사용합니다.\n"
            "새로운 작품 검색어는 인터넷에 전송됩니다. 진행할까요?",
        )
        if not approved:
            return
        self.stop_requested.clear()
        for ctl in (self.choose_button, self.clear_button, self.start_button,
                    self.retry_button):
            ctl.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set(f"이전 검색 오류 {len(targets)}개 파일 재검사 중")
        self.thread = threading.Thread(
            target=self._retry_worker,
            args=(targets, self._last_fast_mode), daemon=True,
        )
        self.thread.start()

    def _retry_worker(self, targets: tuple, fast_mode: bool) -> None:
        session = SearchSession(
            fast_enhanced_classify_game if fast_mode else enhanced_classify_game,
        )
        try:
            for position, (idx, path, previous, signature) in enumerate(targets, 1):
                if self.stop_requested.is_set():
                    break
                started = time.perf_counter()
                before = session.metrics
                self.queue.put(("retry_progress", position, len(targets), path.name))
                def on_stage(stage: int, label: str) -> None:
                    self.queue.put(("retry_step", idx, stage, label))
                try:
                    stages = recheck_archive_search(
                        path, previous, classifier=session,
                        expected_stat=signature,
                        progress_callback=on_stage,
                        max_search_queries=3 if fast_mode else 6,
                    )
                    on_stage(6, "실패 검색 재조회 후 최종 검증 중")
                    verified = verify_identity(stages)
                    result = self._online_result(
                        path, stages, verified, session, fast_mode,
                    )
                    result["payload"]["recheck"] = {
                        "local_evidence_reused": stages.local_evidence_reused,
                        "only_failed_queries_retried": stages.local_evidence_reused,
                    }
                    delta = {
                        key: getattr(session.metrics, key) - getattr(before, key)
                        for key in ("requests", "cache_hits",
                                    "avoided_requests", "network_errors")
                    }
                    result["payload"]["search_delta"] = delta
                    duration = round(time.perf_counter() - started, 3)
                    result["duration_seconds"] = duration
                    result["payload"]["analysis_seconds"] = duration
                    stages.stage_timings_ms["total_ms"] = round(duration * 1000, 3)
                    result["payload"]["stages_1_to_5"]["stage_timings_ms"] = (
                        stages.stage_timings_ms.copy()
                    )
                    result["detail"] = (
                        f"재검사 소요시간: {duration:.2f}초\n"
                        f"기존 내부 근거 재사용: {stages.local_evidence_reused}\n\n"
                        + result["detail"]
                    )
                    st = path.stat()
                    new_signature = (st.st_size, st.st_mtime_ns)
                    self.queue.put((
                        "retry_result", idx, result, stages, new_signature,
                    ))
                except Exception as exc:
                    self.queue.put((
                        "retry_error", path.name,
                        f"{type(exc).__name__}: {exc}",
                    ))
        finally:
            self.queue.put(("retry_done", session.metrics.to_dict()))

    def _worker(self, paths: tuple[Path, ...], online: bool,
                fast_mode: bool = True) -> None:
        # 한 번의 검증 배치에서는 동일 작품 ID/제목의 검색 결과를 재사용한다.
        session = SearchSession(
            fast_enhanced_classify_game if fast_mode else enhanced_classify_game,
        ) if online else None
        try:
            for idx, path in enumerate(paths):
                if self.stop_requested.is_set():
                    break
                started = time.perf_counter()
                stages = None
                before = session.metrics if session else None
                self.queue.put(("progress", idx, path.name))
                def on_stage(stage: int, label: str) -> None:
                    # 작업 스레드에서 tkinter를 직접 건드리지 않는다.
                    self.queue.put(("step", idx, stage, label))
                try:
                    if not path.is_file() or path.is_symlink():
                        raise ValueError("일반 로컬 파일이 아니거나 파일을 찾을 수 없습니다.")
                    if online:
                        stages = identify_archive(
                            path, allow_metadata=True, progress_callback=on_stage,
                            classifier=session,
                            max_search_queries=(3 if fast_mode else 6),
                        )
                        on_stage(6, "외부 작품과 내부 근거 교차검증 중")
                        verified = verify_identity(stages)
                        result = self._online_result(
                            path, stages, verified, session, fast_mode,
                        )
                    else:
                        on_stage(4, "오프라인 압축파일 내부 목록 확인 중")
                        index = inspect_archive(path)
                        on_stage(5, "오프라인 소형 설정파일 분석 중")
                        meta = inspect_readme_metadata(path)
                        data = {
                            "mode": "offline_metadata_only",
                            "archive_name": path.name,
                            "inspection": index.to_dict(),
                            "metadata": meta.to_dict(),
                        }
                        result = {
                            "name": path.name,
                            "catalog": "조회 안 함",
                            "verdict": "내부 근거만",
                            "title": " / ".join(meta.title_candidates) or "-",
                            "encryption": "encrypted" if index.encrypted else "미확인" if index.state == "unavailable" else "clear",
                            "scan": index.state,
                            "detail": self._format_offline(index, meta),
                            "payload": data,
                        }
                except Exception as exc:
                    result = {
                        "name": path.name, "catalog": "분석 오류",
                        "verdict": "오류", "title": "-",
                        "encryption": "-", "scan": "실패",
                        "detail": f"파일 분석 오류: {type(exc).__name__}: {exc}",
                        "payload": {"mode": "error", "archive_name": path.name,
                                    "error": type(exc).__name__},
                    }
                duration = round(time.perf_counter() - started, 3)
                if session and before:
                    after = session.metrics
                    result["payload"]["search_delta"] = {
                        key: getattr(after, key) - getattr(before, key)
                        for key in (
                            "requests", "cache_hits",
                            "avoided_requests", "network_errors",
                        )
                    }
                result["duration_seconds"] = duration
                result["payload"]["analysis_seconds"] = duration
                if stages is not None:
                    stages.stage_timings_ms["total_ms"] = round(duration * 1000, 3)
                    result["payload"]["stages_1_to_5"]["stage_timings_ms"] = (
                        stages.stage_timings_ms.copy()
                    )
                result["detail"] = (
                    f"분석 소요시간: {duration:.2f}초\n\n" + result["detail"]
                )
                signature = None
                if stages is not None and path.is_file():
                    st = path.stat()
                    signature = (st.st_size, st.st_mtime_ns)
                self.queue.put(("result", idx, result, stages, signature))
        finally:
            self.queue.put(("done", session.metrics.to_dict() if session else {}))

    @staticmethod
    def _format_verification(verified, stages) -> str:
        out = [
            f"작품 조회: {CATALOG_KO.get(verified.catalog_status, verified.catalog_status)}",
            f"작품 등록 제목: {verified.catalog_title or '미확인'}",
            f"공식 작품 식별자: {', '.join(verified.catalog_product_ids) or '없음'}",
            f"외부 등록 상품 유형: {verified.catalog_release_type}",
            f"로컬 압축파일 대조: {verified.label}",
            "",
            "[서로 다른 외부 상품의 관계 (미확인)]",
            *(
                [f"  • {s}" for s in verified.candidate_relationships]
                if verified.candidate_relationships
                else ["  • 공식 출처로 입증된 관계 없음"]
            ),
            "",
            f"판정: {verified.label}",
            f"게임명 후보: {verified.proposed_title or ', '.join(verified.candidate_titles) or '없음'}",
            f"암호화: {verified.encryption_state}",
            f"파일 구성: {verified.package_assessment}",
            f"한국어 근거: {verified.localization_assessment}",
            f"내부 목록: {verified.inspection_state}",
            f"README 제한 단서: {verified.metadata_state}",
            "",
            "[로컬 파일명 ↔ 외부 후보 대조 (정체 인증 아님)]",
            *(
                [f"  • {s}" for s in verified.local_name_support]
                if verified.local_name_support
                else ["  • 대조 가능한 정확한 이름 근거 없음 또는 복수 후보"]
            ),
            "",
            "[단계별 소요시간 (ms)]",
            *[
                f"  {key}: {value:.3f}"
                for key, value in stages.stage_timings_ms.items()
            ],
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
        out.extend([
            "",
            "[1~5단계 웹 작품 검색 시도]",
        ])
        for attempt in stages.attempts[:12]:
            out.append(
                f"  {attempt.basis}: {attempt.query} → {attempt.decision.status}"
            )
            if attempt.decision.reason:
                out.append(f"    근거: {attempt.decision.reason[:350]}")
        if stages.inspection:
            out.extend([
                "",
                "[압축파일 내부 목록에서 발견한 후보]",
                "  " + (", ".join(stages.inspection.title_candidates[:8]) or "없음"),
            ])
        out.append("")
        out.append("※ 자동 분류는 원본 파일이나 PlayDock 라이브러리를 수정하지 않습니다.")
        return "\n".join(out)

    @staticmethod
    def _format_offline(inspection, meta) -> str:
        out = [
            f"인터넷 검색 없는 내부 조사 (작품 정체 확정 아님)",
            f"압축 내부 목록: {inspection.state} / {inspection.member_count}개 항목",
            f"암호화 표시: {inspection.encrypted}",
            f"README 제한 읽기: {meta.state} / {meta.inspected_files}개 파일 읽음",
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
                    self.status.set(f"검사 중인 파일: {name}")
                    if self.running_online:
                        self.stage_status.set(
                            f"현재 파일 {idx+1}/{len(self.paths)} · 단계 준비 중"
                        )
                    self._show_progress(idx, 1)
                elif event[0] == "step":
                    _, idx, stage, label = event
                    step_text = (
                        (f"{ {1:1, 3:2, 4:3, 5:4, 2:5, 6:6}.get(stage, 1) }/6"
                         f" (원래 {stage}단계)")
                        if self.running_online
                        else ("1/2단계" if stage == 4 else "2/2단계")
                    )
                    self.stage_status.set(
                        f"현재 파일 {idx+1}/{len(self.paths)} · {step_text}: {label}"
                    )
                    self._show_progress(idx, stage)
                elif event[0] == "result":
                    _, idx, row, stages, signature = event
                    row["file_index"] = idx
                    self.rows.append(row)
                    if stages is not None and signature is not None:
                        self._previous[idx] = (stages, signature)
                    if self.tree.exists(str(idx)):
                        self.tree.item(str(idx), values=(
                            row["name"], row["catalog"], row["verdict"],
                            row["title"], row["encryption"], row["scan"],
                        ))
                        self.tree.selection_set(str(idx))
                    self._set_detail(row["detail"])
                    self._show_progress(len(self.rows), 1)
                    self.stage_status.set(
                        f"방금 검사 완료: {row['name']} · {row['verdict']} "
                        f"· {row['duration_seconds']:.1f}초"
                    )
                    self.save_button.configure(state="normal")
                elif event[0] == "retry_progress":
                    _, position, total, name = event
                    self.status.set(
                        f"재검사 {position}/{total} · {name}"
                    )
                elif event[0] == "retry_step":
                    _, idx, stage, label = event
                    self.stage_status.set(
                        f"재검사 {idx + 1}번 파일 · {stage}단계 · {label}"
                    )
                elif event[0] == "retry_result":
                    _, idx, row, stages, signature = event
                    row["file_index"] = idx
                    for position, prior_row in enumerate(self.rows):
                        if prior_row.get("file_index") == idx:
                            self.rows[position] = row
                            break
                    self._previous[idx] = (stages, signature)
                    if self.tree.exists(str(idx)):
                        self.tree.item(str(idx), values=(
                            row["name"], row["catalog"], row["verdict"],
                            row["title"], row["encryption"], row["scan"],
                        ))
                        self.tree.selection_set(str(idx))
                    self._set_detail(row["detail"])
                elif event[0] == "retry_error":
                    _, name, error = event
                    self.status.set(f"검색 재검사 실패 ({name}): {error}")
                elif event[0] == "retry_done":
                    for ctl in (self.choose_button, self.clear_button, self.start_button):
                        ctl.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.retry_button.configure(
                        state="normal" if any(
                            search_recheck_needed(report)
                            for report, _ in self._previous.values()
                        ) else "disabled"
                    )
                    self.status.set(
                        f"검색 오류 재검사 종료 · 웹 요청 {event[1].get('requests', 0)}회"
                    )
                    self.stage_status.set("재검사 종료")
                elif event[0] == "done":
                    for ctl in (self.choose_button, self.clear_button, self.start_button):
                        ctl.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.retry_button.configure(
                        state="normal" if self.running_online and any(
                            search_recheck_needed(report)
                            for report, _ in self._previous.values()
                        ) else "disabled"
                    )
                    suffix = " (사용자 중지)" if self.stop_requested.is_set() else ""
                    metrics = event[1]
                    m = (
                        f" 웹 조회 {metrics.get('requests', 0)}회, "
                        f"캐시 재사용 {metrics.get('cache_hits', 0)}회, "
                        f"장애로 생략 {metrics.get('avoided_requests', 0)}회."
                        if metrics else ""
                    )
                    self.status.set(
                        f"{len(self.rows)}개 파일 처리 완료{suffix}.{m} "
                        "필요하면 결과 저장을 누르세요."
                    )
                    self.stage_status.set("검사 종료")
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
            if row.get("file_index") == index:
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
                        stream, fieldnames=("name", "catalog", "verdict", "title", "encryption", "scan"),
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
            z.writestr("Game/Game.ini", "Title=Legacy Game (must not read)\n")
            z.writestr("Game/steam_appid.txt", "1621540\n")
            z.writestr("Game/README.txt",
                       "Game Title: Sample Test Game\nSteam App ID: 1621540\n")
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
        assert verified.verdict == "needs_review", verified.verdict
        assert verified.catalog_status == "official_game_found"
        assert verified.local_identity_status == "needs_review"
        assert result.metadata.title_candidates == ("Sample Test Game",)
        assert result.metadata.inspected_files == 1
        assert not verified.automatic_binding_allowed
    return 0


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    IdentityTesterApp().mainloop()
