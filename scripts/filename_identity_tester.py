"""PlayDock 게임 이름·품번 전용 독립 판독기 v0.11.

기존 v0.10 내부 분석 GUI와 무관: 압축파일은 열지 않고 basename만 검색한다.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from queue import Queue, Empty
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from experiments.dlsite_detector.filename_only import (
    VERSION, FilenameIdentityResult, extract_filename_clues, identify_filename,
)
from experiments.dlsite_detector.filename_web_search import worker_main
from experiments.dlsite_detector.detector import Product

FILT = [
    ("게임 압축파일", "*.zip *.7z *.rar"),
    ("ZIP 파일", "*.zip"), ("7z 파일", "*.7z"), ("RAR 파일", "*.rar"),
]
UNRESOLVED = {"likely", "multiple", "unidentified", "search_error"}


def details(result: FilenameIdentityResult) -> str:
    x = result.extracted
    out = [
        "판독: " + result.label,
        "파일명: " + x.archive_name,
        "추출 게임명: " + (x.game_name or "없음"),
        "추출 DLsite 품번: " + (", ".join(x.product_codes) or "없음"),
        "추출 Steam App ID: " + (", ".join(x.steam_ids) or "없음"),
        "선택된 외부 작품/단서: " + (result.best_title or "없음"),
        "찾은 상품번호: " + (result.product_id or "없음"),
        "이유: " + result.reason, "",
        "[실제로 조회한 검색어]",
    ]
    out += [" · " + x for x in result.lookups] or [" · 없음"]
    if result.candidates:
        out += ["", "[외부 후보]"]
        for c in result.candidates:
            out += [
                " · " + c.platform + " | " + c.title,
                "   ID: " + (c.product_id or "-"),
                "   조회 방식: " + c.source,
                "   공식 제목 일치: " + ("예" if c.name_matches else "아니오"),
                "   " + c.url,
            ]
            if c.notes:
                out.append("   주의: " + c.notes)
    if result.search_providers:
        out += ["", "[실제 검색 서비스 결과]"]
        for p in result.search_providers:
            out.append(
                " · " + str(p.get("provider", "?")) + " "
                + str(p.get("state", "?")) + " / "
                + str(p.get("result_count", 0)) + "건 중 관련 "
                + str(p.get("relevant_count", "?")) + "건 / 제외 "
                + str(p.get("rejected_count", "?")) + "건 / "
                + str(p.get("seconds", 0)) + "초"
            )
            if p.get("error"):
                out.append("   검색 오류: " + str(p.get("error", ""))[:200])
            for ignored in p.get("discarded_examples", [])[:2]:
                out.append("   제외: " + str(ignored.get("title", ""))[:140])
    if result.web_raw_results:
        out += ["", f"[웹 검색 결과 {len(result.web_raw_results)}건]"]
        for hit in result.web_raw_results:
            out += [" · " + hit.get("title", ""), "   " + hit.get("url", "")]
    elif any(q.startswith("제목 ") for q in result.lookups):
        out += ["", "[웹 검색 결과] 0건 (검색 서비스 로그 확인 필요)"]
    if result.rejected_pages:
        out += ["", "[공식 정보 대조 후 제외된 페이지]"]
        for page in result.rejected_pages:
            out += [
                " · " + page.get("reason", "제외"),
                "   공식 이름: " + page.get("official_title", "미확인"),
                "   " + page.get("url", ""),
            ]
    if result.errors:
        out += ["", "[검색 장애]"]
        out += [" · " + e for e in result.errors]
    out += [
        "", "[검사 범위]",
        " · 압축파일 내부 목록·EXE·README·게임 데이터·버전·번역 정보 미검사",
        " · 공식 상품 등록과 파일명이 일치해도 실제 압축파일의 진위는 미확인",
        f" · 소요시간: {result.elapsed_seconds:.2f}초",
    ]
    return "\n".join(out)


class FilenameTesterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PlayDock 파일명 전용 게임 정체 판독 · " + VERSION)
        self.geometry("1100x760")
        self.minsize(850, 570)
        self.queue: Queue = Queue()
        self.items: list[str] = []
        self.results: dict[int, FilenameIdentityResult] = {}
        self.active = False
        self.stop_signal = threading.Event()
        self.status = tk.StringVar(value="압축파일을 선택하거나 파일명 목록을 붙여넣으세요.")
        self.current = tk.StringVar(value="0개 선택")
        self._setup_style()
        self._layout()
        self.after(100, self._poll)

    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Malgun Gothic", 10))
        style.configure("TButton", padding=(11, 8))
        style.configure("Treeview", rowheight=28)
        style.configure("Treeview.Heading", font=("Malgun Gothic", 10, "bold"))
        style.configure("TNotebook.Tab", padding=(12, 6))

    def _layout(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="게임 이름 + 품번 검색 (파일명 전용)",
                  font=("Malgun Gothic", 17, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="압축파일을 열지 않음 · 파일명에서 이름과 RJ/BJ/VJ/EJ·Steam ID 추출 · 공식 코드 직접 조회 또는 제목 검색 한 번",
        ).pack(anchor="w", pady=(2, 12))
        bar = ttk.Frame(root)
        bar.pack(fill="x", pady=4)
        self.browse = ttk.Button(bar, text="압축파일 선택", command=self.browse_archives)
        self.browse.pack(side="left", padx=(0, 6))
        self.paste = ttk.Button(bar, text="파일명 붙여넣기", command=self.paste_names)
        self.paste.pack(side="left", padx=(0, 6))
        self.clear = ttk.Button(bar, text="목록 초기화", command=self.clear_items)
        self.clear.pack(side="left", padx=(0, 6))
        self.go = ttk.Button(bar, text="인터넷 판독 시작", command=self.start)
        self.go.pack(side="left", padx=(0, 6))
        self.retry = ttk.Button(bar, text="미확인 재검사",
                                command=self.retry_failed, state="disabled")
        self.retry.pack(side="left", padx=(0, 6))
        self.stop = ttk.Button(bar, text="다음 파일부터 중단",
                               command=self.ask_stop, state="disabled")
        self.stop.pack(side="left", padx=(0, 6))
        self.export = ttk.Button(bar, text="JSON 저장",
                                 command=self.export_json, state="disabled")
        self.export.pack(side="right")
        ttk.Label(root, textvariable=self.current).pack(anchor="w", pady=(10, 3))
        self.progress = ttk.Progressbar(root, maximum=100, value=0)
        self.progress.pack(fill="x")
        ttk.Label(root, textvariable=self.status, wraplength=1000).pack(
            anchor="w", pady=(5, 9))
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)
        self.full_table = self._make_table("전체 결과")
        self.pending_table = self._make_table("미확인·보류")
        ttk.Label(root, text="선택한 파일의 추출·검색 근거").pack(anchor="w", pady=(8, 3))
        self.detail = tk.Text(root, height=14, wrap="word",
                              font=("Consolas", 10), padx=10, pady=8)
        self.detail.pack(fill="both", expand=True)
        self.detail.configure(state="disabled")

    def _make_table(self, tabname):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=tabname)
        columns = ("archive", "extracted", "code", "status", "official", "time")
        view = ttk.Treeview(frame, show="headings", columns=columns, height=10)
        opts = [
            ("archive", "압축파일명", 250),
            ("extracted", "추출 게임명", 205),
            ("code", "품번", 135),
            ("status", "정체 판정", 140),
            ("official", "외부 작품명·단서", 220),
            ("time", "검색시간", 85),
        ]
        for key, heading, width in opts:
            view.heading(key, text=heading)
            view.column(key, width=width, minwidth=70, stretch=key in {
                "archive", "extracted", "official"
            })
        sc = ttk.Scrollbar(frame, orient="vertical", command=view.yview)
        view.configure(yscrollcommand=sc.set)
        view.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")
        view.bind("<<TreeviewSelect>>", lambda _, t=view: self._on_select(t))
        return view

    def browse_archives(self):
        files = filedialog.askopenfilenames(
            title="게임 압축파일 선택 — 파일명만 읽습니다", filetypes=FILT)
        self._add_items([Path(s).name for s in files])

    def paste_names(self):
        win = tk.Toplevel(self)
        win.title("압축파일 이름을 한 줄에 하나씩 입력")
        win.geometry("700x450")
        ttk.Label(win, text="ZIP/7z/RAR 실제 파일 없이 이름만으로 판독할 수 있습니다.").pack(
            anchor="w", padx=12, pady=8)
        box = tk.Text(win, wrap="none", font=("Consolas", 11))
        box.pack(fill="both", expand=True, padx=12, pady=6)
        actions = ttk.Frame(win)
        actions.pack(fill="x", padx=12, pady=7)

        def add():
            names = [s.strip() for s in box.get("1.0", "end").splitlines()
                     if s.strip()]
            self._add_items(names)
            win.destroy()

        ttk.Button(actions, text="목록에 추가", command=add).pack(side="right")

    def _add_items(self, values):
        seen = {s.casefold() for s in self.items}
        for raw in values:
            name = str(raw).replace("\\", "/").split("/")[-1].strip()
            if (len(name) <= 260 and name
                    and name.casefold().endswith((".zip", ".7z", ".rar"))
                    and name.casefold() not in seen):
                self.items.append(name)
                seen.add(name.casefold())
        self._render_rows()

    def clear_items(self):
        if self.active:
            return
        self.items.clear()
        self.results.clear()
        self._render_rows()
        self._set_detail("")

    def _render_rows(self):
        for t in (self.full_table, self.pending_table):
            t.delete(*t.get_children())
        for idx, name in enumerate(self.items):
            res = self.results.get(idx)
            if res is None:
                self.full_table.insert("", "end", iid=str(idx),
                                       values=(name, "-", "-", "대기", "-", "-"))
            else:
                self._show_result(idx, res)
        self.current.set(f"압축파일명 {len(self.items)}개")
        self.export.configure(state="normal" if self.results else "disabled")
        self.retry.configure(state="normal" if any(
            r.is_unresolved for r in self.results.values()
        ) else "disabled")

    def _on_select(self, tree):
        sel = tree.selection()
        if not sel:
            return
        result = self.results.get(int(sel[0]))
        self._set_detail(details(result) if result else "아직 검사하지 않았습니다.")

    def _set_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def start(self):
        if self.active:
            return
        if not self.items:
            messagebox.showwarning("파일명 필요", "압축파일 이름을 먼저 추가하세요.")
            return
        if not messagebox.askyesno(
            "인터넷 조회 동의",
            "압축파일명에서 추출한 게임 이름과 품번만 인터넷 검색에 사용합니다.\n"
            "압축파일을 열거나 전체 로컬 경로·파일 내용은 전송하지 않습니다.\n"
            "검색 결과는 게임 바이너리의 진위 확인이 아닙니다.\n\n시작할까요?",
        ):
            return
        self.results.clear()
        self._render_rows()
        self._start_worker(tuple(range(len(self.items))))

    def retry_failed(self):
        if self.active:
            return
        idx = tuple(i for i, r in self.results.items() if r.is_unresolved)
        if idx and messagebox.askyesno("재검색", f"미확인·보류 {len(idx)}개를 재검색할까요?"):
            self._start_worker(idx)

    def _start_worker(self, indices):
        self.active = True
        self.stop_signal.clear()
        self._count = len(indices)
        self.progress.configure(value=0)
        self.go.configure(state="disabled")
        self.browse.configure(state="disabled")
        self.paste.configure(state="disabled")
        self.clear.configure(state="disabled")
        self.retry.configure(state="disabled")
        self.stop.configure(state="normal")
        self.export.configure(state="disabled")
        thread = threading.Thread(target=self._worker, args=(indices,), daemon=True)
        thread.start()

    def ask_stop(self):
        self.stop_signal.set()
        self.status.set("현재 조회가 끝나면 다음 파일부터 중단합니다.")

    def _worker(self, indices):
        try:
            for completed, i in enumerate(indices):
                if self.stop_signal.is_set():
                    break
                self.queue.put(("status", self.items[i] + " 검색 중"))
                try:
                    result = identify_filename(self.items[i])
                    self.queue.put(("result", i, result))
                except Exception as exc:
                    self.queue.put(("error", i, type(exc).__name__))
                self.queue.put(("progress", completed + 1, len(indices)))
        finally:
            self.queue.put(("done",))

    def _poll(self):
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "status":
                    self.status.set(item[1])
                elif kind == "result":
                    self.results[item[1]] = item[2]
                    self._show_result(item[1], item[2])
                elif kind == "error":
                    # 오류도 JSON과 보류 목록에 기록하므로 다음 검사에서 확인 가능.
                    idx, reason = item[1], item[2]
                    from experiments.dlsite_detector.filename_only import FilenameIdentityResult
                    result = FilenameIdentityResult(
                        self.items[idx], extract_filename_clues(self.items[idx]),
                        "search_error", "", "", "판독 프로그램 오류: " + reason,
                        (), (), (reason,), 0.0,
                    )
                    self.results[idx] = result
                    self._show_result(idx, result)
                elif kind == "progress":
                    self.progress.configure(value=100 * item[1] / max(1, item[2]))
                    self.current.set(f"{item[1]}/{item[2]}개 검색 완료")
                elif kind == "done":
                    self.active = False
                    for c in (self.go, self.browse, self.paste, self.clear):
                        c.configure(state="normal")
                    self.stop.configure(state="disabled")
                    self.export.configure(state="normal" if self.results else "disabled")
                    self.retry.configure(state="normal" if any(
                        r.is_unresolved for r in self.results.values()
                    ) else "disabled")
                    match = sum(r.status == "official_match" for r in self.results.values())
                    catalog = sum(r.status == "catalog_found" for r in self.results.values())
                    web = sum(r.status == "web_candidate" for r in self.results.values())
                    remain = sum(r.is_unresolved for r in self.results.values())
                    self.status.set(
                        f"완료: 공식 이름 일치 {match}개 · 품번 상품 발견 "
                        f"{catalog}개 · 웹 단서 {web}개 · 보류/미확인 "
                        f"{remain}개 (압축파일 내용 미인증)"
                    )
        except Empty:
            pass
        self.after(100, self._poll)

    def _show_result(self, idx, result):
        cl = result.extracted
        row = (
            result.filename, cl.game_name or "-",
            ", ".join(cl.product_codes + tuple("Steam " + s for s in cl.steam_ids)) or "-",
            result.label, result.best_title or "-",
            f"{result.elapsed_seconds:.2f}초",
        )
        if self.full_table.exists(str(idx)):
            self.full_table.item(str(idx), values=row)
        else:
            self.full_table.insert("", "end", iid=str(idx), values=row)
        if result.is_unresolved:
            if self.pending_table.exists(str(idx)):
                self.pending_table.item(str(idx), values=row)
            else:
                self.pending_table.insert("", "end", iid=str(idx), values=row)
        elif self.pending_table.exists(str(idx)):
            self.pending_table.delete(str(idx))
        for table in (self.full_table, self.pending_table):
            if str(idx) in table.selection():
                self._set_detail(details(result))

    def export_json(self):
        if not self.results:
            return
        path = filedialog.asksaveasfilename(
            title="판독 결과 저장",
            initialfile="PlayDock_Filename_Identity_v0.11.4.json",
            defaultextension=".json", filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        records = [r.to_dict() for _, r in sorted(self.results.items())]
        payload = {
            "program": "PlayDock Filename-only Identity Tester",
            "version": VERSION,
            "created_at_local": datetime.now().astimezone().isoformat(),
            "scope": "archive_filename_only",
            "files": records,
            "unresolved": [r for r in records if r["is_unresolved"]],
            "statistics": {
                "tested": len(records),
                "official_name_matches": sum(
                    r["status"] == "official_match" for r in records),
                "catalog_found_by_id": sum(
                    r["status"] == "catalog_found" for r in records),
                "web_name_candidates": sum(
                    r["status"] == "web_candidate" for r in records),
                "web_raw_result_total": sum(
                    len(r["web_raw_results"]) for r in records),
                "rejected_official_pages": sum(
                    len(r.get("rejected_pages", [])) for r in records),
                "provider_errors": sum(
                    p.get("state") == "error" for r in records
                    for p in r["search_providers"]),
                "unresolved": sum(r["is_unresolved"] for r in records),
            },
            "privacy": "개인 검사 결과. 공개 저장소에 업로드하지 않습니다.",
        }
        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))
            return
        messagebox.showinfo("저장 완료", f"{len(records)}개 결과를 저장했습니다.")


def self_test() -> int:
    """빌드된 EXE의 무인터넷 자체 진단. ZIP 파일은 하나도 열지 않음."""
    try:
        calls = []
        def fake_lookup(code):
            calls.append(code)
            return Product(
                code, "Moon Valley", "ADV", "maniax",
                f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html",
            )
        def no_web(_):
            raise AssertionError("작품번호 조회 성공 후 웹 검색을 수행하면 안 됩니다")
        result = identify_filename(
            "Moon Valley [RJ09999123] [한국어].7z",
            dlsite_lookup=fake_lookup,
            web_search=no_web,
        )
        assert result.status == "official_match", result
        assert result.extracted.game_name == "Moon Valley"
        assert calls == ["RJ09999123"]
        assert result.to_dict()["archive_contents_inspected"] is False
        no_code = identify_filename(
            "BunnyHero [v0.5.2].zip", web_search=lambda _: [],
        )
        assert no_code.status == "unidentified"
        assert no_code.extracted.game_name == "BunnyHero"
        from experiments.dlsite_detector.filename_page_rank import page_score
        # 합성 데이터로 짧은 제목 오인과 개발자 홈 제외를 자체 진단.
        assert page_score(
            "NOR", "Son of Nor on Steam",
            "https://store.steampowered.com/app/264000/Son_of_Nor/"
        ) == 0
        assert page_score(
            "Moon Valley", "moonvalley - itch.io",
            "https://moonvalley.itch.io/"
        ) == 0
        # 실제 PyInstaller 패키징 환경에서도 별도 워커 프로세스가
        # GUI를 다시 띄우지 않고 정상 기동하는지 무인터넷 검증.
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "worker_probe.txt"
            cmd = ([sys.executable, "--filename-worker-probe", str(out)]
                   if getattr(sys, "frozen", False)
                   else [sys.executable, "-m", "scripts.filename_identity_tester",
                         "--filename-worker-probe", str(out)])
            p = subprocess.run(
                cmd, timeout=20, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, check=False,
            )
            assert p.returncode == 0
            assert out.read_text(encoding="utf-8") == "worker-ok"
        print("PlayDock filename-only v0.11.4 self-test: passed", flush=True)
        return 0
    except Exception:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--filename-worker-probe":
        Path(sys.argv[2]).write_text("worker-ok", encoding="utf-8")
        sys.exit(0)
    # PyInstaller --windowed 실행 시에도 UI 없이 별도 검색 워커를 기동.
    if len(sys.argv) == 4 and sys.argv[1] == "--filename-web-worker":
        sys.exit(worker_main(sys.argv[2], sys.argv[3]))
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    FilenameTesterApp().mainloop()
