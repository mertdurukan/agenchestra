"""I-152: ana ajan payı tanımı. Kartsız alt ajan ana ajana yazılmaz; K6 kart harcaması olmayan günde mutlak eşikle çalışır."""
import datetime
import os
import sys
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import maliyet_anomali as MA  # noqa: E402
import ork_lib as L  # noqa: E402


def satir(ajan, usd, gorev="-", gun=10, is_=None, agent_id=None):
    z = datetime.datetime(2026, 3, gun, 12, 0).astimezone()
    d = {"zaman": z.isoformat(), "_z": z, "oturum": "o1", "gorev": gorev, "ajan": ajan, "agent_id": agent_id,
         "maliyet_usd": usd, "surec": "is", "model": "claude-sonnet-5-5"}
    if is_:
        d["is"] = is_
    return d


class AnaAjanTanimi(unittest.TestCase):
    def test_ana_ajan_ve_alt_ajan_ayrilir(self):
        self.assertTrue(L.ana_ajan_satiri_mi(satir("ana-ajan", 1)))
        self.assertTrue(L.ana_ajan_satiri_mi({"gorev": "-", "maliyet_usd": 1}))  # eski satır: ajan alanı yok
        self.assertFalse(L.ana_ajan_satiri_mi(satir("orkestra:arastirmaci", 1, agent_id="a1")))
        self.assertTrue(L.kartsiz_alt_ajan_satiri_mi(satir("general-purpose", 1, agent_id="a2")))
        self.assertTrue(L.kartsiz_alt_ajan_satiri_mi(satir("perspektif-bakimcisi", 1)))  # agent_id boş ama ajan ana değil

    def test_kartli_satir_ne_ana_ne_kartsiz_alt(self):
        r = satir("orkestra:isci-t2", 1, gorev="G-1", agent_id="a3")
        self.assertFalse(L.ana_ajan_satiri_mi(r))
        self.assertFalse(L.kartsiz_alt_ajan_satiri_mi(r))
        self.assertFalse(L.kartsiz_satir_mi(r))
        self.assertFalse(L.ana_ajan_satiri_mi(satir("ana-ajan", 1, gorev="G-1")))

    def test_dagilim_uc_kalem_ve_kart_satiri_haric(self):
        rs = [satir("ana-ajan", 3.0, is_="I-1"), satir("ana-ajan", 2.0), satir("general-purpose", 0.5, agent_id="a"),
              satir("orkestra:isci-t2", 9.0, gorev="G-1", agent_id="b")]
        d = L.ana_ajan_dagilimi(rs)
        self.assertEqual((d["ana_is_bagli"]["satir"], d["ana_is_bagli"]["usd"]), (1, 3.0))
        self.assertEqual((d["ana_is_bagsiz"]["satir"], d["ana_is_bagsiz"]["usd"]), (1, 2.0))
        self.assertEqual((d["kartsiz_alt_ajan"]["satir"], d["kartsiz_alt_ajan"]["usd"]), (1, 0.5))
        self.assertEqual(sum(v["usd"] for v in d.values()), 5.5)


class K6KartsizGun(unittest.TestCase):
    def k6(self, satirlar):
        return [a for a in MA.denetle(satirlar, {}) if a["kural"] == "K6"]

    def test_alt_ajan_ana_payina_girmez(self):
        # gün 10: kart 6$, ana 2$, kartsız alt ajan 8$ → ana payı 2/16 = %12 (alt ajan dahil olsaydı %62)
        rs = [satir("orkestra:isci-t2", 6.0, gorev="G-1", agent_id="x"), satir("ana-ajan", 2.0),
              satir("general-purpose", 8.0, agent_id="y")]
        self.assertEqual(self.k6(rs), [])

    def test_kartli_gunde_pay_kurali_calisir(self):
        rs = [satir("orkestra:isci-t2", 1.0, gorev="G-1", agent_id="x"), satir("ana-ajan", 9.0)]
        k = self.k6(rs)
        self.assertEqual([a["ad"] for a in k], ["ana-ajan-payi"])

    def test_kartsiz_gunde_pay_yerine_mutlak_esik(self):
        # gün 11 kart harcaması yok: ana 150$ ≥ 100$ → günlük satır; pay satırı yok
        k = self.k6([satir("ana-ajan", 150.0, gun=11)])
        self.assertEqual([a["ad"] for a in k], ["ana-ajan-gun-maliyeti"])
        self.assertIn("11.03", k[0]["ayrinti"])

    def test_kartsiz_gunde_esik_altinda_uyari_yok(self):
        self.assertEqual(self.k6([satir("ana-ajan", 40.0, gun=11)]), [])

    def test_karisik_pencere_gunler_ayri_degerlendirilir(self):
        rs = [satir("orkestra:isci-t2", 5.0, gorev="G-1", agent_id="x", gun=10), satir("ana-ajan", 1.0, gun=10),
              satir("ana-ajan", 120.0, gun=11)]
        ad = sorted(a["ad"] for a in self.k6(rs))
        self.assertEqual(ad, ["ana-ajan-gun-maliyeti"])  # gün 10 payı %17 < %50


if __name__ == "__main__":
    unittest.main()
