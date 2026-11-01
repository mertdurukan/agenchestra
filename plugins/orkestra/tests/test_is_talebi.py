"""Todo işi talebi (I-324 P1; sözleşme S1, S2)."""
import json
import os
import sys

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_talebi as T  # noqa: E402

A, B, C = "aaaa1111-0000", "bbbb2222-0000", "cccc3333-0000"
MADDE = "Talep kaydı modülünü yaz ve testlerini ekle"
T0 = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _acik(monkeypatch):
    monkeypatch.delenv("ORKESTRA_IS_TALEBI", raising=False)


def _sd(tmp_path, mod=None, esik=None):
    sd = tmp_path / "durum"
    (sd / "oturumlar").mkdir(parents=True)
    ayar = {}
    if mod:
        ayar["mod"] = mod
    if esik is not None:
        ayar["jaccard_esik"] = esik
    if ayar:
        (sd / "is_talebi.json").write_text(json.dumps(ayar), encoding="utf-8")
    return str(sd)


def _gunluk(sd):
    yol = os.path.join(sd, "gunluk.jsonl")
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def _talepler(sd):
    with open(T.kayit_yolu(sd), encoding="utf-8") as f:
        return json.load(f)["talepler"]


def test_mod_varsayilan_golge_ve_esik(tmp_path):
    sd = _sd(tmp_path)
    assert T.mod(sd) == "golge" and T.esik(sd) == 0.6


def test_s1_golge_ikinci_talepte_sahip_uyari_kayit_ve_talep_alinir(tmp_path):
    sd = _sd(tmp_path)
    r1 = T.talep_al(sd, A, "I-1", MADDE, ["scripts/is_talebi.py"], simdi=T0)
    assert r1["durum"] == "alindi" and r1["sahip"] is None
    r2 = T.talep_al(sd, B, "I-2", "başka metin", ["scripts\\is_talebi.py"], simdi=T0 + 60)
    assert r2["durum"] == "sahip_var" and r2["mod"] == "golge" and not r2.get("reddedildi")
    assert r2["sahip"] == {"oturum": A, "is_id": "I-1", "madde": MADDE}
    assert r2["neden"] == "yazma_alani"
    assert {x["oturum"] for x in _talepler(sd)} == {A, B}  # gölgede talep yine alınır
    g = [x for x in _gunluk(sd) if x["kapi"] == "is_talebi"]
    assert len(g) == 1 and g[0]["tur"] == "kapi_golge" and g[0]["sahip"] == A[:8] and g[0]["oturum"] == B[:8]
    assert "aaaa1111" in T.satir(r2) and len(T.satir(r2)) <= 250


def test_s1_ihlal_ikinci_talep_reddedilir(tmp_path):
    sd = _sd(tmp_path, mod="ihlal")
    T.talep_al(sd, A, "I-1", MADDE, ["scripts/is_talebi.py"], simdi=T0)
    r2 = T.talep_al(sd, B, "I-2", MADDE, [], simdi=T0 + 60)
    assert r2["durum"] == "sahip_var" and r2["reddedildi"] is True and r2["sahip"]["oturum"] == A
    assert r2["neden"] == "jaccard"
    assert [x["oturum"] for x in _talepler(sd)] == [A]  # ret: talep yazılmaz
    g = [x for x in _gunluk(sd) if x["kapi"] == "is_talebi"]
    assert len(g) == 1 and g[0]["tur"] == "kapi_ret"
    assert T.satir(r2).startswith("UYARI")


def test_s2_suresi_dolan_sahip_devralinir(tmp_path):
    sd = _sd(tmp_path, mod="ihlal")
    T.talep_al(sd, A, "I-1", MADDE, ["scripts/is_talebi.py"], simdi=T0)
    on = T.devral_gerekir_mi(sd, B, "I-2", MADDE, ["scripts/is_talebi.py"], simdi=T0 + T.CANLI_S + 1)
    assert on["gerekir"] is True and on["sahip"]["oturum"] == A
    r = T.talep_al(sd, B, "I-2", MADDE, ["scripts/is_talebi.py"], simdi=T0 + T.CANLI_S + 1)
    assert r["durum"] == "devralindi" and r["sahip"]["oturum"] == A and not r.get("reddedildi")
    assert [x["oturum"] for x in _talepler(sd)] == [B]  # A'nın talebi düştü
    assert not [x for x in _gunluk(sd) if x.get("kapi") == "is_talebi"]


def test_s2_sinirda_hala_canli_ve_oturum_kaydi_canli_tutar(tmp_path):
    sd = _sd(tmp_path, mod="ihlal")
    T.talep_al(sd, A, "I-1", MADDE, [], simdi=T0)
    assert T.devral_gerekir_mi(sd, B, None, MADDE, simdi=T0 + T.CANLI_S)["canli"] is True  # tam 30 dk: canlı
    # talep yenilenmemiş ama oturum kaydı (oturum_farkindalik konum.gorulme) taze: sahip canlı sayılır
    with open(os.path.join(sd, "oturumlar", A + ".json"), "w", encoding="utf-8") as f:
        json.dump({"konum": {"gorulme": T0 + 3000}}, f)
    r = T.talep_al(sd, B, None, MADDE, [], simdi=T0 + 3600)
    assert r["durum"] == "sahip_var" and r["reddedildi"]


def test_ayni_oturum_yenileme_eslesme_sayilmaz(tmp_path):
    sd = _sd(tmp_path, mod="ihlal")
    assert T.talep_al(sd, A, "I-1", MADDE, ["x.py"], simdi=T0)["durum"] == "alindi"
    r = T.talep_al(sd, A, "I-1", MADDE, ["x.py"], simdi=T0 + 600)
    assert r["durum"] == "alindi" and r.get("yenilendi") is True
    t = _talepler(sd)
    assert len(t) == 1 and t[0]["yenilendi"] == T0 + 600 and t[0]["zaman"] == T0
    assert T.yenile(sd, A, "I-1", simdi=T0 + 900) == 1 and _talepler(sd)[0]["yenilendi"] == T0 + 900
    assert not _gunluk(sd)


def test_golgede_ilk_sahip_yenilerken_ikinciyi_sahip_gormez(tmp_path):
    sd = _sd(tmp_path)
    T.talep_al(sd, A, "I-1", MADDE, ["x.py"], simdi=T0)
    T.talep_al(sd, B, "I-2", MADDE, ["x.py"], simdi=T0 + 10)
    assert T.talep_al(sd, A, "I-1", MADDE, ["x.py"], simdi=T0 + 20)["durum"] == "alindi"
    assert T.talep_al(sd, B, "I-2", MADDE, ["x.py"], simdi=T0 + 30)["sahip"]["oturum"] == A


def _kelimeler(onek, n):
    return [onek + chr(97 + i // 26) + chr(97 + i % 26) for i in range(n)]


def test_jaccard_esik_siniri(tmp_path):
    sd = _sd(tmp_path, mod="ihlal")
    ortak = _kelimeler("ort", 3)
    a, b = " ".join(ortak + ["birx"]), " ".join(ortak + ["ikix"])  # 3/5 = 0,6
    assert T.jaccard(T.tokenlar(a), T.tokenlar(b)) == pytest.approx(0.6)
    T.talep_al(sd, A, "I-1", a, [], simdi=T0)
    assert T.talep_al(sd, B, "I-2", b, [], simdi=T0 + 1)["durum"] == "sahip_var"

    sd2 = _sd(tmp_path / "iki", mod="ihlal")
    ortak = _kelimeler("ort", 13)
    a, b = " ".join(ortak + _kelimeler("aaa", 5)), " ".join(ortak + _kelimeler("bbb", 4))  # 13/22 ≈ 0,59
    j = T.jaccard(T.tokenlar(a), T.tokenlar(b))
    assert 0.59 <= j < 0.6
    T.talep_al(sd2, A, "I-1", a, [], simdi=T0)
    assert T.talep_al(sd2, B, "I-2", b, [], simdi=T0 + 1)["durum"] == "alindi"


def test_jaccard_esik_ayardan(tmp_path):
    sd = _sd(tmp_path, mod="ihlal", esik=0.59)
    ortak = _kelimeler("ort", 13)
    a, b = " ".join(ortak + _kelimeler("aaa", 5)), " ".join(ortak + _kelimeler("bbb", 4))
    T.talep_al(sd, A, "I-1", a, [], simdi=T0)
    assert T.esik(sd) == 0.59 and T.talep_al(sd, B, "I-2", b, [], simdi=T0 + 1)["durum"] == "sahip_var"


def test_normalize_noktalama_sayi_durak_ve_buyuk_harf():
    assert T.tokenlar("P1: Talep kaydı, ve 30 dk İŞ!") == frozenset({"talep", "kaydı", "dk", "iş"})


def test_yazma_alani_kesisimi(tmp_path):
    sd = _sd(tmp_path, mod="ihlal")
    T.talep_al(sd, A, "I-1", "tamamen farklı bir iş", ["scripts/a.py", "tests/test_a.py"], simdi=T0)
    assert T.talep_al(sd, B, "I-2", "ilgisiz başka konu", ["docs/b.md"], simdi=T0 + 1)["durum"] == "alindi"
    r = T.talep_al(sd, C, "I-3", "yine ilgisiz konu", ["./tests/test_a.py"], simdi=T0 + 2)
    assert r["durum"] == "sahip_var" and r["neden"] == "yazma_alani" and r["sahip"]["oturum"] == A
    assert T.alan_kesisir(T.alan_kumesi(["scripts"]), T.alan_kumesi(["scripts/a.py"]))


def test_kapali_mod_hicbir_sey_yazmaz(tmp_path, monkeypatch):
    sd = _sd(tmp_path, mod="ihlal")
    T.talep_al(sd, A, "I-1", MADDE, ["x.py"], simdi=T0)
    monkeypatch.setenv("ORKESTRA_IS_TALEBI", "0")
    assert T.mod(sd) == "kapali"
    r = T.talep_al(sd, B, "I-2", MADDE, ["x.py"], simdi=T0 + 1)
    assert r["durum"] == "kapali" and r["sahip"] is None
    assert [x["oturum"] for x in _talepler(sd)] == [A] and not _gunluk(sd)
    assert T.devral_gerekir_mi(sd, B, "I-2", MADDE, ["x.py"], simdi=T0 + 1)["sahip"] is None


def test_birak_ve_sir_maskelenir(tmp_path):
    sd = _sd(tmp_path)
    T.talep_al(sd, A, "I-1", MADDE, ["x.py"], simdi=T0)
    assert T.birak(sd, A, "I-1") == 1 and _talepler(sd) == []
    T.talep_al(sd, A, "I-1", "parola=Gizli123abc ayarla", [], simdi=T0)
    assert "Gizli123abc" not in json.dumps(_talepler(sd))
