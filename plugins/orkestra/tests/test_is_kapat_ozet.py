"""Görev bitiş raporu kapısı (P-009): `orkestra is kapat` doldurulmuş calisma_ozeti_*.md olmadan reddeder."""
import datetime
import os
import unittest

import test_cekirdek as TC

GUN = datetime.datetime.now().strftime("%Y%m%d")
OZET_DOLU = "# Deneme işi: çalışma özeti\n\n**Amaç:**\n\nDeneme.\n\n**Ana bulgu:**\n\nİş tamamlandı.\n\n**Kapsam kararı:**\n\nYok.\n"
OZET_BOS = "# Deneme işi: çalışma özeti\n\n**Amaç:**\n\nDeneme.\n\n**Ana bulgu:**\n\n**Kapsam kararı:**\n\nYok.\n"


class IsKapatOzet(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def cli(self, *args, kapi="1"):
        return TC.kos([TC.CLI, *args], self.proje, ortam={"ORKESTRA_OZET_KAPISI": kapi})

    def ac(self):
        klasor = os.path.join(self.proje, "is1")
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), klasor

    @staticmethod
    def yaz(klasor, metin):
        with open(os.path.join(klasor, f"calisma_ozeti_{GUN}.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def test_ozet_yoksa_reddeder_ve_is_acik_kalir(self):
        i, _ = self.ac()
        r = self.cli("is", "kapat", i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("görev bitiş raporu yok", r.stderr + r.stdout)
        self.assertIn("is belge", r.stderr + r.stdout)
        self.assertNotIn("kapandi", self.cli("is", "liste", "--durum", "kapandi").stdout)

    def test_bos_sablon_reddedilir(self):
        i, klasor = self.ac()
        self.yaz(klasor, OZET_BOS)
        r = self.cli("is", "kapat", i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Ana bulgu", r.stderr + r.stdout)

    def test_dolu_ozetle_kapanir_ve_ozet_satiri_basilir(self):
        i, klasor = self.ac()
        self.yaz(klasor, OZET_DOLU)
        r = self.cli("is", "kapat", i)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kapandi", r.stdout)
        self.assertIn(f"calisma_ozeti_{GUN}.md", r.stdout)

    def test_ozetsiz_bayragi_nedenle_kapatir(self):
        i, _ = self.ac()
        r = self.cli("is", "kapat", i, "--ozetsiz", "iş hiç yapılmadı")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("özetsiz kapatıldı: iş hiç yapılmadı", r.stdout)

    def test_kapi_kapaliyken_ozetsiz_kapanir(self):
        i, _ = self.ac()
        self.assertEqual(self.cli("is", "kapat", i, kapi="0").returncode, 0)


if __name__ == "__main__":
    unittest.main()
