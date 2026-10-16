"""Tarama 18 (16.10): ret oranı, ana ajan payı, iş başına USD ve önbellek yazma eki tek tanımdan gelir."""
import datetime
import os
import sys
import unittest

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import analitik as A  # noqa: E402
import maliyet_anomali as MA  # noqa: E402
import ork_lib as L  # noqa: E402


def _kart(id_, durum, kararlar, is_=None):
    return {"id": id_, "durum": durum, "baslangic_basamak": "T2", "basamak": "T2", "is": is_, "gecmis": [],
            "denetimler": [{"karar": k, "sira": n, "basamak": "T2", "neden": None} for n, k in enumerate(kararlar)]}


class RetOrani(unittest.TestCase):
    def test_iptal_kart_sayilmaz(self):
        kartlar = [_kart("G-001", "teslim", ["ret", "onay"]), _kart("G-002", "iptal", ["ret", "ret", "onay"])]
        self.assertEqual(L.ret_onay_say(kartlar), (1, 2))

    def test_basamak_tablosu_ayni_tanim(self):
        kartlar = [_kart("G-001", "teslim", ["ret", "onay"]), _kart("G-002", "iptal", ["ret", "ret", "onay"])]
        satir = A._basamak(kartlar, [])["satirlar"]
        self.assertEqual(sum(s["ret"] for s in satir), 1)
        self.assertEqual(sum(s["denetim"] for s in satir), 2)

    def test_ders_iptal_retleri_saymaz(self):
        kartlar = [_kart("G-001", "teslim", ["ret", "onay"]), _kart("G-002", "iptal", ["ret", "ret"])]
        self.assertEqual(A._ders(kartlar, [])["toplam"]["ret"], 1)


class AnaAjanPayi(unittest.TestCase):
    def test_gorev_bos_ya_da_tire_ana_sayilir(self):
        self.assertTrue(L.ana_ajan_satiri_mi({"gorev": None}))
        self.assertTrue(L.ana_ajan_satiri_mi({"gorev": "-"}))
        self.assertTrue(L.ana_ajan_satiri_mi({}))
        self.assertFalse(L.ana_ajan_satiri_mi({"gorev": "G-001"}))

    def test_k6_payda_butun_defter_hook_artik_dusmez(self):
        z = datetime.datetime(2026, 10, 16, 8, 0).astimezone()

        def satir(usd, gorev, kaynak, agent_id=None):
            return {"ajan": "ana-ajan" if not agent_id else "isci-t1", "agent_id": agent_id, "gorev": gorev,
                    "kaynak": kaynak, "maliyet_usd": usd, "_z": z, "oturum": "s1", "surec": "is"}

        satirlar = [satir(6.0, "-", "tur"), satir(2.0, "-", "hook-artik"), satir(2.0, "G-001", "tur", "a1")]
        out = [o for o in MA.denetle(satirlar, {"G-001": {"id": "G-001"}}) if o["kural"] == "K6"]
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["usd"], 8.0)            # tur + hook-artik, ikisi de ana
        self.assertIn("%80 (8.00$ / 10.00$)", out[0]["ayrinti"])


class IsBasinaUsd(unittest.TestCase):
    def test_satir_karta_bagliysa_kartin_isine_yazilir(self):
        kart_is = {"G-001": "I-005"}
        self.assertEqual(L.satir_isi({"gorev": "G-001", "is": "I-002"}, kart_is), "I-005")
        self.assertEqual(L.satir_isi({"gorev": "G-001", "is": ""}, kart_is), "I-005")
        self.assertEqual(L.satir_isi({"gorev": "-", "is": "I-002"}, kart_is), "I-002")
        self.assertEqual(L.satir_isi({"gorev": "G-009"}, kart_is), "")


class AkisBekleme(unittest.TestCase):
    def test_ard_arda_is_bitti_ayni_beklemeyi_bir_kez_sayar(self):
        def e(dk, olay):
            return {"zaman": f"2026-10-16T08:{dk:02d}:00+03:00", "olay": olay}

        k = {"id": "G-001", "basamak": "T2", "durum": "teslim", "olusturma": "2026-10-16T08:00:00+03:00",
             "gecmis": [e(1, "isleniyor"), e(5, "is-bitti"), e(6, "is-bitti"), e(7, "is-bitti"), e(17, "denetim:onay"),
                        e(18, "teslim")]}
        a = A._akis([k], [])["kartlar"][0]
        self.assertEqual(a["denetim_toplam_dk"], 10.0)   # son is-bitti (08:07) → denetim (08:17)
        self.assertEqual(a["is_dk"], 4.0)                # isleniyor 08:01 → ilk is-bitti 08:05; ara is-bitti terim üretmez


class OnkontrolRetOrani(unittest.TestCase):
    def test_kartin_onkontrol_kosularindan_hesaplanir(self):
        import json
        import tempfile
        import kpi as K
        sd = tempfile.mkdtemp()
        os.makedirs(os.path.join(sd, "gorevler"))
        k = {"id": "G-001", "durum": "teslim", "olusturma": "2026-10-16T08:00:00+03:00", "gecmis": [], "denetimler": [],
             "isciler": [], "onkontrol_kosulari": [{"gecti": True}, {"gecti": False}, {"gecti": True}, {"gecti": True}]}
        with open(os.path.join(sd, "gorevler", "G-001.json"), "w", encoding="utf-8") as f:
            json.dump(k, f)
        self.assertEqual(K.olcum(sd)["genel"]["onkontrol_ret_orani"], 0.25)


class K4Tolerans(unittest.TestCase):
    def test_bir_saniyelik_yuvarlama_cakisma_sayilmaz(self):
        t0 = datetime.datetime(2026, 10, 16, 8, 0).astimezone()

        def isci(bitis_sn, sure_sn, agent_id):
            return {"ajan": "isci-t1", "agent_id": agent_id, "gorev": "G-001", "kaynak": "tur", "maliyet_usd": 1.0,
                    "_z": t0 + datetime.timedelta(seconds=bitis_sn), "sure_ms": sure_sn * 1000, "oturum": "s1", "surec": "is"}

        kartlar = {"G-001": {"id": "G-001"}}
        k4 = lambda sat: [o for o in MA.denetle(sat, kartlar) if o["kural"] == "K4"]   # noqa: E731
        self.assertEqual(k4([isci(100, 100, "a1"), isci(199, 100, "a2")]), [])      # 1 sn çakışma: yuvarlama
        self.assertEqual(len(k4([isci(100, 100, "a1"), isci(160, 100, "a2")])), 1)  # 40 sn çakışma: gerçek


class OnbellekYazmaEki(unittest.TestCase):
    def test_1_saat_tarifesi(self):
        f = L.model_fiyati("claude-opus-5-5")
        r = {"model": "claude-opus-5-5", "onbellek_yazma": 1_000_000, "maliyet_usd": 1.0}
        ek = A._tasarruf([r])["onbellek"]["yazma_eki"]
        self.assertAlmostEqual(ek, round(f["onbellek_yazma_1sa"] - f["giris"], 2), places=2)


if __name__ == "__main__":
    unittest.main()
