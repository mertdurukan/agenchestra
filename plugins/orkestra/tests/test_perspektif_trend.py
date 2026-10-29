"""Perspektif trend (P3): sentetik kart/maliyet/zaman/gunluk verisiyle iki pencere karsilastirmasi.
python -m pytest tests/test_perspektif_trend.py
"""
import datetime
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import kpi as K  # noqa: E402
import perspektif_trend as T  # noqa: E402

TZ = datetime.timezone.utc
SIMDI = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=TZ)


def iso(d):
    return d.isoformat()


class TrendOrtam(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_ptrend_")
        os.makedirs(os.path.join(self.sd, "gorevler"), exist_ok=True)
        self.gunluk = []
        self.n = 0

    def kart(self, gun_once, ret=0, onay=1):
        self.n += 1
        z = SIMDI - datetime.timedelta(days=gun_once)
        gid = f"G-{self.n}"
        den = [{"karar": "ret"}] * ret + [{"karar": "onay"}] * onay
        k = {"id": gid, "durum": "onaylandi", "olusturma": iso(z), "denetimler": den, "isciler": [{}]}
        with open(os.path.join(self.sd, "gorevler", gid + ".json"), "w", encoding="utf-8") as f:
            json.dump(k, f)

    def ret_kaydi(self, gun_once, adet):
        for i in range(adet):
            self.gunluk.append({"zaman": iso(SIMDI - datetime.timedelta(days=gun_once, minutes=i)),
                                "tur": "kapi_ret", "kapi": "k1", "is": f"I-{i}", "neden": "x"})

    def yaz(self):
        with open(os.path.join(self.sd, "gunluk.jsonl"), "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(o) + "\n" for o in self.gunluk))

    def hesapla(self, gun=7):
        self.yaz()
        return T.hesapla(self.sd, gun, simdi=SIMDI)


class Yaprak(unittest.TestCase):
    def test_sayisal_yaprak_cikarimi(self):
        y = T.yapraklar({"a": 1, "b": {"c": 2.5, "d": None, "e": "s", "f": [1, 2], "g": True}, "h": {"i": {"j": 3}}})
        self.assertEqual(y, {"a": 1, "b.c": 2.5, "b.d": None, "h.i.j": 3})

    def test_beklenti_tablosu(self):
        self.assertEqual(T.beklenti("onbellek_isabet"), "artmali")
        self.assertEqual(T.beklenti("kapanis_orani"), "artmali")
        self.assertEqual(T.beklenti("ret_orani"), "azalmali")
        self.assertEqual(T.beklenti("basari_basina_maliyet"), "azalmali")
        self.assertIsNone(T.beklenti("denetim_payi"))

    def test_kotu_sayac_kapanis_icerse_azalmali(self):
        self.assertEqual(T.beklenti("gunluk kural_ihlal.kapanis_atlandi"), "azalmali")
        self.assertEqual(T.beklenti("gunluk kapi_golge.paralellik_kapanis"), "azalmali")
        self.assertEqual(T.beklenti("kapanis_orani"), "artmali")
        self.assertEqual(T.beklenti("cikti_olcum.kapanis_orani"), "artmali")
        r = T.karsilastir({"kural_ihlal.kapanis_atlandi": 5, "ret": 1}, {"kural_ihlal.kapanis_atlandi": 2, "ret": 1})
        self.assertEqual(r["kural_ihlal.kapanis_atlandi"]["yon"], "kotu")


class Karsilastir(unittest.TestCase):
    def test_delta_ve_yon(self):
        r = T.karsilastir({"ret_orani": 0.1, "onbellek_isabet": 0.9, "p95_sure_sn": 50, "bilinmeyen": 5, "sabit_ret": 2},
                          {"ret_orani": 0.3, "onbellek_isabet": 0.95, "p95_sure_sn": 40, "bilinmeyen": 1, "sabit_ret": 2})
        self.assertEqual(r["ret_orani"]["yon"], "iyi")
        self.assertAlmostEqual(r["ret_orani"]["delta"], -0.2)
        self.assertEqual(r["onbellek_isabet"]["yon"], "kotu")
        self.assertEqual(r["p95_sure_sn"]["yon"], "kotu")
        self.assertEqual(r["bilinmeyen"]["yon"], "belirsiz")
        self.assertEqual(r["bilinmeyen"]["delta"], 4)
        self.assertEqual(r["sabit_ret"]["yon"], "ayni")

    def test_onceki_bos_belirsiz(self):
        r = T.karsilastir({"ret_orani": 0.1, "hata": 3}, {"ret_orani": 0.0, "hata": 0})
        self.assertTrue(all(v["yon"] == "belirsiz" for v in r.values()))
        self.assertEqual(r["hata"]["delta"], 3)


class Entegrasyon(TrendOrtam):
    def test_kpi_pencere_kaydirma(self):
        # bu pencere (7 gun): 2 kart, 1 ret; onceki pencere (7-14 gun once): 2 kart, 0 ret
        self.kart(1, ret=1, onay=1)
        self.kart(2, ret=0, onay=1)
        self.kart(9, ret=0, onay=2)
        self.kart(10, ret=0, onay=1)
        self.kart(30, ret=5, onay=0)  # her iki pencere disinda
        r = self.hesapla(7)
        ro = r["kpi"]["ret_orani"]
        self.assertAlmostEqual(ro["simdi"], 1 / 3, places=4)
        self.assertEqual(ro["onceki"], 0.0)
        self.assertEqual(ro["yon"], "kotu")  # onceki pencere dolu (kartlar var), ret 0 -> 1/3
        # kpi.olcum aralik ile dogrudan: onceki pencere yalniz 9. ve 10. gundeki kartlari gormeli
        bas = T.L.gun_baslangici(7, SIMDI)
        onc = K.olcum(self.sd, aralik=(T.L.gun_baslangici(14, SIMDI), bas))["genel"]
        self.assertEqual(onc["ret_orani"], 0.0)

    def test_gunluk_iki_pencere_yon(self):
        self.kart(1)
        self.kart(9)
        self.ret_kaydi(1, 2)
        self.ret_kaydi(9, 5)
        r = self.hesapla(7)
        e = r["gunluk"]["kapi_ret.k1"]
        self.assertEqual((e["simdi"], e["onceki"], e["delta"], e["yon"]), (2, 5, -3, "iyi"))

    def test_onceki_pencere_bos_belirsiz(self):
        self.kart(1)
        self.ret_kaydi(1, 3)
        r = self.hesapla(7)
        self.assertEqual(r["gunluk"]["kapi_ret.k1"]["onceki"], 0)
        self.assertEqual(r["gunluk"]["kapi_ret.k1"]["yon"], "belirsiz")
        self.assertEqual(r["kpi"]["ret_orani"]["yon"], "belirsiz")
        self.assertIsNone(r["kpi"]["ret_orani"]["delta"])
        self.assertEqual(set(r), {"pencere", "kpi", "anomali", "zaman", "gunluk"})


if __name__ == "__main__":
    unittest.main()
