"""orkestra mcp liste|config|kur (ADR-0096): config yalnız sarmalayıcı komutunu taşır, sır değeri hiçbir çıktıda yok."""
import json
import os
import subprocess
import sys

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
from komutlar import mcp as M  # noqa: E402

CLI = os.path.join(KOK, "scripts", "orkestra.py")
SIR = "fc-SAHTE-p@ss/w:rd#9"


def ortam(tmp_path, kimlik=True):
    proje = tmp_path / "proje"
    (proje / ".claude" / "orkestra").mkdir(parents=True)
    kok = tmp_path / "kimlik"
    (kok / "testproje").mkdir(parents=True)
    if kimlik:
        (kok / "testproje" / "firecrawl.env").write_text(f"FIRECRAWL_API_KEY={SIR}\n", encoding="utf-8")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(proje), "ORKESTRA_KIMLIK_DIZINI": str(kok),
           "ORKESTRA_KIMLIK_PROJE": "testproje", "PYTHONUTF8": "1"}
    env.pop("FIRECRAWL_API_KEY", None)
    return env, proje


def cli(env, *args):
    return subprocess.run([sys.executable, CLI, "mcp", *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=60, cwd=env["CLAUDE_PROJECT_DIR"])


def test_config_json_yalniz_sarmalayici_komutu_sir_yok(tmp_path):
    env, _ = ortam(tmp_path)
    p = cli(env, "config")
    assert p.returncode == 0, p.stderr
    assert SIR not in p.stdout and SIR not in p.stderr
    d = json.loads(p.stdout)["mcpServers"]
    assert {"markitdown", "firecrawl", "sequential-thinking"} <= set(d)
    for ad, g in d.items():
        assert g["command"] == "python" and g["args"][-1] == ad and g["args"][0].endswith("mcp_kimlik.py")
        assert "env" not in g                       # anahtar config'in env alanına hiç yazılmaz


def test_config_claude_code_hedefi(tmp_path):
    env, _ = ortam(tmp_path)
    p = cli(env, "config", "--mcp", "firecrawl", "--hedef", "claude-code")
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("claude mcp add --scope user firecrawl -- python ") and SIR not in p.stdout


def test_liste_kimlik_durumu_var_yok_degersiz(tmp_path):
    env, _ = ortam(tmp_path, kimlik=True)
    p = cli(env, "liste")
    assert "firecrawl: kimlik var" in p.stdout and "markitdown: kimlik gerekmez" in p.stdout
    assert SIR not in p.stdout + p.stderr
    env2, _ = ortam(tmp_path / "bos", kimlik=False)
    p2 = cli(env2, "liste")
    assert "firecrawl: kimlik yok: firecrawl.FIRECRAWL_API_KEY" in p2.stdout


def test_bilinmeyen_mcp_reddedilir(tmp_path):
    env, _ = ortam(tmp_path)
    p = cli(env, "config", "--mcp", "yok-boyle")
    assert p.returncode != 0 and "kayıtta olmayan MCP" in (p.stdout + p.stderr)


def test_sema_ihlali_config_uretimini_durdurur(tmp_path):
    env, proje = ortam(tmp_path)
    kotu = {"mcp": {"x": {"komut": ["x"], "parola": SIR}}}
    (proje / ".claude" / "orkestra" / "mcp_kimlik.json").write_text(json.dumps(kotu), encoding="utf-8")
    p = cli(env, "config")
    assert p.returncode != 0 and SIR not in p.stdout + p.stderr


def test_kur_argv_sir_icermez_ve_kayitliyi_atlar():
    cagrilar = []

    class R:
        def __init__(self, k):
            self.returncode = k

    def sahte(komut, **kw):
        cagrilar.append(komut)
        # `claude mcp get`: markitdown kayıtlı (0), diğerleri değil (1); `add` başarılı
        if komut[1:3] == ["mcp", "get"]:
            return R(0 if komut[3] == "markitdown" else 1)
        return R(0)

    sonuc = dict(M.kur(["markitdown", "firecrawl"], calistir=sahte))
    assert sonuc == {"markitdown": "zaten kayıtlı", "firecrawl": "eklendi"}
    ekle = [c for c in cagrilar if c[1:3] == ["mcp", "add"]]
    assert len(ekle) == 1 and ekle[0][3:6] == ["--scope", "user", "firecrawl"]
    assert SIR not in " ".join(" ".join(c) for c in cagrilar)


def test_kur_kuru_calistirmaz():
    def yasak(*a, **k):
        raise AssertionError("kuru modda komut çalışmamalı")
    sonuc = M.kur(["firecrawl"], calistir=yasak, kuru=True)
    assert sonuc[0][1].startswith("kuru: claude mcp add")


def test_kur_hata_kodu_raporlanir():
    class R:
        def __init__(self, k):
            self.returncode = k
    sonuc = M.kur(["firecrawl"], calistir=lambda c, **k: R(1))
    assert sonuc[0][1].startswith("hata")


# --- ön koşul (gerek, ADR-0097) ---
KAYIT_GEREK = {"uvli": {"komut": ["x"], "gerek": ["uv-yok-boyle"]}, "duz": {"komut": ["x"]}}


class _R:
    def __init__(self, k):
        self.returncode = k


def _sahte_kayit_icin(cagrilar):
    def sahte(komut, **kw):
        cagrilar.append(komut)
        return _R(1 if komut[1:3] == ["mcp", "get"] else 0)
    return sahte


def test_liste_eksik_gerek_yazar(tmp_path):
    env, proje = ortam(tmp_path)
    (proje / ".claude" / "orkestra" / "mcp_kimlik.json").write_text(
        json.dumps({"mcp": {"uvli": {"komut": ["x"], "gerek": ["uv-yok-boyle"]}}}), encoding="utf-8")
    p = cli(env, "liste")
    assert "uvli: kimlik gerekmez; komut x; gerek: uv-yok-boyle yok" in p.stdout
    assert SIR not in p.stdout + p.stderr


def test_kur_hepsi_eksik_gerekli_atlar_ve_add_cagirmaz():
    cagrilar = []
    sonuc = dict(M.kur(["uvli", "duz"], calistir=_sahte_kayit_icin(cagrilar), kayit=KAYIT_GEREK, hepsi=True))
    assert sonuc["uvli"] == "atlandı: uv-yok-boyle yok" and sonuc["duz"] == "eklendi"
    assert not [c for c in cagrilar if "uvli" in c]


def test_kur_tek_tek_istenince_uyarir_ve_kaydeder():
    cagrilar = []
    sonuc = dict(M.kur(["uvli"], calistir=_sahte_kayit_icin(cagrilar), kayit=KAYIT_GEREK, hepsi=False))
    assert sonuc["uvli"] == "eklendi (uyarı: uv-yok-boyle yok)"
    assert [c for c in cagrilar if c[1:3] == ["mcp", "add"]]
