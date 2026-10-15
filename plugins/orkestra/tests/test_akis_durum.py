"""akis.py (G-083) kabul testleri: aciklik kart 'durum'undan, birlestirme-ret karar beklemeyi baslatir.

Eski test_akis.py testlerine dokunulmaz; burada yalniz yeni davranis sinanir.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_akis import kart, kos, yaz, z  # noqa: E402

SIMDI = z(200)


def acik_bul(out, cid):
    return [k for k in out["acik"] if k["id"] == cid]


def g074(durum="beklemede"):
    # gercek veri sekli: beklemede, beklemeden-teslim, birlestirme-ret
    return kart("G-074", [
        (z(0), "olusturuldu"), (z(2), "isleniyor"), (z(20), "is-bitti"),
        (z(22), "denetim:onay"), (z(57), "beklemede"),
        (z(58), "beklemeden-teslim"), (z(58, 30), "birlestirme-ret")], durum=durum)


# ---- k1 ----
def test_k1_g074_benzeri_karar_bekleme_acik(tmp_path):
    yaz(tmp_path, [g074()])
    out = kos(tmp_path, "--simdi", SIMDI)
    a = acik_bul(out, "G-074")
    assert len(a) == 1
    assert a[0]["asama"] == "karar_bekleme"


def test_k1_yas_birlestirme_ret_zamanindan(tmp_path):
    yaz(tmp_path, [g074()])
    a = acik_bul(kos(tmp_path, "--simdi", SIMDI), "G-074")[0]
    # 200 dk - 58.5 dk = 141.5 dk (beklemede z(57) olsaydi 143.0 olurdu)
    assert a["yas_dk"] == 141.5


def test_k1_birlestirme_ret_sonrasi_beklemede_olayi_yok_yas_ret_aninda(tmp_path):
    k = kart("G-010", [(z(0), "olusturuldu"), (z(1), "isleniyor"), (z(30), "birlestirme-ret")],
             durum="beklemede")
    yaz(tmp_path, [k])
    a = acik_bul(kos(tmp_path, "--simdi", SIMDI), "G-010")
    assert len(a) == 1 and a[0]["asama"] == "karar_bekleme" and a[0]["yas_dk"] == 170.0


# ---- k2 ----
def test_k2_beklemede_durumu_son_olay_baska_ise_de_karar_bekleme(tmp_path):
    k = kart("G-020", [
        (z(0), "olusturuldu"), (z(2), "isleniyor"), (z(50), "beklemede"),
        (z(60), "denetim:onay")], durum="beklemede")
    yaz(tmp_path, [k])
    a = acik_bul(kos(tmp_path, "--simdi", SIMDI), "G-020")
    assert len(a) == 1
    assert a[0]["asama"] == "karar_bekleme"
    assert a[0]["yas_dk"] == 150.0  # son 'beklemede' (z(50)) olayindan


def test_k2_yas_beklemede_ile_ret_arasinda_sonuncusundan(tmp_path):
    k = kart("G-021", [
        (z(0), "olusturuldu"), (z(2), "isleniyor"), (z(40), "birlestirme-ret"),
        (z(90), "beklemede"), (z(95), "is-bitti")], durum="beklemede")
    yaz(tmp_path, [k])
    a = acik_bul(kos(tmp_path, "--simdi", SIMDI), "G-021")[0]
    assert a["asama"] == "karar_bekleme" and a["yas_dk"] == 110.0


def test_k2_durum_teslim_olaylar_ne_olursa_olsun_acik_degil(tmp_path):
    ks = [
        g074(durum="teslim"),
        kart("G-031", [(z(0), "olusturuldu"), (z(5), "beklemede")], durum="teslim"),
        kart("G-032", [(z(0), "olusturuldu"), (z(5), "isleniyor")], durum="teslim"),
    ]
    yaz(tmp_path, ks)
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["acik"] == []


def test_k2_durum_iptal_acik_degil(tmp_path):
    k = kart("G-033", [(z(0), "olusturuldu"), (z(5), "birlestirme-ret")], durum="iptal")
    yaz(tmp_path, [k])
    assert kos(tmp_path, "--simdi", SIMDI)["acik"] == []


def test_k2_teslim_olayi_var_ama_durum_beklemede_acik_sayilir(tmp_path):
    # aciklik olaydan degil durumdan: son olay teslim olsa da durum beklemede ise acik
    k = kart("G-034", [(z(0), "olusturuldu"), (z(5), "beklemede"), (z(8), "teslim"),
                       (z(9), "birlestirme-ret")], durum="beklemede")
    yaz(tmp_path, [k])
    a = acik_bul(kos(tmp_path, "--simdi", SIMDI), "G-034")
    assert len(a) == 1 and a[0]["asama"] == "karar_bekleme" and a[0]["yas_dk"] == 191.0


def test_k2_durum_beklemede_degilse_mevcut_olay_esleme(tmp_path):
    k = kart("G-035", [(z(0), "olusturuldu"), (z(5), "isleniyor"), (z(10), "is-bitti")],
             durum="denetimde")
    yaz(tmp_path, [k])
    a = acik_bul(kos(tmp_path, "--simdi", SIMDI), "G-035")
    assert len(a) == 1 and a[0]["asama"] == "denetimde" and a[0]["yas_dk"] == 190.0


def test_k2_aciklik_olaydan_degil_durumdan_olusturuldu_sonrasi(tmp_path):
    # durum isleniyor, olay akisinda beklemeden-teslim son: kapanmis degil
    k = kart("G-036", [(z(0), "olusturuldu"), (z(5), "isleniyor"), (z(8), "beklemede"),
                       (z(9), "beklemeden-teslim"), (z(12), "isleniyor")], durum="isleniyor")
    yaz(tmp_path, [k])
    a = acik_bul(kos(tmp_path, "--simdi", SIMDI), "G-036")
    assert len(a) == 1 and a[0]["asama"] == "iscide_ilk"


# ---- k3 ----
def test_k3_ret_beklemede_isleniyor_karar_bekleme_ret_anindan(tmp_path):
    k = kart("G-040", [
        (z(0), "olusturuldu"), (z(2), "isleniyor"), (z(10), "birlestirme-ret"),
        (z(15), "beklemede"), (z(40), "isleniyor")], durum="isleniyor")
    yaz(tmp_path, [k])
    out = kos(tmp_path, "--simdi", SIMDI)
    s = out["asamalar"]["karar_bekleme"]
    assert s["n"] == 1
    assert s["toplam_dk"] == 30.0  # z(10)..z(40), z(15)'ten degil
    assert acik_bul(out, "G-040")[0]["asama"] != "karar_bekleme"


def test_k3_ret_dogrudan_isleniyor_sureyi_sayar(tmp_path):
    k = kart("G-041", [
        (z(0), "olusturuldu"), (z(2), "isleniyor"), (z(10), "birlestirme-ret"),
        (z(25), "isleniyor")], durum="isleniyor")
    yaz(tmp_path, [k])
    s = kos(tmp_path, "--simdi", SIMDI)["asamalar"]["karar_bekleme"]
    assert s["n"] == 1 and s["toplam_dk"] == 15.0


def test_k3_ret_sonra_teslim_karar_bekleme_olarak_kapanir(tmp_path):
    k = kart("G-042", [
        (z(0), "olusturuldu"), (z(2), "isleniyor"), (z(10), "birlestirme-ret"),
        (z(70), "teslim")], durum="teslim")
    yaz(tmp_path, [k])
    out = kos(tmp_path, "--simdi", SIMDI)
    s = out["asamalar"]["karar_bekleme"]
    assert s["n"] == 1 and s["toplam_dk"] == 60.0
    assert out["acik"] == []


# ---- k4 (davranis 4) ----
def test_beklemeden_teslim_sonrasi_ret_toplama_bekleme_sayilmaz(tmp_path):
    yaz(tmp_path, [g074()])
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["asamalar"]["toplama_bekleme"]["n"] == 0
    a = acik_bul(out, "G-074")
    assert len(a) == 1 and a[0]["asama"] == "karar_bekleme"
    assert not [k for k in out["acik"] if k["asama"] == "toplama_bekleme"]


def test_g074_canli_darbogaz_karar_bekleme(tmp_path):
    yaz(tmp_path, [g074()])
    assert kos(tmp_path, "--simdi", SIMDI)["darbogaz"]["canli"] == "karar_bekleme"
