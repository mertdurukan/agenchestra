"""I-058 P2 (G-163): analitik._planlayici planlayıcı modeli x sınıf x basamak tablosu, maliyet rapor MD ve KPI satırı."""
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import analitik as A  # noqa: E402
import kpi  # noqa: E402


def z(sa, dk=0):
    sa, dk = sa + dk // 60, dk % 60
    return f"2026-03-10T{sa:02d}:{dk:02d}:00+03:00"


def kart(gid, plan=None, oturum="o1", sinif="kod", bas="T2", durum="teslim", karar=("onay",), olus=(10, 0), teslim_dk=30,
         isci=2):
    gecmis = [{"zaman": z(*olus), "olay": "olusturuldu"}]
    if teslim_dk is not None:
        gecmis.append({"zaman": z(olus[0], olus[1] + teslim_dk), "olay": "teslim"})
    k = {"id": gid, "sinif": sinif, "basamak": bas, "baslangic_basamak": bas, "durum": durum, "olusturma": z(*olus),
         "oturum": oturum, "gecmis": gecmis, "isciler": [f"{gid}-i{i}" for i in range(isci)],
         "denetimler": [{"zaman": z(23), "sira": i + 1, "karar": c, "basamak": bas} for i, c in enumerate(karar)]}
    if plan is not None:
        k["plan_modeli"] = plan
    return k


def mal(gorev, ajan, usd, surec="is", model="claude-sonnet-5-5", oturum="o1"):
    return {"zaman": z(10), "oturum": oturum, "gorev": gorev, "agent_id": f"{gorev}-{ajan}", "ajan": ajan, "surec": surec,
            "model": model, "maliyet_usd": usd, "kaynak": "tur"}


def ana(oturum, model, usd):
    return {"zaman": z(9), "oturum": oturum, "gorev": "-", "agent_id": None, "ajan": "ana-ajan", "surec": "is",
            "model": model, "maliyet_usd": usd, "kaynak": "hook"}


def satir(sonuc, plan, sinif="*", bas="*"):
    liste = sonuc["toplam"] if sinif == "*" else sonuc["satirlar"]
    return next(r for r in liste if r["planlayici"] == plan and r["sinif"] == sinif and r["baslangic_basamak"] == bas)


# opus: 3 kart (2 ilk seferde onay, 1 ret->onay), sonnet: 2 kart; kodlu hücre n=3
KARTLAR = [
    kart("G-1", plan="claude-opus-4-7", karar=("onay",), teslim_dk=30, isci=2),
    kart("G-2", plan="claude-opus-4-7", karar=("onay",), teslim_dk=50, isci=4),
    kart("G-3", plan="claude-opus-4-7", karar=("ret", "onay"), teslim_dk=100, isci=6),
    kart("G-4", plan="claude-sonnet-5-5", karar=("onay",), teslim_dk=10, isci=2, sinif="belge", bas="T1"),
    kart("G-5", plan="claude-sonnet-5-5", karar=("ret",), durum="reddedildi", teslim_dk=None, isci=2, sinif="belge", bas="T1"),
    kart("G-6", plan="claude-opus-4-7", durum="iptal", karar=(), teslim_dk=None),
]
KAYITLAR = [
    mal("G-1", "isci-t2", 1.0), mal("G-1", "orkestra:denetci", 0.5, surec="denetim"),
    mal("G-2", "isci-t2", 2.0), mal("G-2", "orkestra:denetci", 0.5, surec="denetim"),
    mal("G-3", "isci-t2", 3.0), mal("G-3", "orkestra:denetci", 1.0, surec="denetim"),
    mal("G-4", "isci-t1", 0.2), mal("G-4", "orkestra:denetci", 0.1, surec="denetim"),
    mal("G-5", "isci-t1", 0.4), mal("G-5", "orkestra:denetci", 0.1, surec="denetim"),
    mal("G-6", "isci-t2", 9.0),
]


class Planlayici(unittest.TestCase):
    def test_toplam_satirlari_ve_iptal_disarida(self):
        s = A._planlayici(KARTLAR, KAYITLAR, 3)
        o = satir(s, "opus")
        self.assertEqual(o["n"], 3)                       # iptal G-6 sayılmaz
        self.assertEqual(o["denetlenen"], 3)
        self.assertAlmostEqual(o["ilk_gecis"], 0.667, places=3)
        self.assertEqual(o["ret"], 1)
        self.assertAlmostEqual(o["isci_kart"], 4.0)       # (2+4+6)/3 işçi çağrısı
        self.assertEqual(satir(s, "sonnet")["n"], 2)

    def test_kabul_basina_usd_isci_arti_denetci(self):
        s = A._planlayici(KARTLAR, KAYITLAR, 1)
        o = satir(s, "opus")
        self.assertAlmostEqual(o["kabul_usd"], (1 + .5 + 2 + .5 + 3 + 1) / 3, places=4)
        son = satir(s, "sonnet")                           # G-5 reddedildi: maliyeti kabul edilen G-4'e yüklenir
        self.assertEqual(son["onaylanan"], 1)
        self.assertAlmostEqual(son["kabul_usd"], 0.2 + 0.1 + 0.4 + 0.1, places=4)
        self.assertAlmostEqual(o["isci_usd_kart"], 2.0, places=4)

    def test_dakika_medyan_ve_p90_olusturmadan_tesline(self):
        o = satir(A._planlayici(KARTLAR, KAYITLAR, 1), "opus")
        self.assertEqual(o["dk_medyan"], 50.0)
        self.assertEqual(o["dk_p90"], 90.0)               # 30,50,100 -> p90 = 50 + 0.8*(100-50)... doğrusal ara değer
        self.assertEqual(o["teslim"], 3)

    def test_alt_sinir_beta_yuzde_20(self):
        self.assertAlmostEqual(A.beta_alt_sinir(0, 0), None)
        # 10/10 başarı: Beta(11,1) CDF = x**11 -> %20 kuantili 0.2 ** (1/11)
        self.assertAlmostEqual(A.beta_alt_sinir(10, 10), 0.2 ** (1 / 11), places=3)
        o = satir(A._planlayici(KARTLAR, KAYITLAR, 1), "opus")
        self.assertTrue(0 < o["alt_sinir"] < o["ilk_gecis"])

    def test_yetersiz_veri_etiketi_karar_uretmez(self):
        s = A._planlayici(KARTLAR, KAYITLAR, 3)
        yeterli = satir(s, "opus")
        yetersiz = satir(s, "sonnet")
        self.assertTrue(yeterli["yeterli"])
        self.assertTrue(yeterli["karar_satiri"])
        self.assertFalse(yetersiz["yeterli"])
        self.assertFalse(yetersiz["karar_satiri"])
        self.assertEqual(yetersiz["etiket"], "yetersiz veri")
        hucre = satir(s, "sonnet", "belge", "T1")
        self.assertFalse(hucre["yeterli"])

    def test_hucre_satirlari_sinif_ve_basamak(self):
        s = A._planlayici(KARTLAR, KAYITLAR, 1)
        self.assertEqual({(r["planlayici"], r["sinif"], r["baslangic_basamak"]) for r in s["satirlar"]},
                         {("opus", "kod", "T2"), ("sonnet", "belge", "T1")})

    def test_plan_modeli_yoksa_ana_ajan_yedegi(self):
        kartlar = [kart("G-1", plan=None, oturum="oA"), kart("G-2", plan="-", oturum="oA"), kart("G-3", plan=None, oturum="oYok")]
        kayit = [ana("oA", "claude-opus-4-7", 5.0), ana("oA", "claude-sonnet-5-5", 1.0)]
        s = A._planlayici(kartlar, kayit, 1)
        self.assertEqual(satir(s, "opus")["n"], 2)
        self.assertEqual(satir(s, "bilinmiyor")["n"], 1)

    def test_min_n_dosyasi_yoksa_varsayilan(self):
        self.assertGreaterEqual(A.planlayici_min_n(), 1)

    def test_md_tablosu_etiketli(self):
        md = A.planlayici_md(A._planlayici(KARTLAR, KAYITLAR, 3))
        self.assertIn("Planlayıcı modeli", md)
        self.assertIn("ölçüm", md)
        self.assertIn("yetersiz veri", md)
        self.assertIn("| **opus** | toplam |", md)

    def test_olustur_cikti_anahtari(self):
        with tempfile.TemporaryDirectory() as t:
            sd = os.path.join(t, ".claude", "orkestra")
            os.makedirs(os.path.join(sd, "gorevler"))
            with open(os.path.join(sd, "gorevler", "G-1.json"), "w", encoding="utf-8") as f:
                json.dump(KARTLAR[0], f)
            sonuc = A.olustur(sd, t)
            self.assertIn("planlayici", sonuc)
            self.assertEqual(sonuc["planlayici"]["toplam"][0]["planlayici"], "opus")


class KpiSatiri(unittest.TestCase):
    def test_kpi_olcum_ve_tablo_planlayici_satiri(self):
        with tempfile.TemporaryDirectory() as t:
            sd = os.path.join(t, ".claude", "orkestra")
            os.makedirs(os.path.join(sd, "gorevler"))
            os.makedirs(os.path.join(sd, "onaylar"))
            for k in KARTLAR:
                with open(os.path.join(sd, "gorevler", k["id"] + ".json"), "w", encoding="utf-8") as f:
                    json.dump(k, f)
            with open(os.path.join(sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
                for r in KAYITLAR:
                    f.write(json.dumps(r) + "\n")
            s = kpi.olcum(sd)
            pl = {r["planlayici"]: r for r in s["planlayici"]}
            self.assertAlmostEqual(pl["opus"]["kabul_usd"], 8.0 / 3, places=3)
            self.assertIn("planlayici opus", kpi.tablo(s))
            self.assertIn("kabul_usd", kpi.tablo(s))


class PanelJs(unittest.TestCase):
    def test_verim_js_planlayici_bolumu(self):
        js = open(os.path.join(AD, "..", "assets", "verim.js"), encoding="utf-8").read()
        self.assertIn("planlayiciIcerik", js)
        self.assertIn("function planlayiciCiz", js)
        self.assertIn("v.planlayici", js)


if __name__ == "__main__":
    unittest.main()
