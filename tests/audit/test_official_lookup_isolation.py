"""Check that production starts and resolves official IDs without the experiments package."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

def test_production_imports_and_lookup_without_experiment_package():
    code = r"""
import importlib.abc
import sys

class BlockExperiments(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "experiments" or fullname.startswith("experiments."):
            raise AssertionError("Production imports experiments: " + fullname)
        return None

sys.meta_path.insert(0, BlockExperiments())
import app
from services.catalog_collection_service import CatalogCollector
from workers.identity_artwork import IdentityArtworkThread
from integrations.official_lookup.code_only import InputItem, check, Work
from integrations.official_lookup.detector import Product
calls = []
def fetch(code):
    calls.append(code)
    return Product(code, "Official title", "", "maniax",
                   "https://www.dlsite.com/maniax/work/=/product_id/" + code + ".html")
def never(*args):
    raise AssertionError("Unexpected network request")
assert check(InputItem("Unknown.zip", "archive"), fetcher=never,
             steam_fetcher=never).status == "excluded"
result = check(InputItem("Game RJ123456 Steam 1091500.zip", "archive"),
               fetcher=fetch, steam_fetcher=never)
assert result.selected_store == "dlsite"
assert result.works[0].title == "Official title"
assert calls == ["RJ123456"]
assert not any(n == "experiments" or n.startswith("experiments.") for n in sys.modules)
"""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src/playdock"), str(ROOT)))
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, check=True, timeout=45)
