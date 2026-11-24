"""Verify the import-only cleanup against the audited source. Never import the app."""
from __future__ import annotations
import argparse
import ast
import collections
import json
import re
from pathlib import Path
from audit_source import git, module_name


def tree(ref):
    return {
        p: meta.split()[2]
        for item in git("ls-tree", "-r", "-z", ref).decode("utf-8").split("\0")
        if item for meta, p in [item.split("\t", 1)] if meta.split()[1] == "blob"
    }


def source(ref, path):
    return git("show", f"{ref}:{path}").decode("utf-8-sig")


def imported(node):
    if isinstance(node, ast.Import):
        return [(a.name, a.asname or a.name.split(".")[0]) for a in node.names]
    if isinstance(node, ast.ImportFrom):
        return [("." * node.level + (node.module or "") + ":" + a.name, a.asname or a.name)
                for a in node.names]
    return []


def imports(root):
    return collections.Counter(pair for node in root.body for pair in imported(node))


def nonimports(root):
    return ast.dump(ast.Module(body=[n for n in root.body if not isinstance(n, (ast.Import, ast.ImportFrom))],
                               type_ignores=[]), include_attributes=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ref", required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    old = tree(a.ref)
    new = tree("HEAD")
    inventory = json.loads(a.inventory.read_text(encoding="utf-8"))
    changed = [path for path in old if old[path] != new.get(path)]
    production = [path for path in changed if path.startswith("src/playdock/") or path in {"app.py", "title_editor.py"}]
    # New audit scripts, CI definitions and documentation are allowed; existing
    # production files must differ only by deletion of top-level import names.
    errors, rows = [], []
    for path in production:
        if path not in new:
            errors.append(f"Deleted production file: {path}")
            continue
        before, after = ast.parse(source(a.ref, path)), ast.parse(source("HEAD", path))
        if nonimports(before) != nonimports(after):
            errors.append(f"Non-import AST changed: {path}")
        removed = imports(before) - imports(after)
        added = imports(after) - imports(before)
        if added:
            errors.append(f"Unexpected imported bindings: {path}: {list(added)}")
        # Preserve ordering of all retained import bindings.
        ordered_old = [pair for n in before.body for pair in imported(n)]
        ordered_new = [pair for n in after.body for pair in imported(n)]
        remaining = list(ordered_old)
        for pair in removed.elements():
            remaining.remove(pair)
        if remaining != ordered_new:
            errors.append(f"Retained import order changed: {path}")
        candidates = {x["name"] for x in inventory["files"][path]["unused_import_candidates"]}
        for module, name in removed.elements():
            if name not in candidates:
                errors.append(f"Not an audited candidate: {path}: {name}")
            rows.append({"path":path,"module":module,"name":name})
    deleted = sorted(set(old) - set(new))
    if deleted:
        errors.append(f"Deleted tracked files: {deleted}")
    unexpected = [p for p in changed if p not in production]
    if unexpected:
        errors.append(f"Unexpected existing file changes: {unexpected}")

    # Inspect explicit imports, module attribute references and exact string
    # paths in all tracked Python sources (including tests and experiments).
    targets = collections.defaultdict(set)
    for row in rows:
        target = module_name(row["path"])
        targets[target].add(row["name"])
        if row["path"].startswith("src/playdock/"):
            targets["playdock." + target].add(row["name"])
    references = []
    for path in old:
        if not path.endswith(".py"):
            continue
        raw = source(a.ref,path)
        parsed = ast.parse(raw,filename=path)
        aliases = {}
        for n in ast.walk(parsed):
            if isinstance(n, ast.ImportFrom):
                module = n.module or ""
                if module in targets:
                    for item in n.names:
                        if item.name in targets[module] or item.name == "*":
                            references.append(dict(path=path,line=n.lineno,reference=f"from {module} import {item.name}"))
            elif isinstance(n, ast.Import):
                for item in n.names:
                    if item.name in targets:
                        aliases[item.asname or item.name] = item.name
        for n in ast.walk(parsed):
            if isinstance(n, ast.Attribute):
                prefix = ast.unparse(n.value)
                target = aliases.get(prefix)
                if target and n.attr in targets[target]:
                    references.append(dict(path=path,line=n.lineno,reference=f"{target}.{n.attr}"))
            elif isinstance(n, ast.Constant) and isinstance(n.value,str):
                for target, names in targets.items():
                    for name in names:
                        if re.search(r"(?<![\w.])"+re.escape(target+"."+name)+r"(?!\w)",n.value):
                            references.append(dict(path=path,line=n.lineno,reference=f"string: {target}.{name}"))
    # A reference may be a negative assertion or explanatory string. Flag it
    # for explicit review rather than interpreting it as proof of use.
    core = [r for r in rows if r["path"].startswith("src/playdock/")]
    retained = []
    removed_keys = {(r["path"],r["name"]) for r in core}
    for path, record in inventory["files"].items():
        if path.startswith("src/playdock/"):
            for candidate in record["unused_import_candidates"]:
                if (path,candidate["name"]) not in removed_keys:
                    retained.append({"path":path,"name":candidate["name"],
                        "reason":"Preserve compatibility exports or defer legacy/ambiguous bindings."})
    report = dict(baseline=a.ref,source_inventory=inventory["baseline"],head=git("rev-parse","HEAD").decode().strip(),
                  changed_production_files=production,removed=rows,core_removed=len(core),
                  core_retained=retained,reference_candidates=references,errors=errors)
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"import_cleanup.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("IMPORT_ONLY_FILES",len(production))
    print("REMOVED_BINDINGS",len(rows),"CORE_REMOVED",len(core),"CORE_RETAINED",len(retained))
    print("ROOT_REMOVED",len(rows)-len(core))
    print("EXTERNAL_REFERENCE_CANDIDATES",len(references))
    for ref in references: print("REVIEW",ref)
    for error in errors: print("ERROR",error)
    if errors or len(core)+len(retained)!=97:
        raise SystemExit(1)
    print("IMPORT_AST_VERIFIED")


if __name__=="__main__":
    main()
