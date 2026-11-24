"""Read-only static inventory of tracked Python sources. No application imports."""
from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ("app.py", "setup_wizard.py", "uninstall_wizard.py",
               "title_editor.py", "title_editor_entry.py")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def module_name(path):
    parts = path.removesuffix(".py").split("/")
    if parts[:2] == ["src", "playdock"]:
        parts = parts[2:]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def group(path):
    if path.startswith("src/playdock/"):
        parts = path.split("/")
        return parts[2] if len(parts) > 3 else "core-root"
    return path.split("/")[0] if "/" in path else "root"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    ref = git("rev-parse", args.ref).decode().strip()
    tree = git("ls-tree", "-r", "-l", "-z", ref).decode("utf-8")
    tracked = []
    for record in tree.split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        mode, kind, sha, size = meta.split()
        if kind == "blob":
            tracked.append(dict(path=path, sha=sha, bytes=int(size)))
    paths = [r["path"] for r in tracked if r["path"].endswith(".py")]
    names = {}
    for path in paths:
        name = module_name(path)
        if name:
            names[name] = path
            if path.startswith("src/playdock/"):
                names["playdock." + name] = path
    records, errors, clones = {}, [], collections.defaultdict(list)
    edges = collections.defaultdict(set)
    reverse = collections.defaultdict(set)
    layers = collections.defaultdict(lambda: dict(files=0, lines=0, bytes=0))
    for item in tracked:
        path = item["path"]
        if path not in paths:
            continue
        raw = git("show", f"{ref}:{path}")
        expected = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if expected != item["sha"]:
            errors.append({"path": path, "error": "blob SHA mismatch"})
            continue
        try:
            source = raw.decode("utf-8-sig")
            parsed = ast.parse(source, filename=path)
        except (SyntaxError, UnicodeError) as exc:
            errors.append({"path": path, "error": str(exc)})
            continue
        record = {**item, "lines": len(source.splitlines()), "imports": [],
                  "definitions": [], "unused_import_candidates": [], "dynamic_markers": []}
        layer = layers[group(path)]
        layer["files"] += 1
        layer["lines"] += record["lines"]
        layer["bytes"] += len(raw)
        # All scopes are considered for references, including annotations and
        # string references; candidates deliberately err toward retention.
        loads = {n.id for n in ast.walk(parsed) if isinstance(n, ast.Name)}
        string_text = "\n".join(n.value for n in ast.walk(parsed)
                                if isinstance(n, ast.Constant) and isinstance(n.value, str))
        for node in ast.walk(parsed):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", None) or ""
                level = getattr(node, "level", 0)
                if level:
                    package = module_name(path).split(".")
                    if not path.endswith("/__init__.py"):
                        package = package[:-1]
                    package = package[:max(0, len(package)-level+1)]
                    module = ".".join([*package, module]).strip(".")
                for alias in node.names:
                    target_name = alias.name if isinstance(node, ast.Import) else module
                    submodule = module + "." + alias.name
                    target = names.get(submodule) if isinstance(node, ast.ImportFrom) else None
                    target = target or names.get(target_name)
                    if target and target != path:
                        edges[path].add(target)
                        reverse[target].add(path)
                    record["imports"].append(dict(line=node.lineno, module=target_name,
                                                  name=alias.name, target=target))
                    binding = alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name)
                    if (node in parsed.body and binding != "*" and binding not in loads
                            and binding not in string_text and module != "__future__"
                            and not path.endswith("__init__.py")):
                        record["unused_import_candidates"].append(dict(line=node.lineno, name=binding,
                            caution="May be a re-export or dynamic/build reference; manually verify."))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                record["definitions"].append(dict(line=node.lineno, name=node.name,
                                                   kind=type(node).__name__))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = node.body
                    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                        body = body[1:]
                    if sum(1 for statement in body for _ in ast.walk(statement)) >= 25:
                        key = ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)
                        clones[hashlib.sha256(key.encode()).hexdigest()].append(
                            dict(path=path, line=node.lineno, function=node.name))
            elif isinstance(node, ast.Call):
                func = ast.unparse(node.func)
                if func in {"__import__", "importlib.import_module", "sys.path.insert",
                            "sys.path.append", "sqlite3.connect"} or func.startswith("subprocess."):
                    record["dynamic_markers"].append(dict(line=node.lineno, function=func))
        records[path] = record

    def reachable(roots):
        seen, pending = set(), list(roots)
        while pending:
            path = pending.pop()
            if path not in seen:
                seen.add(path)
                pending.extend(edges[path] - seen)
        return seen

    live = reachable(ENTRYPOINTS)
    for path, record in records.items():
        record["incoming"] = sorted(reverse[path])
        record["entrypoint_reachable"] = path in live
        if path.startswith("src/playdock/"):
            record["classification"] = "keep_or_relocate" if path in live else "manual_reachability_review"
        else:
            record["classification"] = "preserve_test_experiment_script_or_entrypoint"

    cross = [{"source": p, "target": t} for p in sorted(edges) for t in sorted(edges[p])
             if (p.startswith("src/playdock/") or p in ENTRYPOINTS) and t.startswith("experiments/")]
    duplicates = [v for v in clones.values() if len(v) > 1]
    production = [r for p, r in records.items() if p.startswith("src/playdock/")]
    unreachable = [r for r in production if not r["entrypoint_reachable"] and not r["path"].endswith("__init__.py")]
    report = dict(baseline=ref, tracked=tracked, python_count=len(paths),
                  parsed_count=len(records), errors=errors, layers=dict(layers),
                  entrypoints=list(ENTRYPOINTS), files=records, experiment_edges=cross,
                  reachable_experiments=sorted(p for p in live if p.startswith("experiments/")),
                  duplicate_body_candidates=duplicates,
                  limitations=["Static imports are not execution proof.",
                               "Dynamic imports, package initializers, Qt signals, build references and external callers require review.",
                               "Unused imports and identical AST bodies are only candidates; do not delete automatically."])
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = [
        "# 소스코드 정적 감사 결과", "", f"- 기준: {ref}",
        f"- 전체 추적 파일: {len(tracked)}", f"- Python: {len(paths)} / 분석 성공: {len(records)}",
        f"- 본체: {len(production)}개 / {sum(r['lines'] for r in production)}줄",
        f"- 분석 오류: {len(errors)}",
        f"- 본체 미사용 import 후보: {sum(len(r['unused_import_candidates']) for r in production)}",
        f"- 본체 직접 실험 의존: {len(cross)}",
        f"- 진입점에서 도달한 실험 모듈: {len(report['reachable_experiments'])}",
        f"- 전체 동일 AST 함수 본문 후보 그룹: {len(duplicates)}",
        "", "## 계층별 규모", "", "| 계층 | 파일 | 줄 | 바이트 |", "|---|---:|---:|---:|",
        *[f"| {k} | {v['files']} | {v['lines']} | {v['bytes']} |" for k,v in sorted(layers.items())],
        "", "## 본체에서 실험으로 직접 import", "",
        *[f"- {x['source']} → {x['target']}" for x in cross],
        "", "## 본체 정적 미도달 후보 (삭제 금지)", "",
        *[f"- {r['path']} (역참조: {', '.join(r['incoming']) or '없음'})" for r in unreachable],
        "", "## 본체 파일별 분류", "", "| 파일 | 줄 | 내부 import | 역참조 | 분류 |", "|---|---:|---:|---:|---|",
        *[f"| {r['path']} | {r['lines']} | {len(edges[r['path']])} | {len(r['incoming'])} | {r['classification']} |" for r in production],
        "", "정적 분석 후보는 미사용 확정이 아님. 실제 동작, 테스트, 빌드 및 외부 호출 확인 후 판단."
    ]
    (args.out / "summary_KO.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary[:summary.index("## 본체 파일별 분류")]))
    print("AUDIT_COMPLETE" if not errors and len(records) == len(paths) else "AUDIT_INCOMPLETE")
    if errors or len(records) != len(paths):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
