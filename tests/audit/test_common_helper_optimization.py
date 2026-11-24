"""Shared helper identity and behavior; keep old import names usable."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import setup_wizard
import install_management
import ai_providers
import artwork
from models.game_codes import STEAM_MARKED
from services.official_work_service import STEAM_MARKED as service_pattern
from integrations.official_lookup.code_only import STEAM_MARKED as lookup_pattern, steam_ids_in

def test_desktop_helper_shared_and_fallback(monkeypatch,tmp_path):
    assert setup_wizard.desktop_directory is install_management.desktop_directory
    monkeypatch.setattr(install_management.sys,"platform","other")
    monkeypatch.setenv("USERPROFILE",str(tmp_path))
    assert setup_wizard.desktop_directory()==tmp_path/"Desktop"

@pytest.mark.parametrize("raw", ['{"title":"Game"}','  {"title":"Game"}  ','\x60\x60\x60json\n{"title":"Game"}\n\x60\x60\x60','\x60\x60\x60\n{"title":"Game"}\n\x60\x60\x60'])
def test_json_helper_shared_and_equivalent(raw):
    assert artwork._decode_json is ai_providers._extract_json
    assert artwork._decode_json(raw)=={"title":"Game"}

def test_invalid_json_still_raises():
    with pytest.raises(json.JSONDecodeError):
        artwork._decode_json("invalid")

@pytest.mark.parametrize("name,expected",[
    ("Game Steam 1091500.zip",("1091500",)),
    ("Game AppID:123456.7z",("123456",)),
    ("SteamAppID=1091500 + Steam ID 123456.rar",("1091500","123456")),
    ("Game 1091500.zip",()),
    ("v1.2.3 build 12345.zip",()),
    ("Steam 012345.zip",()),
])
def test_steam_marker_shared_and_no_bare_number_guess(name,expected):
    assert service_pattern is STEAM_MARKED is lookup_pattern
    assert steam_ids_in(name)==expected
