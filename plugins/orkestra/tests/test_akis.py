"""akis.py (G-082) kabul testleri: kart asama sureleri, acik kart yasi, darbogaz.

Testler betigi CLI uzerinden (--json) calistirir; kart dosyalari tmp durum dizininde kurulur.
"""
import ast
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "akis.py"
T0 = datetime.datetime(2026, 1, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
ASAMALAR = ["alinma_bekleme", "iscide_ilk", "iscide_duzeltme",
            "denetimde", "toplama_bekleme", "karar_bekleme"]


def z(dk, sn=0):
    return (T0 + datetime.timedelta(minutes=dk, seconds=sn)).isoformat()


def kart(cid, olaylar, durum="isleniyor", baslik=None):
    return {"id": cid, "baslik": baslik or f"Baslik {cid}", "durum": durum,
            "gecmis": [{"zaman": t, "olay": o} for t, o in olaylar]}


def yaz(sd, kartlar, ekstra=None):
    g = Path(sd) / "gorevler"
    g.mkdir(parents=True, exist_ok=True)
    for k in kartlar:
        (g / f"{k['id']}.json").write_text(json.dumps(k), encoding="utf-8")
    for ad, icerik in (ekstra or {}).items():
        (g / ad).write_text(icerik, encoding="utf-8")


def kos(sd, *ek, json_cikti=True):
    cmd = [sys.executable, str(SCRIPT), "--sd", str(sd), *ek]
    if json_cikti:
        cmd.append("--json")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if json_cikti else r.stdout


SIMDI = z(200)


# ---- toplu fixture: 3 tamamlanmis kart ----
def tam_kartlar():
    a = kart("G-001", [
        (z(0), "olusturuldu"), (z(10), "isleniyor"), (z(30), "is-bitti"),
        (z(35), "denetim:ret"), (z(40), "isleniyor"), (z(60), "is-bitti"),
        (z(66), "denetim:onay"), (z(70), "teslim")], durum="teslim")
    b = kart("G-002", [
        (z(0), "olusturuldu"), (z(4), "isleniyor"), (z(10), "is-bitti"),
        (z(12), "denetim:onay"), (z(30), "teslim")], durum="teslim")
    c = kart("G-003", [
        (z(0), "olusturuldu"), (z(2), "isleniyor"), (z(5), "beklemede"),
        (z(25), "isleniyor"), (z(30), "is-bitti"), (z(31), "denetim:onay"),
        (z(33), "teslim")], durum="teslim")
    return a, b, c


@pytest.fixture
def sd_tam(tmp_path):
    yaz(tmp_path, tam_kartlar())
    return tmp_path


def test_k1_json_sekli(sd_tam):
    out = kos(sd_tam, "--simdi", SIMDI)
    assert set(out) == {"asamalar", "acik", "darbogaz", "kart_sayisi"}
    assert set(out["asamalar"]) == set(ASAMALAR)
    for ad in ASAMALAR:
        assert set(out["asamalar"][ad]) == {"n", "medyan_dk", "p90_dk", "toplam_dk"}
    assert out["kart_sayisi"] == 3


def test_k1_bos_dizinde_n0_null(tmp_path):
    (tmp_path / "gorevler").mkdir()
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["kart_sayisi"] == 0
    assert out["acik"] == []
    assert out["darbogaz"]["canli"] is None
    for ad in ASAMALAR:
        s = out["asamalar"][ad]
        assert s["n"] == 0 and s["medyan_dk"] is None and s["p90_dk"] is None
        assert s["toplam_dk"] == 0


def test_k1_gorevler_dizini_yoksa_hata_vermez(tmp_path):
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["kart_sayisi"] == 0


def test_k1_dakika_tek_ondalik_ve_p90_en_yakin_sira(tmp_path):
    # 2 dk 20 sn -> 2.3 ; tek kart, n=1 -> medyan=p90=toplam
    yaz(tmp_path, [kart("G-001", [(z(0), "olusturuldu"), (z(2, 20), "isleniyor")])])
    s = kos(tmp_path, "--simdi", SIMDI)["asamalar"]["alinma_bekleme"]
    assert s["n"] == 1
    assert s["medyan_dk"] == 2.3 and s["p90_dk"] == 2.3 and s["toplam_dk"] == 2.3


def test_k1_p90_10_ogede_9uncu(tmp_path):
    # alinma sureleri 1..10 dk: ceil(0.9*10)=9 -> 9.0 ; medyan (5+6)/2 = 5.5
    kartlar = [kart(f"G-{i:03d}", [(z(0), "olusturuldu"), (z(i), "isleniyor")])
               for i in range(1, 11)]
    yaz(tmp_path, kartlar)
    s = kos(tmp_path, "--simdi", SIMDI)["asamalar"]["alinma_bekleme"]
    assert s["n"] == 10
    assert s["p90_dk"] == 9.0
    assert s["medyan_dk"] == 5.5
    assert s["toplam_dk"] == 55.0


def test_k2_asama_sureleri_birebir(sd_tam):
    a = kos(sd_tam, "--simdi", SIMDI)["asamalar"]
    beklenen = {
        "alinma_bekleme": (3, 4.0, 10.0, 16.0),
        "iscide_ilk": (3, 20.0, 28.0, 54.0),
        "iscide_duzeltme": (1, 20.0, 20.0, 20.0),
        "denetimde": (3, 2.0, 11.0, 14.0),     # G-001: 5 + 6 = 11 tek deger
        "toplama_bekleme": (3, 4.0, 18.0, 24.0),
        "karar_bekleme": (1, 20.0, 20.0, 20.0),
    }
    for ad, (n, med, p90, top) in beklenen.items():
        assert a[ad] == {"n": n, "medyan_dk": med, "p90_dk": p90, "toplam_dk": top}, ad


def test_k2_ret_sonrasi_tur_duzeltmeye_gider(tmp_path):
    yaz(tmp_path, [kart("G-001", [
        (z(0), "olusturuldu"), (z(1), "isleniyor"), (z(11), "is-bitti"),
        (z(12), "denetim:ret"), (z(13), "isleniyor"), (z(18), "is-bitti"),
        (z(19), "denetim:ret"), (z(20), "isleniyor"), (z(23), "is-bitti"),
        (z(24), "denetim:onay"), (z(25), "teslim")], durum="teslim")])
    a = kos(tmp_path, "--simdi", SIMDI)["asamalar"]
    assert a["iscide_ilk"]["toplam_dk"] == 10.0 and a["iscide_ilk"]["n"] == 1
    # iki duzeltme turu (5 + 3) kart basina tek deger
    assert a["iscide_duzeltme"]["n"] == 1 and a["iscide_duzeltme"]["toplam_dk"] == 8.0
    # uc denetim turu (1 + 1 + 1) tek deger
    assert a["denetimde"]["n"] == 1 and a["denetimde"]["toplam_dk"] == 3.0


def test_k2_ajan_bitti_gibi_olaylar_asama_degistirmez(tmp_path):
    k = kart("G-001", [
        (z(0), "olusturuldu"), (z(1), "isleniyor"), (z(3), "ajan-bitti"),
        (z(4), "test-ayar"), (z(6), "calisma-agaci"), (z(10), "is-bitti"),
        (z(12), "birlestirildi"), (z(15), "denetim:onay"), (z(16), "yukseltme"),
        (z(20), "teslim")], durum="teslim")
    yaz(tmp_path, [k])
    a = kos(tmp_path, "--simdi", SIMDI)["asamalar"]
    assert a["iscide_ilk"]["toplam_dk"] == 9.0
    assert a["denetimde"]["toplam_dk"] == 5.0
    assert a["toplama_bekleme"]["toplam_dk"] == 5.0


def test_k2_beklemeden_teslim_karari_kapatir(tmp_path):
    yaz(tmp_path, [kart("G-001", [
        (z(0), "olusturuldu"), (z(1), "isleniyor"), (z(2), "beklemede"),
        (z(12), "beklemeden-teslim")], durum="teslim")])
    a = kos(tmp_path, "--simdi", SIMDI)
    assert a["asamalar"]["karar_bekleme"]["n"] == 1
    assert a["asamalar"]["karar_bekleme"]["toplam_dk"] == 10.0
    assert a["acik"] == []


# ---- acik kartlar ----
def acik_kartlar():
    return [
        kart("G-010", [(z(100), "olusturuldu")], baslik="D"),
        kart("G-011", [(z(0), "olusturuldu"), (z(50), "isleniyor")], baslik="E"),
        kart("G-012", [(z(0), "olusturuldu"), (z(1), "isleniyor"),
                       (z(120), "beklemede")], durum="beklemede", baslik="F"),
        kart("G-013", [(z(0), "olusturuldu"), (z(1), "isleniyor"), (z(5), "is-bitti"),
                       (z(6), "denetim:ret")], baslik="G"),
        kart("G-014", [(z(0), "olusturuldu"), (z(1), "isleniyor"),
                       (z(190), "is-bitti")], baslik="H"),
        kart("G-015", [(z(0), "olusturuldu"), (z(1), "isleniyor"), (z(5), "is-bitti"),
                       (z(180), "denetim:onay")], baslik="I"),
        kart("G-016", [(z(0), "olusturuldu"), (z(1), "isleniyor"), (z(2), "is-bitti"),
                       (z(3), "denetim:onay"), (z(4), "teslim")], durum="teslim"),
        kart("G-017", [(z(0), "olusturuldu"), (z(1), "iptal")], durum="iptal"),
    ]


def test_k3_acik_liste_sirali_ve_asamali(tmp_path):
    yaz(tmp_path, acik_kartlar())
    out = kos(tmp_path, "--simdi", SIMDI)
    acik = out["acik"]
    assert [(k["id"], k["asama"], k["yas_dk"]) for k in acik] == [
        ("G-013", "alinma_bekleme", 194.0),
        ("G-011", "iscide_ilk", 150.0),
        ("G-010", "alinma_bekleme", 100.0),
        ("G-012", "karar_bekleme", 80.0),
        ("G-015", "toplama_bekleme", 20.0),
        ("G-014", "denetimde", 10.0),
    ]
    assert set(acik[0]) == {"id", "baslik", "asama", "yas_dk"}
    assert acik[0]["baslik"] == "G"


def test_k3_duzeltme_turundaki_acik_kart(tmp_path):
    yaz(tmp_path, [kart("G-001", [
        (z(0), "olusturuldu"), (z(1), "isleniyor"), (z(5), "is-bitti"),
        (z(6), "denetim:ret"), (z(100), "isleniyor")])])
    acik = kos(tmp_path, "--simdi", SIMDI)["acik"]
    assert acik[0]["asama"] == "iscide_duzeltme" and acik[0]["yas_dk"] == 100.0


def test_k3_acik_kart_kart_sayisina_girer_iptal_girmez(tmp_path):
    yaz(tmp_path, acik_kartlar())
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["kart_sayisi"] == 7  # 8 dosya - 1 iptal


def test_k3_beklemede_donup_islenen_kart_acik_asama(tmp_path):
    yaz(tmp_path, [kart("G-001", [
        (z(0), "olusturuldu"), (z(1), "isleniyor"), (z(5), "beklemede"),
        (z(50), "isleniyor")])])
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["acik"][0]["asama"] == "iscide_ilk"
    assert out["acik"][0]["yas_dk"] == 150.0
    assert out["asamalar"]["karar_bekleme"]["n"] == 1
    assert out["asamalar"]["karar_bekleme"]["toplam_dk"] == 45.0


# ---- darbogaz ----
def test_k4_darbogaz_canli_ve_gecmis(tmp_path):
    yaz(tmp_path, acik_kartlar())
    d = kos(tmp_path, "--simdi", SIMDI)["darbogaz"]
    assert set(d) == {"canli", "gecmis"}
    # alinma_bekleme acik yas toplami 194+100 = 294 en yuksek
    assert d["canli"] == "alinma_bekleme"
    assert d["gecmis"] in ASAMALAR


def test_k4_gecmis_en_yuksek_toplam(sd_tam):
    d = kos(sd_tam, "--simdi", SIMDI)["darbogaz"]
    assert d["gecmis"] == "iscide_ilk"  # toplam 54
    assert d["canli"] is None           # acik kart yok


def test_k4_canli_yas_toplami_adet_degil_toplam_sayilir(tmp_path):
    # 2 kart denetimde (yas 5+5), 1 kart iscide_ilk (yas 150) -> iscide_ilk
    yaz(tmp_path, [
        kart("G-001", [(z(0), "olusturuldu"), (z(1), "isleniyor"), (z(195), "is-bitti")]),
        kart("G-002", [(z(0), "olusturuldu"), (z(1), "isleniyor"), (z(195), "is-bitti")]),
        kart("G-003", [(z(0), "olusturuldu"), (z(50), "isleniyor")]),
    ])
    assert kos(tmp_path, "--simdi", SIMDI)["darbogaz"]["canli"] == "iscide_ilk"


# ---- saglamlik ----
def test_k5_gecersiz_dosyalar_sayilmaz(tmp_path):
    a, b, c = tam_kartlar()
    yaz(tmp_path, [a, b, c], ekstra={
        "G-001.denetim.json": json.dumps({"gecmis": [{"zaman": z(0), "olay": "olusturuldu"}]}),
        "G-001.onkontrol.json": json.dumps({"gecmis": [{"zaman": z(0), "olay": "olusturuldu"}]}),
        "G-002.lock": "kilit",
        "G-090.json": json.dumps([{"gecmis": []}]),
        "G-091.json": "{bozuk json",
        "G-092.json": json.dumps({"id": "G-092", "durum": "isleniyor", "baslik": "x"}),
        "G-093.json": "",
    })
    yaz(tmp_path, [kart("G-094", [(z(0), "olusturuldu"), (z(1), "iptal")], durum="iptal")])
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["kart_sayisi"] == 3
    assert out["asamalar"]["alinma_bekleme"]["n"] == 3
    assert out["acik"] == []


def test_k5_tzsiz_zaman_yerel_kabul_edilir(tmp_path):
    def yerel(dk):
        t = (T0 + datetime.timedelta(minutes=dk)).astimezone()
        return t.replace(tzinfo=None).isoformat()
    yaz(tmp_path, [kart("G-001", [(yerel(0), "olusturuldu"), (yerel(10), "isleniyor")])])
    simdi = (T0 + datetime.timedelta(minutes=30)).isoformat()
    out = kos(tmp_path, "--simdi", simdi)
    assert out["asamalar"]["alinma_bekleme"]["toplam_dk"] == 10.0
    # isleniyor +10'dan simdi +30'a = 20 dk
    assert out["acik"][0]["yas_dk"] == 20.0


def test_k5_karisik_tz_yerel_ile_utc_tutarli(tmp_path):
    yerel0 = T0.astimezone().replace(tzinfo=None).isoformat()
    yaz(tmp_path, [kart("G-001", [(yerel0, "olusturuldu"), (z(7), "isleniyor")])])
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["asamalar"]["alinma_bekleme"]["toplam_dk"] == 7.0


def test_k5_olay_sirasi_karisik_zamana_gore_siralanir(tmp_path):
    a, b, c = tam_kartlar()
    for k in (a, b, c):
        k["gecmis"] = list(reversed(k["gecmis"]))
    yaz(tmp_path, [a, b, c])
    karisik = kos(tmp_path, "--simdi", SIMDI)
    d = tmp_path / "duz"
    yaz(d, tam_kartlar())
    duz = kos(d, "--simdi", SIMDI)
    assert karisik == duz


def test_k5_bozuk_olay_ogesi_hata_vermez(tmp_path):
    k = kart("G-001", [(z(0), "olusturuldu"), (z(5), "isleniyor")])
    k["gecmis"].insert(1, "olay-degil")
    k["gecmis"].append({"zaman": "bozuk-zaman", "olay": "teslim"})
    k["gecmis"].append({"olay": "teslim"})
    yaz(tmp_path, [k])
    out = kos(tmp_path, "--simdi", SIMDI)
    assert out["asamalar"]["alinma_bekleme"]["toplam_dk"] == 5.0


# ---- gun / simdi / metin ----
def test_k6_gun_suzgeci(tmp_path):
    eski = [(z(-30 * 1440), "olusturuldu"), (z(-30 * 1440 + 10), "isleniyor"),
            (z(-30 * 1440 + 20), "is-bitti"), (z(-30 * 1440 + 21), "denetim:onay"),
            (z(-30 * 1440 + 22), "teslim")]
    yeni = [(z(190), "olusturuldu"), (z(195), "isleniyor")]
    yaz(tmp_path, [kart("G-001", eski, durum="teslim"), kart("G-002", yeni)])
    tum = kos(tmp_path, "--simdi", SIMDI)
    assert tum["kart_sayisi"] == 2
    son = kos(tmp_path, "--simdi", SIMDI, "--gun", "7")
    assert son["kart_sayisi"] == 1
    assert son["asamalar"]["alinma_bekleme"]["n"] == 1
    assert son["asamalar"]["alinma_bekleme"]["toplam_dk"] == 5.0
    assert son["asamalar"]["denetimde"]["n"] == 0


def test_k6_simdi_yasi_belirler(tmp_path):
    yaz(tmp_path, [kart("G-001", [(z(0), "olusturuldu")])])
    a = kos(tmp_path, "--simdi", z(60))["acik"][0]["yas_dk"]
    b = kos(tmp_path, "--simdi", z(90))["acik"][0]["yas_dk"]
    assert (a, b) == (60.0, 90.0)


def test_k6_metin_tablo_turkce(tmp_path):
    yaz(tmp_path, acik_kartlar() + list(tam_kartlar()))
    cikti = kos(tmp_path, "--simdi", SIMDI, json_cikti=False)
    low = cikti.lower()
    for ad in ASAMALAR:
        assert ad in cikti
    for kelime in ("medyan", "p90", "toplam", "açık"):
        assert kelime in low, kelime
    assert "G-013" in cikti  # en yasli acik kart
    satirlar = [s for s in cikti.splitlines() if s.strip()]
    assert "darboğaz" in satirlar[-1].lower()
    with pytest.raises(ValueError):
        json.loads(cikti)


def test_k6_metin_bos_dizinde_calisir(tmp_path):
    cikti = kos(tmp_path, "--simdi", SIMDI, json_cikti=False)
    assert "darboğaz" in [s for s in cikti.splitlines() if s.strip()][-1].lower()


# ---- k7 ----
def test_k7_salt_okuma(tmp_path):
    yaz(tmp_path, acik_kartlar())

    def anlik():
        return sorted((str(p.relative_to(tmp_path)), p.stat().st_mtime_ns, p.stat().st_size)
                      for p in tmp_path.rglob("*"))
    once = anlik()
    kos(tmp_path, "--simdi", SIMDI)
    kos(tmp_path, "--simdi", SIMDI, json_cikti=False)
    assert anlik() == once


def test_k7_dosya_bicimi_ve_importlar():
    assert SCRIPT.is_file()
    ham = SCRIPT.read_bytes()
    assert not ham.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in ham
    ham.decode("utf-8")
    agac = ast.parse(ham.decode("utf-8"))
    modüller = set()
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            modüller |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            modüller.add(n.module.split(".")[0])
    izinli = set(sys.stdlib_module_names) | {"ork_lib", "__future__"}
    assert modüller <= izinli, modüller - izinli
    yasak = {"hook", "ozet", "panel", "orkestra", "niyet"}
    assert not (modüller & yasak)
