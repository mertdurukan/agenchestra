"""MCP kimlik sarmalayıcısı (scripts/mcp_kimlik.py, ADR-0096): kayıt şeması, kimlikten ortam, stdio aktarımı, sızıntı.

Sarmalayıcı gerçek bir alt süreç olarak koşar (stdio'nun aktarıldığı yalnız böyle sınanır); sahte MCP bir Python tek satırıdır.
"""
import hashlib
import importlib
import json
import os
import subprocess
import sys

import pytest

EKLENTI = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(EKLENTI, "scripts"))
mk = importlib.import_module("mcp_kimlik")
BETIK = os.path.join(EKLENTI, "scripts", "mcp_kimlik.py")

SIR = "P@ss/w:rd#1?x-SAHTE"
SIR_OZET = hashlib.sha256(SIR.encode()).hexdigest()
# Sahte MCP: stdin'den bir satır okur, aynen yankılar, ortamdaki değerin yalnız özetini yazar (değerin kendisini asla).
SAHTE_MCP = (
    "import hashlib,os,sys;"
    "s=sys.stdin.readline().strip();"
    "v=os.environ.get('SAHTE_ANAHTAR','');"
    "print('YANKI:'+s);"
    "print('OZET:'+hashlib.sha256(v.encode()).hexdigest())"
)


def kur(tmp_path, ortam=None, kimlik_icerik=SIR, servis="sahte"):
    """Geçici proje + kimlik klasörü: kayıt `eko` MCP'sini tanımlar; kimlik dosyası SAHTE_ANAHTAR taşır."""
    proje = tmp_path / "proje"
    (proje / ".claude" / "orkestra").mkdir(parents=True)
    kayit = {"mcp": {"eko": {"komut": [sys.executable, "-c", SAHTE_MCP], "kimlik_servisi": servis,
                             "ortam": {"SAHTE_ANAHTAR": "SAHTE_ANAHTAR"} if ortam is None else ortam}}}
    (proje / ".claude" / "orkestra" / "mcp_kimlik.json").write_text(json.dumps(kayit), encoding="utf-8")
    kok = tmp_path / "kimlik"
    (kok / "testproje").mkdir(parents=True)
    if kimlik_icerik is not None:
        (kok / "testproje" / f"{servis}.env").write_text(f"SAHTE_ANAHTAR={kimlik_icerik}\n", encoding="utf-8")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(proje), "ORKESTRA_KIMLIK_DIZINI": str(kok),
           "ORKESTRA_KIMLIK_PROJE": "testproje", "PYTHONUTF8": "1"}
    env.pop("SAHTE_ANAHTAR", None)
    return env


def kos(env, ad="eko", girdi="merhaba\n"):
    return subprocess.run([sys.executable, "-I", BETIK, ad], input=girdi, capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=60)


def test_stdio_aktarilir_ve_deger_alt_surecin_ortaminda(tmp_path):
    p = kos(kur(tmp_path))
    assert p.returncode == 0, p.stderr
    assert "YANKI:merhaba" in p.stdout            # stdin alt sürece, stdout geri aktarıldı
    assert f"OZET:{SIR_OZET}" in p.stdout         # değer alt sürecin ortamında


def test_deger_sarmalayici_argv_stdout_stderr_de_yok(tmp_path):
    env = kur(tmp_path)
    p = kos(env)
    assert SIR not in p.stdout and SIR not in p.stderr
    assert SIR not in " ".join([sys.executable, "-I", BETIK, "eko"])
    # Kayıtta da yalnız ad var: değer proje ayarına hiç yazılmaz.
    kayit = (tmp_path / "proje" / ".claude" / "orkestra" / "mcp_kimlik.json").read_text(encoding="utf-8")
    assert SIR not in kayit


def test_kimlik_yoksa_ad_soyleyen_hata_stdout_bos(tmp_path):
    p = kos(kur(tmp_path, kimlik_icerik=None))
    assert p.returncode == 3
    assert p.stdout == ""
    assert "sahte.SAHTE_ANAHTAR" in p.stderr and "orkestra kimlik ekle" in p.stderr


def test_anahtar_dosyada_yoksa_ad_soyleyen_hata(tmp_path):
    env = kur(tmp_path, ortam={"SAHTE_ANAHTAR": "BASKA_ANAHTAR"})
    p = kos(env)
    assert p.returncode == 3 and p.stdout == ""
    assert "sahte.BASKA_ANAHTAR" in p.stderr and SIR not in p.stderr


def test_kayitta_olmayan_mcp(tmp_path):
    p = kos(kur(tmp_path), ad="yok-boyle-mcp")
    assert p.returncode == 3 and p.stdout == "" and "kayıtta yok" in p.stderr


@pytest.mark.parametrize("girdi,parca", [
    ({"komut": ["x"], "parola": "gizli-deger-123"}, "parola"),                       # değer alanı
    ({"komut": ["x"], "kimlik_servisi": "s", "ortam": {"A": "p@ss/w:rd"}}, "ortam girdileri"),  # ad dışı değer
    ({"komut": ["x"], "ortam": {"A": "B"}}, "kimlik_servisi"),                       # servis yok
    ({"komut": []}, "komut"),
    ({"komut": ["x"], "ortam": ["A"]}, "ortam nesne"),
])
def test_sema_degeri_ve_bilinmeyen_alani_reddeder(girdi, parca):
    with pytest.raises(mk.KayitHata) as e:
        mk.dogrula("t", girdi)
    assert parca in str(e.value)
    for deger in ("gizli-deger-123", "p@ss/w:rd"):
        assert deger not in str(e.value)            # hata iletisi değer taşımaz


def test_eklenti_kaydi_gecerli_ve_ucu_var_degersiz(tmp_path):
    kayit = mk.kayit_oku(str(tmp_path))
    assert {"markitdown", "firecrawl", "sequential-thinking"} <= set(kayit)
    assert kayit["firecrawl"]["ortam"] == {"FIRECRAWL_API_KEY": "FIRECRAWL_API_KEY"}
    ham = open(os.path.join(EKLENTI, "ayarlar", "mcp_kimlik.json"), encoding="utf-8").read()
    assert "fc-" not in ham                          # Firecrawl anahtar öneki: kayıtta değer yok


def test_ortam_kur_alt_surec_ortamini_tabana_ekler():
    g = {"komut": ["x"], "kimlik_servisi": "s", "ortam": {"A": "B"}}
    env = mk.ortam_kur("t", g, lambda s, a: "deger", taban={"PATH": "p"})
    assert env == {"PATH": "p", "A": "deger"}


def test_ortam_kur_hata_iletisi_alttaki_istisnayi_tasimaz():
    g = {"komut": ["x"], "kimlik_servisi": "s", "ortam": {"A": "B"}}

    def al(s, a):
        raise RuntimeError(f"ic ayrinti {SIR}")
    with pytest.raises(mk.KayitHata) as e:
        mk.ortam_kur("t", g, al, taban={})
    assert SIR not in str(e.value) and "s.B" in str(e.value)


def test_servis_onekli_anahtar_iki_servisten_alinir():
    g = {"komut": ["x"], "ortam": {"A": "s1.K1", "B": "s2.K2"}}
    mk.dogrula("t", g)
    gelen = []

    def al(s, a):
        gelen.append((s, a))
        return "d-" + s
    env = mk.ortam_kur("t", g, al, taban={})
    assert env == {"A": "d-s1", "B": "d-s2"} and gelen == [("s1", "K1"), ("s2", "K2")]


@pytest.mark.parametrize("ortam", [{"A": "s1."}, {"A": ".K"}, {"A": "s 1.K"}, {"A": "s1.K.X"}])
def test_bozuk_servis_anahtar_reddedilir(ortam):
    with pytest.raises(mk.KayitHata):
        mk.dogrula("t", {"komut": ["x"], "kimlik_servisi": "s", "ortam": ortam})


@pytest.mark.parametrize("gerek", ["uv", ["a/b"], ["a\b"], [""], [1]])
def test_gerek_gecersiz_tur_ve_yol_ayraci_reddedilir(gerek):
    with pytest.raises(mk.KayitHata):
        mk.dogrula("t", {"komut": ["x"], "gerek": gerek})


def test_gerek_gecerli_kabul_edilir():
    mk.dogrula("t", {"komut": ["x"], "gerek": ["uv", "docker"]})


def test_proje_yer_tutucusu_acilir_ve_yoksa_hata(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert mk.komut_ac(["npx", "${CLAUDE_PROJECT_DIR}"], "t") == ["npx", str(tmp_path)]
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    with pytest.raises(mk.KayitHata):
        mk.komut_ac(["npx", "${CLAUDE_PROJECT_DIR}"], "t")


def test_baska_yer_tutucu_reddedilir():
    with pytest.raises(mk.KayitHata):
        mk.dogrula("t", {"komut": ["x", "${HOME}"]})
    mk.dogrula("t", {"komut": ["x", "${CLAUDE_PROJECT_DIR}/a"]})


def test_servis_onekli_hata_iletisi_degersiz():
    g = {"komut": ["x"], "ortam": {"A": "s1.K1"}}

    def al(s, a):
        raise RuntimeError(SIR)
    with pytest.raises(mk.KayitHata) as e:
        mk.ortam_kur("t", g, al, taban={})
    assert "s1.K1" in str(e.value) and SIR not in str(e.value)
