"""Olay şeması (I-289 P1): davranis() kategori, alt, sonuc alanlarını yazar; eski satırlar ve okuyucular bozulmaz."""
import importlib
import json
import os
import sys

EKLENTI = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(EKLENTI, "scripts"))
hk = importlib.import_module("hata_kayit")


def _satirlar(sd):
    return [json.loads(s) for s in open(os.path.join(str(sd), hk.DOSYA), encoding="utf-8")]


def test_davranis_kategori_alt_sonuc_yazar(tmp_path):
    hk.davranis(str(tmp_path), "hook-red", "P-016 onay bekliyor", baglam="I-289")
    s = _satirlar(tmp_path)[0]
    assert (s["kategori"], s["alt"], s["sonuc"], s["baglam"], s["sinif"]) == ("kapi_ret", "hook-red", None, "I-289", "davranis")


def test_bilinmeyen_tur_belirsiz(tmp_path):
    hk.davranis(str(tmp_path), "yeni-tur", "x")
    s = _satirlar(tmp_path)[0]
    assert (s["kategori"], s["alt"]) == ("belirsiz", "yeni-tur")


def test_gecersiz_kategori_belirsiz_ve_verilen_kategori_gecerli(tmp_path):
    assert hk.olay_kategori("x", "uydurma", "a") == ("belirsiz", "a")
    assert hk.olay_kategori("x", "yanlis_oneri", "a") == ("yanlis_oneri", "a")


def test_eski_satir_okunur_ve_sonuc_birlestirilir():
    eski = {"imza": "hook-red: a", "sinif": "davranis"}
    assert hk.sonuc_birlestir(eski)["sonuc"] is None
    assert hk.sonuc_birlestir(eski, {"hook-red: a": "tekrarladi"})["sonuc"] == "tekrarladi"
    assert "sonuc" not in eski   # ham satır değişmez


def test_hata_en_cok_yeni_alanli_satirla_calisir(tmp_path):
    hk.davranis(str(tmp_path), "hook-red", "P-016 onay bekliyor")
    he = importlib.import_module("hata_en_cok")
    assert any(a for a in dir(he) if not a.startswith("_"))
