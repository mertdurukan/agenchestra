"""G-075: scripts/oner.py (veriye dayali baslangic basamagi onerisi + benzer kart uyarisi).

Sozlesme:
  sinif_normal(s) -> str                       'kod-duzenleme'->'kod'; None/'-'/''->'belirsiz'; digerleri kucuk harf
  basamak_oner(kartlar, kayitlar, sinif, metin='', min_n=5) -> {sinif, onerilen, gerekce, adaylar, benzer, uyarilar}
    grup = (sinif_normal, baslangic_basamak or basamak); ilk denetim (denetimler[0].karar 'onay'/'ret') sayilir
    P=(a+1)/(a+r+2); ort_usd = grup kart basi USD (kayitlar'da gorev==id toplami); beklenen_usd = ort_usd/P
    n>=min_n adaylar arasinda en kucuk beklenen_usd; hicbiri yoksa onerilen='T2', gerekce='yetersiz-veri'
  benzer(kartlar, metin, k=5) -> [{id, baslik, basamak, ret_sayisi, nedenler, skor}]  (TF-IDF kosinus, skor>0)
  KRITER_IPUCU: {neden_kodu: cumle}
  CLI: oner.py basamak --sinif S --metin M [--json] [--min-n N] [--sd DIZIN]
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(AD, "..", "scripts"))
ONER = os.path.join(SCRIPTS, "oner.py")
sys.path.insert(0, SCRIPTS)


class _OnerYukle:
    """Modulu ilk erisimde yukler: modul yokken toplama hatasi degil, test basarisizligi olusur."""

    def __getattr__(self, ad):
        import importlib
        return getattr(importlib.import_module("oner"), ad)


oner = _OnerYukle()


def kart(i, sinif="kod", bas="T2", denetimler=None, baslik="x", kriter=None, basamak=None):
    return {"id": i, "baslik": baslik, "sinif": sinif, "basamak": basamak or bas, "baslangic_basamak": bas,
            "kabul_kriterleri": kriter or [], "durum": "onaylandi",
            "denetimler": denetimler if denetimler is not None else []}


def d(karar, neden=None):
    return {"karar": karar, "neden": neden, "basamak": "T2"}


def usd(gorev, v, **ek):
    r = {"gorev": gorev, "maliyet_usd": v, "kaynak": "tur", "oturum": "o1", "agent_id": "a-" + gorev}
    r.update(ek)
    return r


def grup(prefix, bas, a, r, usd_kart, sinif="kod"):
    kartlar, kayit = [], []
    for j in range(a + r):
        i = f"G-{prefix}{j}"
        ilk = d("onay") if j < a else d("ret", "kapsam-eksik")
        kartlar.append(kart(i, sinif, bas, [ilk]))
        kayit.append(usd(i, usd_kart))
    return kartlar, kayit


def bo(kartlar, kayitlar, sinif, metin="", min_n=5, **kw):
    """Eski testler n=5 verisiyle yazildi: min_n acikca 5 verilir (varsayilan politikadan 20)."""
    return oner.basamak_oner(kartlar, kayitlar, sinif, metin, min_n, **kw)


def aday(sonuc, bas):
    return next(x for x in sonuc["adaylar"] if x["basamak"] == bas)


# ---- 2: sinif_normal
@pytest.mark.parametrize("girdi,beklenen", [
    ("kod-duzenleme", "kod"), ("kod", "kod"), ("KOD", "kod"), ("Analiz", "analiz"),
    (None, "belirsiz"), ("-", "belirsiz"), ("", "belirsiz"),
])
def test_sinif_normal(girdi, beklenen):
    assert oner.sinif_normal(girdi) == beklenen


# ---- 3: basamak_oner
def test_posterior_ve_beklenen_usd():
    k, m = grup("A", "T2", 4, 1, 0.10)
    s = bo(k, m, "kod")
    a = aday(s, "T2")
    assert a["n"] == 5
    assert a["ilk_gecis_olasiligi"] == pytest.approx(5 / 7)
    assert a["ort_usd"] == pytest.approx(0.10)
    assert a["alt_sinir"] < a["ilk_gecis_olasiligi"]
    assert a["beklenen_usd"] == pytest.approx(0.10 / a["alt_sinir"])
    assert s["onerilen"] == "T2" and s["gerekce"] != "yetersiz-veri"


def test_en_kucuk_beklenen_usd_secilir_ucuz_ama_dusuk_olasilik():
    k1, m1 = grup("A", "T1", 2, 3, 0.02)   # ucuz, alt sinir dusuk ama yine en ucuz
    k2, m2 = grup("B", "T2", 4, 1, 0.10)   # beklenen=0.14
    k3, m3 = grup("C", "T3", 5, 0, 0.50)   # P=6/7, beklenen=0.5833
    s = bo(k1 + k2 + k3, m1 + m2 + m3, "kod")
    assert s["onerilen"] == "T1"
    assert aday(s, "T1")["beklenen_usd"] == pytest.approx(0.02 / aday(s, "T1")["alt_sinir"])
    assert aday(s, "T3")["beklenen_usd"] == pytest.approx(0.50 / aday(s, "T3")["alt_sinir"])


def test_ucuz_basamak_cok_ret_alirsa_pahali_secilir():
    k1, m1 = grup("A", "T1", 0, 5, 0.05)   # P=1/7, beklenen=0.35
    k2, m2 = grup("B", "T2", 5, 0, 0.10)   # P=6/7, beklenen=0.1167
    s = bo(k1 + k2, m1 + m2, "kod")
    assert s["onerilen"] == "T2"
    assert aday(s, "T1")["ilk_gecis_olasiligi"] == pytest.approx(1 / 7)


def test_yeterli_veri_yoksa_t2_yetersiz_veri():
    k, m = grup("A", "T1", 3, 1, 0.01)     # n=4 < 5
    s = bo(k, m, "kod")
    assert s["onerilen"] == "T2" and s["gerekce"] == "yetersiz-veri"


def test_yetersiz_veride_t2_ucuz_t1_olsa_bile():
    k, m = grup("A", "T1", 4, 0, 0.01)
    s = bo(k, m, "kod")
    assert s["onerilen"] == "T2" and s["gerekce"] == "yetersiz-veri"


def test_bos_girdi():
    s = bo([], [], "kod")
    assert s["onerilen"] == "T2" and s["gerekce"] == "yetersiz-veri"
    assert s["adaylar"] == [] and s["benzer"] == [] and s["uyarilar"] == []
    assert s["sinif"] == "kod"


def test_min_n_ayarlanabilir():
    k, m = grup("A", "T1", 3, 0, 0.01)
    assert bo(k, m, "kod")["gerekce"] == "yetersiz-veri"
    s = bo(k, m, "kod", min_n=3)
    assert s["onerilen"] == "T1" and s["gerekce"] != "yetersiz-veri"


def test_n_tam_min_n_sinirinda_yeterli():
    k, m = grup("A", "T1", 5, 0, 0.01)
    assert bo(k, m, "kod")["onerilen"] == "T1"


def test_yalniz_ilk_denetim_sayilir_ve_denetimsiz_kart_sayilmaz():
    kartlar = [kart(f"G-{i}", "kod", "T1", [d("ret", "bicim"), d("onay")]) for i in range(5)]
    kartlar.append(kart("G-9", "kod", "T1", []))
    s = bo(kartlar, [usd(f"G-{i}", 0.1) for i in range(5)], "kod")
    a = aday(s, "T1")
    assert a["n"] == 5
    assert a["ilk_gecis_olasiligi"] == pytest.approx(1 / 7)  # a=0, r=5


def test_baslangic_basamak_gruplamada_kullanilir_yoksa_basamak():
    kartlar = [kart(f"G-{i}", "kod", "T1", [d("onay")], basamak="T3") for i in range(5)]
    s = bo(kartlar, [], "kod")
    assert [x["basamak"] for x in s["adaylar"]] == ["T1"]
    k2 = [kart(f"G-{i}", "kod", None, [d("onay")], basamak="T3") for i in range(5)]
    for c in k2:
        c["baslangic_basamak"] = None
    s2 = bo(k2, [], "kod")
    assert [x["basamak"] for x in s2["adaylar"]] == ["T3"]


def test_sinif_filtresi_ve_normallestirme():
    k, m = grup("A", "T1", 5, 0, 0.01, sinif="kod-duzenleme")
    k2, m2 = grup("B", "T2", 5, 0, 0.01, sinif="arastirma")
    s = bo(k + k2, m + m2, "kod")
    assert [x["basamak"] for x in s["adaylar"]] == ["T1"]
    s2 = bo(k + k2, m + m2, "kod-duzenleme")
    assert s2["sinif"] == "kod"


def test_belirsiz_sinif_gruplanir():
    kartlar = [kart(f"G-{i}", None, "T2", [d("onay")]) for i in range(5)]
    s = bo(kartlar, [], "-")
    assert s["sinif"] == "belirsiz" and aday(s, "T2")["n"] == 5


def test_kart_usd_gorev_toplami_ve_kartsiz_satir_yok_sayilir():
    kartlar = [kart(f"G-{i}", "kod", "T2", [d("onay")]) for i in range(5)]
    kayit = [usd("G-0", 0.2, agent_id="x"), usd("G-0", 0.3, agent_id="y"), usd("G-1", 0.5),
             usd("-", 99.0), usd("G-404", 99.0)]
    a = aday(bo(kartlar, kayit, "kod"), "T2")
    assert a["ort_usd"] == pytest.approx(1.0 / 5)


# ---- 5: benzer
BENZ = [
    kart("G-1", baslik="Telegram bildirim kanali ekle", kriter=["bildirim gonderilir"],
         denetimler=[d("ret", "kanit-yok")]),
    kart("G-2", baslik="Maliyet raporu panel grafigi", kriter=["grafik cizilir"]),
    kart("G-3", baslik="Zamanlayici hata duzeltmesi", kriter=["hata giderilir"]),
]


def test_benzer_acikca_benzer_en_ustte():
    r = oner.benzer(BENZ, "telegram bildirim kanali duzenle")
    assert r[0]["id"] == "G-1"
    assert r[0]["skor"] > 0
    assert set(r[0]) >= {"id", "baslik", "basamak", "ret_sayisi", "nedenler", "skor"}
    assert r[0]["ret_sayisi"] == 1 and "kanit-yok" in r[0]["nedenler"]


def test_benzer_sifir_skor_donmez():
    r = oner.benzer(BENZ, "telegram bildirim")
    assert all(x["skor"] > 0 for x in r)
    assert "G-2" not in [x["id"] for x in r] and "G-3" not in [x["id"] for x in r]


def test_benzer_hic_ortak_yoksa_bos_ve_bos_metin():
    assert oner.benzer(BENZ, "kuantum fizigi") == []
    assert oner.benzer(BENZ, "") == []
    assert oner.benzer([], "telegram") == []


def test_benzer_k_siniri_ve_sirali():
    kartlar = [kart(f"G-{i}", baslik="telegram bildirim " + "ek " * i) for i in range(1, 9)]
    r = oner.benzer(kartlar, "telegram bildirim", k=3)
    assert len(r) == 3
    assert [x["skor"] for x in r] == sorted((x["skor"] for x in r), reverse=True)


def test_benzer_kabul_kriteri_metni_da_katilir_ve_buyuk_kucuk_harf():
    kartlar = [kart("G-1", baslik="alfa", kriter=["Zamanlayici HATASI giderilir"]), kart("G-2", baslik="beta")]
    r = oner.benzer(kartlar, "zamanlayici hatasi")
    assert [x["id"] for x in r] == ["G-1"]


def test_benzer_kisa_tokenlar_yok_sayilir():
    kartlar = [kart("G-1", baslik="ve ile bu"), kart("G-2", baslik="uzun kelime")]
    assert oner.benzer(kartlar, "ve ile bu") == []


def test_dis_kutuphane_yok():
    with open(ONER, encoding="utf-8") as f:
        kaynak = f.read()
    for yasak in ("sklearn", "numpy", "scipy", "pandas", "nltk"):
        assert yasak not in kaynak


# ---- 6: uyarilar
BES = ["kapsam-eksik", "sayi-tutarsiz", "kanit-yok", "kriter-belirsiz", "talimat-ihlali"]


def test_kriter_ipucu_bes_kod_tanimli():
    for kod in BES:
        assert isinstance(oner.KRITER_IPUCU.get(kod), str) and len(oner.KRITER_IPUCU[kod]) > 10
    assert len({oner.KRITER_IPUCU[k] for k in BES}) == 5


def test_uyarilar_benzer_kartlardaki_nedenler_icin_ipucu():
    kartlar = [kart("G-1", baslik="telegram bildirim",
                    denetimler=[d("ret", "kapsam-eksik"), d("ret", "sayi-tutarsiz"), d("onay")]),
               kart("G-2", baslik="telegram bildirim kanal", denetimler=[d("ret", "kanit-yok")]),
               kart("G-3", baslik="tamamen baska konu", denetimler=[d("ret", "talimat-ihlali")])]
    s = bo(kartlar, [], "kod", metin="telegram bildirim")
    metin = "\n".join(s["uyarilar"])
    for kod in ("kapsam-eksik", "sayi-tutarsiz", "kanit-yok"):
        assert oner.KRITER_IPUCU[kod] in metin
    assert oner.KRITER_IPUCU["talimat-ihlali"] not in metin
    assert {"G-1", "G-2"} <= {b["id"] for b in s["benzer"]}
    assert "G-3" not in {b["id"] for b in s["benzer"]}


def test_uyarilar_ayni_neden_tekrarlanmaz_ve_bos_metinde_bos():
    kartlar = [kart(f"G-{i}", baslik="telegram bildirim", denetimler=[d("ret", "kanit-yok")]) for i in range(3)]
    s = bo(kartlar, [], "kod", metin="telegram bildirim")
    assert sum(oner.KRITER_IPUCU["kanit-yok"] in u for u in s["uyarilar"]) == 1
    assert bo(kartlar, [], "kod", metin="")["uyarilar"] == []


# ---- 1, 4, 7: CLI ve maliyet tekillestirme
def _sd(kartlar, satirlar):
    sd = tempfile.mkdtemp()
    os.makedirs(os.path.join(sd, "gorevler"))
    for c in kartlar:
        with open(os.path.join(sd, "gorevler", c["id"] + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(c, f)
    with open(os.path.join(sd, "maliyet.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for r in satirlar:
            f.write(json.dumps(r) + "\n")
    return sd


def _cli(*args):
    return subprocess.run([sys.executable, ONER, *args], capture_output=True, text=True, encoding="utf-8")


def test_maliyet_hook_tur_cift_satir_cift_sayilmaz():
    kartlar = [kart(f"G-{i}", "kod", "T2", [d("onay")]) for i in range(5)]
    satirlar = []
    for i in range(5):
        g = f"G-{i}"
        satirlar.append({"gorev": g, "maliyet_usd": 1.0, "kaynak": "tur", "oturum": "o", "agent_id": "a" + g})
        satirlar.append({"gorev": g, "maliyet_usd": 1.0, "kaynak": "hook", "oturum": "o", "agent_id": "a" + g,
                         "zaman": "2026-01-01T00:00:00"})
    sd = _sd(kartlar, satirlar)
    p = _cli("basamak", "--sinif", "kod", "--json", "--min-n", "5", "--sd", sd)
    assert p.returncode == 0, p.stderr
    a = next(x for x in json.loads(p.stdout)["adaylar"] if x["basamak"] == "T2")
    assert a["ort_usd"] == pytest.approx(1.0)
    assert a["beklenen_usd"] == pytest.approx(1.0 / a["alt_sinir"])


def test_cli_json_gecerli_ve_sema():
    kartlar = [kart(f"G-{i}", "kod", "T1", [d("onay")], baslik="telegram bildirim") for i in range(5)]
    sd = _sd(kartlar, [])
    p = _cli("basamak", "--sinif", "kod", "--metin", "telegram bildirim", "--json", "--min-n", "5", "--sd", sd)
    assert p.returncode == 0, p.stderr
    j = json.loads(p.stdout)
    assert set(j) >= {"sinif", "onerilen", "gerekce", "adaylar", "benzer", "uyarilar"}
    assert j["onerilen"] == "T1"
    assert j["benzer"]


def test_cli_min_n_etkisi():
    kartlar = [kart(f"G-{i}", "kod", "T1", [d("onay")]) for i in range(3)]
    sd = _sd(kartlar, [])
    assert json.loads(_cli("basamak", "--sinif", "kod", "--json", "--sd", sd).stdout)["gerekce"] == "yetersiz-veri"
    assert json.loads(_cli("basamak", "--sinif", "kod", "--json", "--min-n", "3", "--sd", sd).stdout)["onerilen"] == "T1"


def test_cli_duz_cikti_en_cok_15_satir():
    kartlar = []
    for b in ("T1", "T2", "T3"):
        for i in range(6):
            kartlar.append(kart(f"G-{b}{i}", "kod", b, [d("onay") if i % 2 else d("ret", "kapsam-eksik")],
                                baslik="telegram bildirim kanali"))
    sd = _sd(kartlar, [])
    p = _cli("basamak", "--sinif", "kod", "--metin", "telegram bildirim kanali", "--min-n", "5", "--sd", sd)
    assert p.returncode == 0, p.stderr
    satirlar = [s for s in p.stdout.splitlines() if s.strip()]
    assert 1 <= len(satirlar) <= 15
    assert "T" in p.stdout
    with pytest.raises(ValueError):
        json.loads(p.stdout)


def test_cli_bos_durum_klasoru_cokmez():
    sd = _sd([], [])
    p = _cli("basamak", "--sinif", "kod", "--json", "--sd", sd)
    assert p.returncode == 0, p.stderr
    j = json.loads(p.stdout)
    assert j["onerilen"] == "T2" and j["gerekce"] == "yetersiz-veri"


# ---- G-162: alt sinir, politika min_n, beklenen_dk
def test_alt_sinir_n_kucukken_dusuk_ayni_oran():
    kucuk = oner.alt_sinir(3, 1)      # n=4, oran 0.75
    buyuk = oner.alt_sinir(30, 10)    # n=40, oran 0.75
    assert 0 < kucuk < buyuk < 0.75
    assert oner.alt_sinir(0, 0) == pytest.approx(0.2)   # Beta(1,1) = U(0,1): %20 kuantil


def test_alt_sinir_beta_kuantil_dogru():
    # Beta(2,1): CDF=x^2 -> %20 kuantil = sqrt(0.2)
    assert oner.alt_sinir(1, 0) == pytest.approx(0.2 ** 0.5, abs=1e-9)


def test_min_n_altindaki_basamak_aday_disi_ust_basamaga_gider():
    k1, m1 = grup("A", "T1", 6, 0, 0.01)     # n=6 < 20, en ucuz
    k2, m2 = grup("B", "T2", 22, 0, 0.10)    # n=22 >= 20
    s = oner.basamak_oner(k1 + k2, m1 + m2, "kod")   # min_n politikadan (varsayilan 20)
    assert s["onerilen"] == "T2"
    assert s["gerekce"] == "yetersiz-veri"
    assert s["elenen"] == ["T1"]
    assert aday(s, "T1")["n"] == 6
    s5 = bo(k1 + k2, m1 + m2, "kod", min_n=5)
    assert s5["onerilen"] == "T1"


def test_varsayilan_min_n_20_hic_yeterli_yoksa_t2():
    k, m = grup("A", "T1", 6, 0, 0.01)
    s = oner.basamak_oner(k, m, "kod", min_n=None)
    assert s["onerilen"] == "T2" and s["gerekce"] == "yetersiz-veri"


def test_politika_varsayilanlari():
    p = oner.politika()
    assert p["min_n"] >= 1 and p["usd_fark"] >= 0


def _sureli(prefix, bas, n, usd_kart, dk):
    kartlar, kayit = [], []
    for j in range(n):
        i = f"G-{prefix}{j}"
        c = kart(i, "kod", bas, [d("onay")])
        c["olusturma"] = "2026-10-17T10:00:00+00:00"
        c["gecmis"] = [{"zaman": f"2026-10-17T{10 + dk // 60:02d}:{dk % 60:02d}:00+00:00", "olay": "teslim"}]
        kartlar.append(c)
        kayit.append(usd(i, usd_kart))
    return kartlar, kayit


def test_beklenen_dk_medyan_bolu_alt_sinir():
    k, m = _sureli("A", "T2", 20, 0.10, 30)
    a = aday(oner.basamak_oner(k, m, "kod"), "T2")
    assert a["medyan_dk"] == pytest.approx(30.0)
    assert a["beklenen_dk"] == pytest.approx(30.0 / a["alt_sinir"])


def test_usd_fark_icinde_beklenen_dk_kucuk_secilir():
    k1, m1 = _sureli("A", "T1", 20, 0.100, 50)   # biraz ucuz ama yavas
    k2, m2 = _sureli("B", "T2", 20, 0.105, 10)   # %5 pahali ama hizli
    s = oner.basamak_oner(k1 + k2, m1 + m2, "kod", usd_fark=0.10)
    assert s["onerilen"] == "T2"
    assert aday(s, "T2")["beklenen_dk"] < aday(s, "T1")["beklenen_dk"]
    assert aday(s, "T1")["beklenen_usd"] < aday(s, "T2")["beklenen_usd"]


def test_usd_fark_disinda_ucuz_olan_kalir():
    k1, m1 = _sureli("A", "T1", 20, 0.100, 50)
    k2, m2 = _sureli("B", "T2", 20, 0.200, 10)
    assert oner.basamak_oner(k1 + k2, m1 + m2, "kod", usd_fark=0.10)["onerilen"] == "T1"


def test_cli_json_alanlari_alt_sinir_beklenen_dk():
    kartlar = []
    for i in range(6):
        c = kart(f"G-{i}", "kod", "T1", [d("onay")])
        c["olusturma"] = "2026-10-17T10:00:00+00:00"
        c["gecmis"] = [{"zaman": "2026-10-17T10:05:00+00:00", "olay": "teslim"}]
        kartlar.append(c)
    sd = _sd(kartlar, [])
    j = json.loads(_cli("basamak", "--sinif", "kod", "--json", "--sd", sd).stdout)
    a = j["adaylar"][0]
    assert {"n", "alt_sinir", "beklenen_usd", "beklenen_dk"} <= set(a)
    assert a["beklenen_dk"] == pytest.approx(5.0 / a["alt_sinir"])
    assert j["onerilen"] == "T2" and j["gerekce"] == "yetersiz-veri"


def test_cli_altkomutsuz_hata_kodu():
    assert _cli().returncode != 0


# ---- 8: LF, BOM yok
def test_oner_lf_ve_bomsuz():
    with open(ONER, "rb") as f:
        b = f.read()
    assert not b.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in b
    with open(os.path.join(AD, "test_oner.py"), "rb") as f:
        t = f.read()
    assert not t.startswith(b"\xef\xbb\xbf") and b"\r\n" not in t
