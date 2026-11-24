"""Audit declared dependencies without importing application code."""
from pathlib import Path
import ast
import importlib.metadata as metadata
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=Path(sys.argv[1])
paths=subprocess.check_output(["git","ls-files","-z"],cwd=ROOT).decode("utf-8").split("\0")
entrypoints={"app.py","title_editor.py","title_editor_entry.py","setup_wizard.py","uninstall_wizard.py"}
mapping={"PySide6":"PySide6","py7zr":"py7zr","Pillow":"PIL","keyring":"keyring",
         "pyzipper":"pyzipper","send2trash":"send2trash","rarfile":"rarfile","ddgs":"ddgs"}
groups={"production":{},"tests":{},"experiments":{},"scripts":{}}
qt_modules=set()
dynamic=[]
for path in paths:
    if not path.endswith(".py"):
        continue
    group=("production" if path in entrypoints or path.startswith("src/playdock/") else
           path.split("/",1)[0])
    if group not in groups:
        continue
    source=(ROOT/path).read_text(encoding="utf-8-sig")
    for node in ast.walk(ast.parse(source,filename=path)):
        if isinstance(node,ast.Import):
            imports=[alias.name for alias in node.names]
        elif isinstance(node,ast.ImportFrom) and node.level==0:
            imports=[node.module or ""]
            if node.module=="PySide6":
                imports.extend("PySide6."+a.name for a in node.names)
        else:
            imports=[]
        for module in imports:
            for package, prefix in mapping.items():
                if module==prefix or module.startswith(prefix+"."):
                    groups[group].setdefault(package,[]).append({"path":path,"line":node.lineno,"module":module})
            if module.startswith("PySide6.") and group=="production":
                qt_modules.add(module.split(".")[1])
        if group=="production" and isinstance(node,ast.Call):
            func=node.func
            name=func.id if isinstance(func,ast.Name) else func.attr if isinstance(func,ast.Attribute) else ""
            if name in {"import_module","__import__","find_spec"}:
                dynamic.append({"path":path,"line":node.lineno,"call":ast.unparse(node)[:200]})
requirements=[line.strip() for line in (ROOT/"requirements.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
assert {re.split(r"[<>=!~ ]",line,1)[0] for line in requirements}==set(mapping)
installed=[]
for dist in metadata.distributions():
    files=dist.files or []
    total=0
    for file in files:
        try:
            p=dist.locate_file(file)
            if p.is_file():
                total+=p.stat().st_size
        except OSError:
            pass
    installed.append({"name":dist.metadata["Name"],"version":dist.version,"recorded_file_bytes":total})
report={"commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "requirements":requirements,"imports":groups,"production_qt_modules":sorted(qt_modules),
        "dynamic_import_candidates":dynamic,"installed_distributions":sorted(installed,key=lambda r:r["name"].lower())}
OUTPUT.parent.mkdir(parents=True,exist_ok=True)
OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print("DIRECT_DEPENDENCY_IMPORT_COUNTS",json.dumps({p:len(groups["production"].get(p,[])) for p in mapping}))
print("PRODUCTION_QT_MODULES",sorted(qt_modules))
print("DYNAMIC_IMPORT_CANDIDATES",len(dynamic))
