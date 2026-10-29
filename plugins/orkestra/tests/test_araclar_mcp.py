"""Panel /araclar MCP arka ucu (ADR-0098): liste, aç/kapat; yalnız kayıttaki ad; sır yok."""
import json
import os
import subprocess
import sys

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import araclar_mcp as A  # noqa: E402

SIR = "SAHTE-sir-9f3k"
KAYIT = {
    "memory": {"aciklama": "bellek", "komut": ["npx", "-y", "m"]},
    "serena": {"aciklama": "kod", "komut": ["serena"], "gerek": ["uv"]},
    "firecrawl": {"aciklama": "web", "komut": ["npx", "f"], "kimlik_servisi": "firecrawl",
                  "ortam": {"FIRECRAWL_API_KEY": "FIRECRAWL_API_KEY"}},
    "filesystem": {"aciklama": "dosya", "komut": ["npx", "fs"]},
}


class Sahte:
    """claude CLI taklidi: kayıtlı küme + çağrılan argv listesi."""

    def __init__(self, kayitli=(), cikis=0):
        self.kayitli, self.cikis, self.cagrilar = set(kayitli), cikis, []

    def __call__(self, argv, **kw):
        self.cagrilar.append(argv)
        if self.cikis == 0 and "add" in argv:
            self.kayitli.add(argv[argv.index("--") - 1])
        elif self.cikis == 0 and "remove" in argv:
            self.kayitli.discard(argv[-1])
        return subprocess.CompletedProcess(argv, self.cikis if "get" not in argv else 1)

    def oku(self):
        return set(self.kayitli)


def bul_var(ad):
    return "/bin/" + ad if ad != "uv" else None


def test_liste_alanlari_ve_durum():
    s = A.liste(kayit=KAYIT, kayitli={"memory"}, yukle=lambda sv: {}, bul=bul_var)
    assert [x["ad"] for x in s] == sorted(KAYIT)
    m = {x["ad"]: x for x in s}
    assert m["memory"]["durum"] == "acik" and m["serena"]["durum"] == "kapali"
    assert m["serena"]["eksik_gerek"] == ["uv"]
    assert m["firecrawl"]["kimlik"].startswith("yok") and m["memory"]["kimlik"] == "gerekmez"
    assert m["filesystem"]["yuksek_yetki"] and not m["memory"]["yuksek_yetki"]


def test_liste_sir_degeri_yok():
    s = A.liste(kayit=KAYIT, kayitli=set(), yukle=lambda sv: {"FIRECRAWL_API_KEY": SIR}, bul=bul_var)
    assert SIR not in json.dumps(s)
    assert {x["ad"]: x for x in s}["firecrawl"]["kimlik"] == "var"


def test_kayitsiz_ad_ve_gecersiz_durum_reddedilir():
    f = Sahte()
    with pytest.raises(A.AraclarHata):
        A.degistir("rastgele", "acik", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=bul_var)
    with pytest.raises(A.AraclarHata):
        A.degistir("memory", "belki", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=bul_var)
    with pytest.raises(A.AraclarHata):
        A.degistir(["memory"], "acik", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=bul_var)
    assert f.cagrilar == []


def test_ac_ve_kapat_gidis_donus():
    f = Sahte()
    r = A.degistir("memory", "acik", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=bul_var)
    assert r == {"ad": "memory", "istenen": "acik", "durum": "acik", "tamam": True}
    assert any("add" in c for c in f.cagrilar)
    r = A.degistir("memory", "kapali", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=bul_var)
    assert r["durum"] == "kapali" and r["tamam"]
    assert any("remove" in c and c[-1] == "memory" for c in f.cagrilar)


def test_argv_sir_tasimaz():
    f = Sahte()
    A.degistir("firecrawl", "acik", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=bul_var)
    assert SIR not in json.dumps(f.cagrilar) and "FIRECRAWL_API_KEY=" not in json.dumps(f.cagrilar)


def test_basarisiz_komutta_durum_dogru_raporlanir():
    f = Sahte(cikis=1)
    r = A.degistir("memory", "acik", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=bul_var)
    assert r["durum"] == "kapali" and r["tamam"] is False


def test_zaten_acik_ikinci_cagri_yazmaz():
    f = Sahte(kayitli={"memory"})
    A.degistir("memory", "acik", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=bul_var)
    assert f.cagrilar == []


def test_claude_yoksa_hata():
    f = Sahte()
    with pytest.raises(A.AraclarHata):
        A.degistir("memory", "acik", kayit=KAYIT, calistir=f, kayitli_oku=f.oku, bul=lambda a: None)


def test_kayitli_adlar_okur_bozuk_dosyada_bos(tmp_path):
    d = tmp_path / "c.json"
    d.write_text(json.dumps({"mcpServers": {"a": {}, "b": {}}, "baska": 1}), encoding="utf-8")
    assert A.kayitli_adlar(str(d)) == {"a", "b"}
    d.write_text("{bozuk", encoding="utf-8")
    assert A.kayitli_adlar(str(d)) == set()
    assert A.kayitli_adlar(str(tmp_path / "yok.json")) == set()


def test_gercek_kayit_19_girdi_liste():
    s = A.liste(kayitli=set(), yukle=lambda sv: {}, bul=lambda a: "/x")
    assert len(s) == 19 and all(x["durum"] == "kapali" for x in s)
