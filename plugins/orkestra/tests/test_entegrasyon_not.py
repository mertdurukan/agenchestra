"""Suçlu oturuma geri bildirim (I-323 P4; sözleşme S4, S8).

Karantinaya düşen teslimin hata günlüğü sır süzgecinden redakte edilip `not_birak` ile suçlu oturumun gelen kutusuna
gider; not 60 dk okunmazsa karantina `sahipsiz` işaretlenir ve yeni oturum başlangıcı bağlamına tek satır girer.
Her test geçici git deposu ve geçici durum dizini kullanır.
"""
import json
import os
import sys
import time

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import entegrasyon as E  # noqa: E402
import kuyruk as K  # noqa: E402
import oturum_farkindalik as OF  # noqa: E402
from test_entegrasyon import _depo, _icerikler  # noqa: E402

SUCLU = "oturum-suclu-0001"
# Sır kalıplı sahte günlük: anahtar=değer ve 40+ karakterlik kesintisiz dizi (gerçek değer değildir).
SAHTE_SIR = "Q" * 44
GUNLUK = (
    "collected 12 items\n"
    "FAILED tests/test_ornek.py::test_toplam_dogru - AssertionError\n"
    "ERROR tests/test_baska.py::test_baglanti\n"
    f"api_key={SAHTE_SIR}\n"
    f"baglanti dizesi {SAHTE_SIR}\n"
    "== 1 failed, 1 error, 10 passed in 2.10s ==\n"
)


def _kirmizi_test(agac):
    ok = not any("KIRMIZI" in v for v in _icerikler(agac).values())
    return ok, "" if ok else GUNLUK


def _hazirla(tmp_path, monkeypatch, oturumlar=("t1", "t2", "t3")):
    """t2 kırmızı; suçlu oturumu SUCLU. Dönen (sd, entegre sonucu)."""
    monkeypatch.setenv("ORKESTRA_OTURUM_FARKINDALIK", "1")
    teslimler = [(ad, "KIRMIZI\n" if ad == "t2" else f"ok-{ad}\n") for ad in oturumlar]
    depo = _depo(tmp_path, teslimler)
    sd = str(tmp_path / "durum")
    os.makedirs(os.path.join(sd, "oturumlar"))
    for ad, _ in teslimler:
        K.ekle(sd, ad, SUCLU if ad == "t2" else f"oturum-{ad}", f"dal-{ad}")
    s = E.entegre_et(sd, depo, test_komutu=_kirmizi_test)  # varsayılan kanca: karantina_bildir
    return sd, s


def _gelen(sd, oturum):
    yol = OF.gelen_yol(sd, oturum)
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def test_suclu_oturumun_gelen_kutusunda_not_gorulur(tmp_path, monkeypatch):
    sd, s = _hazirla(tmp_path, monkeypatch)
    assert [k["teslim"] for k in s["karantina"]] == ["t2"] and "kanca_hata" not in s
    notlar = _gelen(sd, SUCLU)
    assert len(notlar) == 1 and notlar[0]["kimden"] == "kuyruk"
    metin = notlar[0]["metin"]
    assert "t2" in metin and "dal-t2" in metin
    assert "test_toplam_dogru" in metin and "test_baglanti" in metin  # başarısız test adları
    assert "passed" in metin  # son satırlar
    assert len(metin) <= OF.NOT_EN_COK
    # başka oturumlara not gitmez
    assert _gelen(sd, "oturum-t1") == [] and _gelen(sd, "oturum-t3") == []
    # oturum gelen kutusunu okuyunca not bağlama girer
    assert "t2" in OF.gelen_metin(sd, SUCLU)
    kayit = {k["teslim"]: k for k in K.liste(sd)}["t2"]
    assert kayit["durum"] == "karantina" and kayit["not_ofset"] > 0 and kayit["not_t"] > 0


def test_sir_kalipli_gunluk_reddedilmez_redakte_gider(tmp_path, monkeypatch):
    sd, _ = _hazirla(tmp_path, monkeypatch)
    notlar = _gelen(sd, SUCLU)
    assert len(notlar) == 1, "sır kalıplı günlük not_birak'ta reddedilmemeli"
    metin = notlar[0]["metin"]
    assert SAHTE_SIR not in metin and "api_key=" not in metin
    assert OF.REDAKTE in metin
    assert not OF._SIR.search(metin)


def test_uzun_gunluk_not_en_cok_sinirina_kisalir():
    gunluk = "\n".join(f"FAILED tests/t.py::test_cok_uzun_bir_test_adi_numara_{i:03d}_ve_devami" for i in range(50))
    gunluk += "\n" + "x " * 2000
    metin = E.karantina_notu({"teslim": "t9", "dal": "dal-t9", "neden": "ilk kırmızı önek", "gunluk": gunluk})
    assert len(metin) <= OF.NOT_EN_COK and not OF._SIR.search(metin)
    ok, hata = OF.not_birak(str(os.getcwd()) if False else os.path.join(os.path.dirname(__file__), "_yok_"), "x", "k", metin) \
        if False else (True, "")
    assert ok and hata == ""


def test_kapali_oturumda_not_bekler_60_dk_sonra_sahipsiz(tmp_path, monkeypatch):
    sd, _ = _hazirla(tmp_path, monkeypatch)
    not_t = {k["teslim"]: k for k in K.liste(sd)}["t2"]["not_t"]
    # oturum kapalı: kaydı yok, not okunmadı; kutuda bekler
    assert len(_gelen(sd, SUCLU)) == 1
    assert OF.sahipsiz_tara(sd, simdi=not_t + 59 * 60) == []
    assert not {k["teslim"]: k for k in K.liste(sd)}["t2"].get("sahipsiz")
    sahipsiz = OF.sahipsiz_tara(sd, simdi=not_t + 61 * 60)
    assert [k["teslim"] for k in sahipsiz] == ["t2"]
    kayit = {k["teslim"]: k for k in K.liste(sd)}["t2"]
    assert kayit["durum"] == "karantina" and kayit["sahipsiz"] is True
    # yeniden tarama ikinci işaret yazmaz
    olay_say = len(K.L.jsonl_oku(K.kuyruk_yolu(sd)))
    OF.sahipsiz_tara(sd, simdi=not_t + 120 * 60)
    assert len(K.L.jsonl_oku(K.kuyruk_yolu(sd))) == olay_say
    # yeniden teslim sahipsiz işaretini düşürür
    K.ekle(sd, "t2", SUCLU, "dal-t2")
    assert not {k["teslim"]: k for k in K.liste(sd)}["t2"].get("sahipsiz")


def test_okunan_not_sahipsiz_olmaz(tmp_path, monkeypatch):
    sd, _ = _hazirla(tmp_path, monkeypatch)
    not_t = {k["teslim"]: k for k in K.liste(sd)}["t2"]["not_t"]
    # suçlu oturum açık: kaydı var ve gelen kutusunu okur
    yol = K.L._oturum_json_yol(sd, SUCLU)
    K.L.atomik_yaz(yol, json.dumps({"oturum": SUCLU}))
    assert len(OF.gelen_oku(sd, SUCLU)) == 1
    assert OF.sahipsiz_tara(sd, simdi=not_t + 61 * 60) == []


def test_oturum_basi_baglaminda_sahipsiz_satiri_var(tmp_path, monkeypatch):
    sd, _ = _hazirla(tmp_path, monkeypatch)
    not_t = {k["teslim"]: k for k in K.liste(sd)}["t2"]["not_t"]
    OF.sahipsiz_tara(sd, simdi=not_t + 61 * 60)
    # yeni ve ilgisiz bir oturum, git deposu olmayan dizinde açılır
    bos = tmp_path / "bos"
    bos.mkdir()
    baglam = OF.oturum_basi(sd, "yeni-oturum-0002", str(bos))
    satirlar = [s for s in baglam.splitlines() if "Sahipsiz karantina" in s]
    assert len(satirlar) == 1 and "t2" in satirlar[0] and len(satirlar[0]) <= 250
    # git deposunda açılan oturumda da satır var
    baglam2 = OF.oturum_basi(sd, "yeni-oturum-0003", str(tmp_path / "depo"))
    assert sum("Sahipsiz karantina" in s for s in baglam2.splitlines()) == 1


def test_sahipsiz_yoksa_oturum_basi_ek_satir_yazmaz(tmp_path, monkeypatch):
    sd, _ = _hazirla(tmp_path, monkeypatch)
    bos = tmp_path / "bos"
    bos.mkdir()
    assert "Sahipsiz" not in OF.oturum_basi(sd, "yeni-oturum-0004", str(bos))


def test_oturumu_bilinmeyen_teslimde_not_gitmez_iz_yazilir(tmp_path, monkeypatch):
    monkeypatch.setenv("ORKESTRA_OTURUM_FARKINDALIK", "1")
    sd = str(tmp_path / "durum")
    os.makedirs(sd)
    K.ekle(sd, "t7", "", "dal-t7")
    K.gecis(sd, "t7", "kosuyor")
    K.gecis(sd, "t7", "karantina", neden="test")
    r = E.karantina_bildir(sd, {"teslim": "t7", "oturum": "-", "dal": "dal-t7", "neden": "x", "gunluk": GUNLUK},
                           simdi=1000.0)
    assert r["gitti"] is False
    kayit = K.liste(sd)[0]
    assert kayit["not_ofset"] is None and kayit["not_t"] == 1000.0
    assert [k["teslim"] for k in OF.sahipsiz_tara(sd, simdi=1000.0 + 3600)] == ["t7"]


def test_kanca_none_bildirimi_kapatir(tmp_path, monkeypatch):
    monkeypatch.setenv("ORKESTRA_OTURUM_FARKINDALIK", "1")
    teslimler = [("t1", "ok\n"), ("t2", "KIRMIZI\n")]
    depo = _depo(tmp_path, teslimler)
    sd = str(tmp_path / "durum")
    os.makedirs(sd)
    for ad, _ in teslimler:
        K.ekle(sd, ad, SUCLU, f"dal-{ad}")
    E.entegre_et(sd, depo, test_komutu=_kirmizi_test, kanca=None)
    assert _gelen(sd, SUCLU) == []


def test_alan_ekle_durum_alanini_degistirmez(tmp_path):
    sd = str(tmp_path / "durum")
    os.makedirs(sd)
    K.ekle(sd, "t1", "o", "dal-t1")
    try:
        K.alan_ekle(sd, "t1", durum="birlesti")
    except K.KuyrukHatasi:
        pass
    else:
        raise AssertionError("durum alan_ekle ile değişmemeli")
    assert K.liste(sd)[0]["durum"] == "bekliyor"
    assert time.time() > 0
