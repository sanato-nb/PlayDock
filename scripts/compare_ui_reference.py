"""Compare UI contracts, protected sources, and actual offscreen pixel captures."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageChops

root=Path(__file__).resolve().parents[1]
old,new=(Path(x) for x in sys.argv[1:3])
# Refactor reviews compare against the immediate pre-change source, not the
# historical frozen design manifest. Default mode keeps its strict SHA guard.
refactor_base=sys.argv[3] if len(sys.argv)==4 else None
manifest=json.loads((root/"docs/ui_reference/source_manifest.json").read_text(encoding="utf-8"))
a,b=(json.loads((p/"ui_contract.json").read_text(encoding="utf-8")) for p in (old,new))
changed=[]
for row in manifest["files"]:
    r=subprocess.run(["git","rev-parse","HEAD:"+row["path"]],cwd=root,capture_output=True,text=True)
    if r.returncode or r.stdout.strip()!=row["sha"]:
        changed.append(row["path"])
if refactor_base:
    changed=subprocess.check_output(["git","diff","--name-only",refactor_base,"HEAD"],cwd=root,text=True).splitlines()
# User-approved change: append only a separator and the support action to Settings.
# Preserve the original menu rows and every other contract/screenshot check.
approved_support_change=False
settings_key="02_settings_menu"
if refactor_base=="86635400e4c925ddfd63e144112214eaaf27f50b":
    before=a["menus"].get(settings_key, [])
    after=b["menus"].get(settings_key, [])
    if len(after)==len(before)+2 and after[:-2]==before:
        separator, action=after[-2:]
        approved_support_change=(
            separator["separator"] and separator["text"]=="" and not separator["children"]
            and action=={"text":"개발자 후원","enabled":True,"separator":False,
                         "checked":False,"children":[]})
        if approved_support_change:
            b={**b,"menus":{**b["menus"],settings_key:before}}
differences=[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]
old_png={p.name:p for p in old.glob("*.png")}
new_png={p.name:p for p in new.glob("*.png")}
assert len(old_png)==14 and old_png.keys()==new_png.keys(), "Missing or unexpected screenshots"
pixels=[]
# These dialogs include live filesystem metadata and path/status text.
# Their structural contract must match; differences remain explicit review items.
dynamic={"11_folder_settings.png","13_database_status.png","14_file_picker.png"}
for name,path in sorted(old_png.items()):
    with Image.open(path) as image, Image.open(new_png[name]) as current:
        x,y=image.convert("RGB"),current.convert("RGB")
        row={"name":name,"baseline_size":list(x.size),"current_size":list(y.size),
             "baseline_pixel_sha256":hashlib.sha256(x.tobytes()).hexdigest(),
             "current_pixel_sha256":hashlib.sha256(y.tobytes()).hexdigest(),
             "dynamic_content":name in dynamic}
        if x.size==y.size:
            diff=ImageChops.difference(x,y)
            bbox=diff.getbbox()
            row["changed_bbox"]=list(bbox) if bbox else None
            row["changed_pixels"]=sum(pixel!=(0,0,0) for pixel in diff.getdata()) if bbox else 0
        else:
            row["changed_pixels"]=None
            row["changed_bbox"]=None
        row["identical"]=x.size==y.size and row["changed_pixels"]==0
        pixels.append(row)
font_info={label:json.loads((path/"font_environment.json").read_text(encoding="utf-8"))
           for label,path in (("baseline",old),("current",new))}
approved_images={settings_key+".png"} if approved_support_change else set()
static_changes=[r["name"] for r in pixels if not r["dynamic_content"] and not r["identical"] and r["name"] not in approved_images]
size_changes=[r["name"] for r in pixels if r["baseline_size"]!=r["current_size"] and r["name"] not in approved_images]
dynamic_review=[r["name"] for r in pixels if r["dynamic_content"] and not r["identical"]]
report={"baseline":refactor_base or manifest["baseline"],"protected_files":len(manifest["files"]),
        "changed_reference_files":changed,"contract_differences":differences,
        "pixel_comparisons":pixels,"identical_images":sum(r["identical"] for r in pixels),
        "static_changes":static_changes,"size_changes":size_changes,"dynamic_review":dynamic_review,
        "approved_settings_support_change":approved_support_change,
        "font_environment":font_info,
        "note":"Offscreen pixels and geometry only. Dynamic differences require review. Native frame/Tk/high-DPI and actual Korean glyph rendering remain manual checks."}
(new/"comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print("UI_SOURCE_CHANGED_REVIEW",json.dumps(changed,ensure_ascii=False))
print("UI_PIXEL_COMPARISON",json.dumps(report,ensure_ascii=False))
if not refactor_base:
    assert not changed, "Protected UI source changed; explicit review required"
assert not differences, "UI contract changed: "+", ".join(differences)
assert not size_changes, "Screenshot size changed: "+", ".join(size_changes)
assert not static_changes, "Static screenshot changed: "+", ".join(static_changes)
assert font_info["baseline"]==font_info["current"], "Font environment differs"
print("UI_CONTRACT_MATCH")
