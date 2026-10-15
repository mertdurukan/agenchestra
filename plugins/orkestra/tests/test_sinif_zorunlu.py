"""G-101: kart açılışında sinif zorunlu; eski sınıfsız kartlar okunmaya devam eder."""
import json
import os
import unittest

import test_cekirdek as TC


class SinifZorunlu(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def kos(self, *args):
        return TC.kos([TC.CLI] + list(args), self.proje)

    def plan(self, liste):
        yol = os.path.join(self.proje, "plan.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(liste, f)
        return yol

    def test_yeni_sinifsiz_reddedilir(self):
        r = self.kos("kart", "yeni", "--baslik", "X", "--kabul", "k")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sinif zorunlu", r.stderr)
        for s in ("kod", "belge", "arastirma"):
            self.assertIn(s, r.stderr)

    def test_toplu_sinifsiz_reddedilir_ve_kart_olusmaz(self):
        yol = self.plan([{"baslik": "A", "sinif": "belge", "kabul_kriterleri": ["k"]},
                         {"baslik": "B", "kabul_kriterleri": ["k"]}])
        r = self.kos("kart", "toplu", yol)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("geçerli sınıflar", r.stderr)
        self.assertFalse(os.listdir(os.path.join(self.sd, "gorevler")) if os.path.isdir(os.path.join(self.sd, "gorevler")) else False)

    def test_sinifli_acilis_calisir(self):
        r = self.kos("kart", "yeni", "--baslik", "X", "--sinif", "belge", "--kabul", "k")
        self.assertEqual(r.returncode, 0, r.stderr)
        yol = self.plan([{"baslik": "T", "sinif": "arastirma", "kabul_kriterleri": ["k"]}])
        r2 = self.kos("kart", "toplu", yol)
        self.assertEqual(r2.returncode, 0, r2.stderr)

    def test_eski_sinifsiz_kart_okunur(self):
        r = self.kos("kart", "yeni", "--baslik", "Eski", "--sinif", "belge", "--kabul", "k")
        self.assertEqual(r.returncode, 0, r.stderr)
        gid = r.stdout.strip()
        yol = os.path.join(self.sd, "gorevler", f"{gid}.json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        k.pop("sinif", None)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)
        self.assertEqual(self.kos("kart", "goster", gid).returncode, 0)
        l = self.kos("kart", "liste")
        self.assertEqual(l.returncode, 0, l.stderr)
        self.assertIn(gid, l.stdout)


if __name__ == "__main__":
    unittest.main()
