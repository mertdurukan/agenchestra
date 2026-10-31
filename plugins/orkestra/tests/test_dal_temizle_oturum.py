"""Dal temizliği canlı oturumun dalını atlar (ADR-0125, yalnız okuma)."""
import json
import os
import subprocess
import sys
import time

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import dal_temizle  # noqa: E402


def git(yol, *a):
    return subprocess.run(["git", "-C", yol, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def _depo(tmp_path):
    d = str(tmp_path / "depo")
    os.makedirs(os.path.join(d, ".claude", "orkestra", "oturumlar"))
    git(tmp_path, "init", "-q", "-b", "main", d)
    git(d, "commit", "-q", "--allow-empty", "-m", "x")
    git(d, "branch", "birlesmis")
    return d


def _kayit(d, dal, gorulme):
    yol = os.path.join(d, ".claude", "orkestra", "oturumlar", "cccc3333-0000.json")
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"konum": {"depo": "x", "dal": dal, "worktree": "y", "gorulme": gorulme}}, f)


def test_canli_oturumun_dali_aday_olmaz(tmp_path):
    d = _depo(tmp_path)
    assert dal_temizle.adaylar(d)["aday"] == ["birlesmis"]  # kayıt yokken eski davranış
    _kayit(d, "birlesmis", time.time())
    assert dal_temizle.adaylar(d)["aday"] == []


def test_bayat_kayit_dali_korumaz(tmp_path):
    d = _depo(tmp_path)
    _kayit(d, "birlesmis", time.time() - 3 * 3600)
    assert dal_temizle.adaylar(d)["aday"] == ["birlesmis"]
