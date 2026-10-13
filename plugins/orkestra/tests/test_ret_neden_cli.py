"""`kart denetim --karar ret` için zorunlu --neden kodu testleri."""
import json
import os
import unittest

import test_cekirdek as TC
from test_cekirdek import CLI, kos

import sys
sys.path.insert(0, os.path.join(os.path.dirname(CLI)))
import ret_nedeni as RN  # noqa: E402


class RetNedenCli(unittest.TestCase):
    # Cekirdek'in yardımcılarını miras almadan ödünç al (testleri tekrar koşmasın)
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def hazir(self):
        g = self.kart()
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md", ajan_id="w1", ajan_tipi="orkestra:isci-t1")
        self.assertEqual(r.returncode, 0, r.stderr)
        return g

    def den(self, g, *ek):
        return self.cli("kart", "denetim", g, "--gerekce", "x", *ek, ajan_id="d1", ajan_tipi="orkestra:denetci")

    def kart_json(self, g):
        with open(os.path.join(self.sd, "gorevler", f"{g}.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_kodsuz_ret_reddedilir(self):
        g = self.hazir()
        once = self.kart_json(g)
        r = self.den(g, "--karar", "ret")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--neden", r.stderr)
        for kod in RN.NEDENLER:
            self.assertIn(kod, r.stderr)
        self.assertEqual(self.kart_json(g), once)

    def test_gecersiz_kod_reddedilir(self):
        g = self.hazir()
        once = self.kart_json(g)
        r = self.den(g, "--karar", "ret", "--neden", "uydurma")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("geçersiz", r.stderr)
        self.assertIn("kapsam-eksik", r.stderr)
        self.assertEqual(self.kart_json(g), once)

    def test_gecerli_kodla_ret_neden_ve_kok_yazar(self):
        g = self.hazir()
        r = self.den(g, "--karar", "ret", "--neden", "yetenek-yetersiz")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.kart_json(g)
        d = k["denetimler"][-1]
        self.assertEqual(d["neden"], "yetenek-yetersiz")
        self.assertEqual(d["kok"], RN.kok("yetenek-yetersiz"))
        self.assertEqual(d["kok"], "basamak")
        self.assertEqual(k["gecmis"][-1]["neden"], "yetenek-yetersiz")
        with open(os.path.join(self.sd, "gorevler", f"{g}.denetim.json"), encoding="utf-8") as f:
            y = json.load(f)
        self.assertEqual(y[-1]["neden"], "yetenek-yetersiz")
        self.assertEqual(y[-1]["kok"], "basamak")

    def test_onay_kodsuz_gecer_ve_kod_yok_sayilir(self):
        g = self.hazir()
        r = self.den(g, "--karar", "onay", "--neden", "bicim")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.kart_json(g)["denetimler"][-1]
        self.assertNotIn("neden", d)
        self.assertNotIn("kok", d)

    def test_onay_kodsuz(self):
        g = self.hazir()
        self.assertEqual(self.den(g, "--karar", "onay").returncode, 0)

    def test_help_kodlari_listeler(self):
        r = kos([CLI, "kart", "denetim", "--help"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        for kod, ac in RN.NEDENLER.items():
            self.assertIn(kod, r.stdout)
            self.assertIn(ac, r.stdout)


if __name__ == "__main__":
    unittest.main()
