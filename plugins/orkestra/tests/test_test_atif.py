"""Test hatası atfı (I-324 P2, S3): düşen test -> sahip oturum; sahipsiz işareti."""
import json
import os
import sys
import time

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import test_atif as A  # noqa: E402


def _n(p):
    return os.path.normcase(os.path.abspath(str(p))).replace("\\", "/")


def _eklenti(tmp_path):
    """Sahte eklenti kökü: scripts/{mod_a,yardimci,ortak}.py, tests/test_mod_a.py (yardimci'yi içe aktarır)."""
    kok = tmp_path / "eklenti"
    (kok / "scripts").mkdir(parents=True)
    (kok / "tests").mkdir()
    for ad in ("mod_a", "yardimci", "ortak"):
        (kok / "scripts" / f"{ad}.py").write_text("x = 1\n", encoding="utf-8")
    (kok / "tests" / "test_mod_a.py").write_text(
        "import os\nimport yardimci\nfrom ortak import x\n\ndef test_bir():\n    assert False\n", encoding="utf-8")
    (kok / "tests" / "test_yetim.py").write_text("import os\n\ndef test_iki():\n    assert False\n", encoding="utf-8")
    return kok


def _oturum(sd, oturum, yazilan, gorulme):
    d = sd / "oturumlar"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{oturum}.json").write_text(json.dumps(
        {"oturum": oturum, "konum": {"depo": "d", "dal": "x", "yazilan": [_n(y) for y in yazilan], "gorulme": gorulme}}),
        encoding="utf-8")


def test_dusenleri_ayikla_gercek_bicim(tmp_path):
    cikti = "\n".join([
        "=========================== short test summary info ===========================",
        "FAILED tests/test_mod_a.py::test_bir - assert False",
        "FAILED tests/test_mod_a.py::TestK::test_b - assert 0",
        "FAILED tests/test_mod_a.py::test_p[a - b] - AssertionError: x",
        "ERROR tests/test_mod_a.py::test_c - RuntimeError: x",
        "ERROR tests/test_kirik.py",
        r"FAILED C:\dis\yer\test_z.py::test_q",
        "  FAILED tests/test_mod_a.py::test_bir - tekrar",  # test_paralel 'Düşenler:' tekrarı, bir kez döner
        "4 failed, 2 errors in 0.8s",
    ])
    d = A.dusenleri_ayikla(cikti, kok=str(tmp_path))
    adlar = [(os.path.basename(x["test_dosyasi"]), x["test_adi"], x["tur"]) for x in d]
    assert adlar == [("test_mod_a.py", "test_bir", "FAILED"), ("test_mod_a.py", "TestK::test_b", "FAILED"),
                     ("test_mod_a.py", "test_p[a - b]", "FAILED"), ("test_mod_a.py", "test_c", "ERROR"),
                     ("test_kirik.py", None, "ERROR"), ("test_z.py", "test_q", "FAILED")]
    assert d[0]["test_dosyasi"] == _n(tmp_path / "tests" / "test_mod_a.py")


def test_bozuk_cikti():
    assert A.dusenleri_ayikla(None) == []
    assert A.dusenleri_ayikla(b"FAILED x.py::t") == []
    assert A.dusenleri_ayikla("FAILED\nERROR \nFAILED notpy::t\nrastgele FAILED x.py::t\n\x00\xff") == []


def test_kaynak_adaylari_ad_kurali_ve_import(tmp_path):
    kok = _eklenti(tmp_path)
    a = A.kaynak_adaylari(str(kok / "tests" / "test_mod_a.py"), str(kok))
    assert {"dosya": _n(kok / "scripts" / "mod_a.py"), "tur": "ad_kurali"} == a[0]
    importlar = {x["dosya"] for x in a if x["tur"] == "import"}
    assert importlar == {_n(kok / "scripts" / "yardimci.py"), _n(kok / "scripts" / "ortak.py")}  # os yerel değil


def test_kaynak_adaylari_bozuk_test_dosyasi(tmp_path):
    kok = _eklenti(tmp_path)
    (kok / "tests" / "test_bozuk.py").write_text("def (:\n", encoding="utf-8")
    a = A.kaynak_adaylari(str(kok / "tests" / "test_bozuk.py"), str(kok))
    assert a == [{"dosya": _n(kok / "scripts" / "bozuk.py"), "tur": "ad_kurali"}]


def test_iki_oturum_dogru_esleme(tmp_path):
    """Daha yeni oturum alakasız dosya yazmış; düşen testin kaynağını yazan eski oturum sahip olur."""
    kok, sd, t = _eklenti(tmp_path), tmp_path / "sd", time.time()
    _oturum(sd, "oturum-kaynak", [kok / "scripts" / "mod_a.py"], t - 600)
    _oturum(sd, "oturum-alakasiz", [kok / "scripts" / "baska.py"], t - 10)
    test = str(kok / "tests" / "test_mod_a.py")
    r = A.sahip_bul(str(sd), test, A.kaynak_adaylari(test, str(kok)), simdi=t)
    assert r == {"test": _n(test), "sahip": "oturum-kaynak", "kanit": _n(kok / "scripts" / "mod_a.py"), "canli": True}


def test_ayni_dosyayi_iki_oturum_en_yeni(tmp_path):
    kok, sd, t = _eklenti(tmp_path), tmp_path / "sd", time.time()
    _oturum(sd, "eski", [kok / "scripts" / "mod_a.py"], t - 300)
    _oturum(sd, "yeni", [kok / "scripts" / "mod_a.py"], t - 30)
    test = str(kok / "tests" / "test_mod_a.py")
    assert A.sahip_bul(str(sd), test, A.kaynak_adaylari(test, str(kok)), simdi=t)["sahip"] == "yeni"


def test_kanit_gucu_yeniden_once(tmp_path):
    """Test dosyasını yazan oturum, yalnız içe aktarılan modülü yazan daha yeni oturumun önüne geçer."""
    kok, sd, t = _eklenti(tmp_path), tmp_path / "sd", time.time()
    _oturum(sd, "testi-yazan", [kok / "tests" / "test_mod_a.py"], t - 900)
    _oturum(sd, "import-yazan", [kok / "scripts" / "yardimci.py"], t - 5)
    test = str(kok / "tests" / "test_mod_a.py")
    r = A.sahip_bul(str(sd), test, A.kaynak_adaylari(test, str(kok)), simdi=t)
    assert (r["sahip"], r["kanit"]) == ("testi-yazan", _n(test))


def test_import_grafigiyle_dolayli_esleme(tmp_path):
    kok, sd, t = _eklenti(tmp_path), tmp_path / "sd", time.time()
    _oturum(sd, "ortak-yazan", [kok / "scripts" / "ortak.py"], t - 3600)  # 60 dk önce: canlı değil
    _oturum(sd, "alakasiz", [kok / "scripts" / "baska.py"], t - 1)
    test = str(kok / "tests" / "test_mod_a.py")
    r = A.sahip_bul(str(sd), test, A.kaynak_adaylari(test, str(kok)), simdi=t)
    assert r == {"test": _n(test), "sahip": "ortak-yazan", "kanit": _n(kok / "scripts" / "ortak.py"), "canli": False}


def test_sahipsiz(tmp_path):
    kok, sd, t = _eklenti(tmp_path), tmp_path / "sd", time.time()
    _oturum(sd, "alakasiz", [kok / "scripts" / "mod_a.py"], t - 1)  # son yazan; ama test_yetim'le ilgisi yok
    test = str(kok / "tests" / "test_yetim.py")
    r = A.sahip_bul(str(sd), test, A.kaynak_adaylari(test, str(kok)), simdi=t)
    assert r == {"test": _n(test), "sahip": None, "kanit": None, "canli": False}


def test_bozuk_ve_eksik_oturum_kayitlari(tmp_path):
    kok, sd, t = _eklenti(tmp_path), tmp_path / "sd", time.time()
    (sd / "oturumlar").mkdir(parents=True)
    (sd / "oturumlar" / "bozuk.json").write_text("{yarim", encoding="utf-8")
    (sd / "oturumlar" / "liste.json").write_text("[1]", encoding="utf-8")
    (sd / "oturumlar" / "konumsuz.json").write_text("{}", encoding="utf-8")
    (sd / "oturumlar" / "x.baglanti.json").write_text(json.dumps(
        {"konum": {"yazilan": [_n(kok / "scripts" / "mod_a.py")], "gorulme": t}}), encoding="utf-8")
    test = str(kok / "tests" / "test_mod_a.py")
    assert A.sahip_bul(str(sd), test, A.kaynak_adaylari(test, str(kok)), simdi=t)["sahip"] is None
    assert A.sahip_bul(str(tmp_path / "yok"), test, [], simdi=t)["sahip"] is None


def test_atfet_uctan_uca(tmp_path):
    kok, sd, t = _eklenti(tmp_path), tmp_path / "sd", time.time()
    _oturum(sd, "a-oturumu", [kok / "scripts" / "mod_a.py"], t - 60)
    _oturum(sd, "b-oturumu", [kok / "scripts" / "baska.py"], t - 1)
    cikti = "FAILED tests/test_mod_a.py::test_bir - assert False\nFAILED tests/test_yetim.py::test_iki - assert False\n"
    r = A.atfet(cikti, str(sd), str(kok), kok=str(kok), simdi=t)
    assert [(x["test"].rsplit("/", 1)[1], x["sahip"]) for x in r] == [
        ("test_mod_a.py::test_bir", "a-oturumu"), ("test_yetim.py::test_iki", None)]
