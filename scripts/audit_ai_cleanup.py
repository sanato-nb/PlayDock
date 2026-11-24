"""Verify stage 2-C retired AI entrypoints and preserve other production sources."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from audit_import_cleanup import tree, source
from audit_source import git

BASELINE = "49d7de255ded0b8937513f4abaec11d8b83d2387"
ALLOWED = {"app.py", "src/playdock/ui/dialogs/library.py", "src/playdock/artwork.py",
           "src/playdock/ai_providers.py", "src/playdock/controllers/title_editor.py",
           "src/playdock/services/title_workers.py"}
RETIRED = {"SettingsDialog", "settings_dialog", "generate_ai_art", "image_bytes", "IMAGE_URL"}
ENDPOINTS = ("/v1/images/generations", "openrouter.ai/api/v1/images", "responseModalities")


def main():
    before, after = tree(BASELINE), tree("HEAD")
    assert not set(before) - set(after), "Unexpected deletion"
    protected = {p for p in before if p.startswith(("src/playdock/", "experiments/")) or
                 p in {"app.py", "title_editor.py", "title_editor_entry.py", "setup_wizard.py",
                       "uninstall_wizard.py", "requirements.txt"}}
    changes = {p for p in protected if before[p] != after[p]}
    assert changes == ALLOWED, changes
    findings = []
    for path in sorted(protected):
        if not path.endswith(".py") or path.startswith("experiments/"):
            continue
        code = source("HEAD", path)
        for node in ast.walk(ast.parse(code, filename=path)):
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Name)):
                names = [node.id if isinstance(node, ast.Name) else node.name]
            elif isinstance(node, ast.Attribute):
                names = [node.attr]
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names]
            # image_bytes is also the legitimate cache byte-count field.
            # Detect only definitions/imports and calls to the retired API;
            # leave inventory counters and stats.image_bytes intact.
            matched = RETIRED.intersection(names)
            if "image_bytes" in matched and isinstance(node, (ast.Name, ast.Attribute)):
                matched.remove("image_bytes")
            if isinstance(node, ast.Call) and (
                    (isinstance(node.func, ast.Name) and node.func.id == "image_bytes") or
                    (isinstance(node.func, ast.Attribute) and node.func.attr == "image_bytes")):
                matched.add("image_bytes")
            if matched:
                findings.append((path, node.lineno, sorted(matched)))
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(endpoint in node.value for endpoint in ENDPOINTS):
                    findings.append((path, node.lineno, "image endpoint"))
    assert not findings, findings
    # Protect text recommendation, stored credentials/config handling and image cache
    # code from unintended changes; only explicit removed symbols may disappear.
    for path, names in {
        "src/playdock/ai_providers.py": ["get_secret", "set_secret", "current_provider",
            "current_models", "save_provider_settings", "recommend_title", "_text_response", "http_json"],
        "src/playdock/artwork.py": ["save_image", "discover_local", "ai_game_title",
            "_archive_artwork_candidates", "_find_artwork_library", "_local_images"],
    }.items():
        a, b = ({n.name: ast.dump(n, include_attributes=False)
                 for n in ast.parse(source(ref,path)).body if isinstance(n, ast.FunctionDef)}
                for ref in (BASELINE, "HEAD"))
        for name in names:
            assert a[name] == b[name], (path, name)
    out = Path("audit_output")
    out.mkdir(exist_ok=True)
    report = {"baseline":BASELINE, "head":git("rev-parse","HEAD").decode().strip(),
              "changed_production_files":sorted(changes),
              "unchanged_protected_files":len(protected-changes),
              "removed_symbols":sorted(RETIRED),
              "net_lines_removed":sum(len(source(BASELINE,p).splitlines())-
                                      len(source("HEAD",p).splitlines()) for p in changes),
              "findings":findings}
    (out/"ai_cleanup.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("AI_CLEANUP_VERIFIED")


if __name__ == "__main__":
    main()
