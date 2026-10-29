"""Eklenti MCP kaydı (ayarlar/mcp_kimlik.json, ADR-0097): 16 yeni girdi şemadan geçer ve değer taşımaz."""
import importlib
import json
import os
import re
import sys

EKLENTI = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(EKLENTI, "scripts"))
mk = importlib.import_module("mcp_kimlik")

YENI = ["memory", "filesystem", "context7", "playwright", "chrome-devtools", "github", "repomix", "serena", "beads",
        "mcp-chrome", "git-mcp", "browsermcp", "desktop-commander", "claude-context", "windows-mcp", "task-master"]
HAM = open(os.path.join(EKLENTI, "ayarlar", "mcp_kimlik.json"), encoding="utf-8").read()


def test_16_yeni_ad_kayitta_ve_toplam_19(tmp_path):
    kayit = mk.kayit_oku(str(tmp_path))
    assert set(YENI) <= set(kayit) and len(kayit) == 19


def test_caveman_kayitta_degil(tmp_path):
    assert "caveman" not in mk.kayit_oku(str(tmp_path))


def test_ortam_yalniz_anahtar_adi(tmp_path):
    for ad, g in mk.kayit_oku(str(tmp_path)).items():
        for ortam_adi, anahtar in (g.get("ortam") or {}).items():
            assert re.fullmatch(r"([A-Za-z0-9_-]+\.)?[A-Za-z_][A-Za-z0-9_]*", anahtar), ad


def test_kayitta_sir_oneki_yok():
    for onek in ("fc-", "ghp_", "sk-", "github_pat_"):
        assert not re.search(r"(?<![A-Za-z0-9])" + re.escape(onek), HAM), onek   # "task-master" içindeki "sk-" sır değildir


def test_docker_env_yalniz_ad_degersiz(tmp_path):
    k = mk.kayit_oku(str(tmp_path))["github"]["komut"]
    i = k.index("-e")
    assert k[i + 1] == "GITHUB_PERSONAL_ACCESS_TOKEN" and "=" not in k[i + 1]


def test_on_kosullu_girdilerde_gerek(tmp_path):
    k = mk.kayit_oku(str(tmp_path))
    assert "docker" in k["github"]["gerek"] and "uv" in k["serena"]["gerek"] and "bd" in k["beads"]["gerek"]
    assert "uvx" in k["windows-mcp"]["gerek"]


def test_claude_context_iki_servis(tmp_path):
    o = mk.kayit_oku(str(tmp_path))["claude-context"]["ortam"]
    assert {v.split(".")[0] for v in o.values()} == {"zilliz", "openai"}
