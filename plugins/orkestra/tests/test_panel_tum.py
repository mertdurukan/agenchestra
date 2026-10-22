"""panel_tum.py: 'Tüm çalışma alanları' birleştirme kuralları (ADR-0030). Saf işlevler; sunucu ve dosya yok.
`py -3.13 -m pytest plugins/orkestra/tests/test_panel_tum.py`"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import panel_tum as PT  # noqa: E402

A = {"id": "alan-a", "ad": "Alan A", "yol": "/a"}
B = {"id": "alan-b", "ad": "Alan B", "yol": "/b"}


class Ayir(unittest.TestCase):
    def test_hata_ve_kapali_alan_atlanir_digeri_gelir(self):
        ok, atlanan = PT.ayir([(A, {"acik": True}), (B, RuntimeError("bozuk"))])
        self.assertEqual([a["id"] for a, _ in ok], ["alan-a"])
        self.assertEqual(atlanan[0]["alan"]["id"], "alan-b")
        self.assertIn("RuntimeError", atlanan[0]["hata"])
        ok, atlanan = PT.ayir([(A, {"acik": False, "hata": "kapalı"})])
        self.assertEqual((ok, atlanan[0]["hata"]), ([], "kapalı"))

    def test_hic_alan_yoksa_acik_false(self):
        v = PT.onaylar([], [])
        self.assertFalse(v["acik"])
        self.assertEqual(v["alan"]["id"], "*")


class Kayitlar(unittest.TestCase):
    def test_kayit_alan_etiketi_tasir_ve_bekleyen_once_gelir(self):
        ok = [(A, {"kayitlar": [{"id": "O-1", "durum": "onaylandi"}], "sayac": {"bekliyor": 1}, "arka_plan": []}),
              (B, {"kayitlar": [{"id": "O-1", "durum": "bekliyor"}], "sayac": {"bekliyor": 2}, "arka_plan": []})]
        v = PT.onaylar(ok, [])
        self.assertEqual([(k["durum"], k["alan"]["id"]) for k in v["kayitlar"]], [("bekliyor", "alan-b"), ("onaylandi", "alan-a")])
        self.assertEqual(v["sayac"]["bekliyor"], 3)
        self.assertEqual(v["perspektif"], {"rapor": None, "durum": None})

    def test_ayni_kimlikli_kayitlar_birbirini_ezmez(self):
        ok = [(A, {"isler": [{"id": "I-001", "son": "2026-10-01", "durum": "acik"}], "kartsiz": {"sayi": 1, "acik": [{"kart": "G-1"}]}}),
              (B, {"isler": [{"id": "I-001", "son": "2026-10-02", "durum": "acik"}], "kartsiz": {"sayi": 2, "acik": []}})]
        v = PT.isler(ok, [])
        self.assertEqual([(i["id"], i["alan"]["id"]) for i in v["isler"]], [("I-001", "alan-b"), ("I-001", "alan-a")])
        self.assertEqual(v["kartsiz"]["sayi"], 3)
        self.assertEqual(v["kartsiz"]["acik"][0]["alan"]["id"], "alan-a")

    def test_kapanan_is_acik_olanin_arkasina_gecer(self):
        ok = [(A, {"isler": [{"id": "I-1", "son": "9", "durum": "kapandi"}, {"id": "I-2", "son": "1", "durum": "acik"}]})]
        self.assertEqual([i["id"] for i in PT.isler(ok, [])["isler"]], ["I-2", "I-1"])

    def test_eklenti_kurali_tek_kez_ortak_proje_kurali_alanli(self):
        plugin = {"katman": "plugin", "id": "K-003", "metin": "m", "durum": "etkin"}
        ok = [(A, {"etkin": [dict(plugin), {"katman": "proje", "id": "K-001", "metin": "x"}], "oneriler": [], "gecmis": [], "kaynaklar": []}),
              (B, {"etkin": [dict(plugin)], "oneriler": [], "gecmis": [], "kaynaklar": []})]
        etkin = PT.kurallar(ok, [])["etkin"]
        self.assertEqual(len(etkin), 2)
        ortak = next(k for k in etkin if k["id"] == "K-003")
        self.assertTrue(ortak["ortak"])
        self.assertNotIn("alan", ortak)
        self.assertEqual(next(k for k in etkin if k["id"] == "K-001")["alan"]["id"], "alan-a")


class Maliyet(unittest.TestCase):
    def _m(self, usd, token, ajan, oturum):
        return {"toplam": usd, "bugun": usd, "kalem": {"usd": {"toplam": usd}},
                "ajan_surec": [{"ajan": ajan, "surec": "s", "kosu": 1, "usd": usd, "token": token, "cikis": 0, "giris": 0}],
                "oturumlar": [{"oturum": oturum}], "model": {"sonnet": usd},
                "pencere": {"bugun": {"usd": usd, "token": token, "gun": 1, "model": {"sonnet": usd},
                                      "ajan_surec": [{"ajan": ajan, "surec": "s", "kosu": 1, "usd": usd, "token": token}]}}}

    def test_tutarlar_toplanir_ajan_surec_tekrarlanmaz(self):
        ok = [(A, {"maliyet": self._m(10.0, 100, "x", "o1")}), (B, {"maliyet": self._m(2.5, 50, "x", "o2")})]
        m = PT.ozet(ok, [])["maliyet"]
        self.assertEqual(m["toplam"], 12.5)
        self.assertEqual(m["kalem"]["usd"]["toplam"], 12.5)
        self.assertEqual(m["model"], {"sonnet": 12.5})
        self.assertEqual(len(m["ajan_surec"]), 1)
        self.assertEqual((m["ajan_surec"][0]["usd"], m["ajan_surec"][0]["kosu"]), (12.5, 2))
        self.assertEqual(len(m["pencere"]["bugun"]["ajan_surec"]), 1)
        self.assertEqual(m["pencere"]["bugun"]["usd"], 12.5)
        self.assertEqual(m["pencere"]["bugun"]["gun"], 1)   # gün sayacı toplanmaz, en büyüğü alınır
        self.assertEqual([o["alan"]["id"] for o in m["oturumlar"]], ["alan-a", "alan-b"])

    def test_tek_alan_eksik_bolumle_cokmez(self):
        v = PT.ozet([(A, {"maliyet": self._m(1.0, 1, "x", "o")}), (B, {})], [])
        self.assertEqual(v["maliyet"]["toplam"], 1.0)


class Analitik(unittest.TestCase):
    def _a(self, usd, yeterli, tahmin, kart):
        return {"trend": {"gunluk": [{"donem": "2026-10-22", "usd": usd, "token": 1}], "saatlik": [], "haftalik": [], "aylik": [],
                          "ay_sonu": {"ay": "2026-10", "simdiye": usd, "gecen_gun": 22, "ay_gun": 31, "veri_gun": 3 if yeterli else 1,
                                      "tahmin_ort": tahmin, "tahmin_yeterli": yeterli},
                          "ilk_kayit": "2026-10-20" if yeterli else "2026-10-22"},
                "pencere": {w: {"kart_sayisi": kart, "birim": {"kart_basi": 1.5, "teslim_kart": kart},
                                "en_pahali": [["G-1", usd]], "en_pahali_token": [], "basamak": [{"ad": "T1"}], "akis_ozet": {}}
                            for w in PT.L.PENCERELER},
                "akis": {"kartlar": [], "ozet": {}, "kosular": [{"x": 1}], "gunler": ["2026-10-22"]},
                "onbellek": {"olay_sayisi": 1, "usd": 1.0, "gun": 7, "model_olaylari": [], "bosluk_olaylari": []},
                "hedef_panosu": {"olculer": [1]}}

    def test_trend_donemde_toplanir_oranlar_toplanmaz(self):
        ok = [(A, self._a(10.0, True, 100.0, 3)), (B, self._a(2.0, False, None, 1))]
        v = PT.analitik_birlesik(ok, [])
        self.assertEqual(v["trend"]["gunluk"], [{"donem": "2026-10-22", "usd": 12.0, "token": 2}])
        w = v["pencere"]["tum_zaman"]
        self.assertEqual(w["kart_sayisi"], 4)
        self.assertEqual(w["birim"]["teslim_kart"], 4)
        self.assertIsNone(w["birim"]["kart_basi"])
        self.assertEqual(w["basamak"], [])
        self.assertEqual(w["en_pahali"], [["G-1", 10.0, "alan-a"], ["G-1", 2.0, "alan-b"]])
        self.assertIsNone(v["hedef_panosu"])
        self.assertIn("hedef_panosu", v["birlesmeyen"])
        self.assertEqual(v["akis"]["kosular"], [])

    def test_ay_sonu_tahmini_eksik_alani_adiyla_bildirir(self):
        ok = [(A, self._a(10.0, True, 100.0, 3)), (B, self._a(2.0, False, None, 1))]
        ay = PT.analitik_birlesik(ok, [])["trend"]["ay_sonu"]
        self.assertEqual(ay["simdiye"], 12.0)
        self.assertEqual(ay["tahmin_ort"], 100.0)
        self.assertEqual(ay["tahmin_eksik_alanlar"], ["Alan B"])
        self.assertEqual(ay["gecen_gun"], 22)   # gün sayacı toplanmaz


if __name__ == "__main__":
    unittest.main()
