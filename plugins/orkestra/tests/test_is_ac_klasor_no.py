"""I-138 P5: `is ac --klasor` NNN- önekini kilit altında denetler; dolu/eksik numarada sıradaki numara alınır."""
import os
import re
import unittest

import test_cekirdek as TC


class IsAcKlasorNo(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def ac(self, ad):
        r = self.cli("is", "ac", "deneme", "--klasor", os.path.join(self.proje, ad))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def klasorler(self):
        return sorted(a for a in os.listdir(self.proje) if re.match(r"\d{3}-", a))

    def test_ayni_numarayla_iki_ac_farkli_numara(self):
        r1 = self.ac("077-x")
        r2 = self.ac("077-x")
        self.assertNotEqual(r1.stdout.strip(), r2.stdout.strip())
        nolar = [a[:3] for a in self.klasorler()]
        self.assertEqual(len(nolar), 2, self.klasorler())
        self.assertEqual(len(set(nolar)), 2)
        self.assertIn("yeni klasör", r2.stderr)
        for a in self.klasorler():
            self.assertTrue(os.path.exists(os.path.join(self.proje, a, "is.json")), a)

    def test_numara_baska_adla_doluysa_siradaki(self):
        self.ac("077-x")
        self.ac("077-y")
        self.assertEqual(self.klasorler()[0][:3], "077")
        self.assertEqual(self.klasorler()[1][:3], "078")

    def test_onek_yok_kok_numaraliysa_numara_alir(self):
        self.ac("077-x")
        r = self.ac("serbest-ad")
        self.assertIn("yeni klasör", r.stderr)
        self.assertEqual(len(self.klasorler()), 2)
        self.assertFalse(os.path.exists(os.path.join(self.proje, "serbest-ad")))

    def test_bos_numarali_ve_numarasiz_kok_aynen_kalir(self):
        self.ac("is1")
        self.assertTrue(os.path.exists(os.path.join(self.proje, "is1", "is.json")))
        self.ac("050-a")
        self.assertTrue(os.path.exists(os.path.join(self.proje, "050-a", "is.json")))

    def test_goreli_klasor_alt_klasorden_cagrida_proje_kokune_gore_cozulur(self):
        alt = os.path.join(self.proje, "altklasor")
        os.makedirs(alt)
        r = TC.kos([TC.CLI, "is", "ac", "deneme", "--klasor", "090-x"], alt)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.proje, "090-x", "is.json")))
        self.assertFalse(os.path.exists(os.path.join(alt, "090-x")))

    def test_onceden_acilmis_bos_klasor_yeniden_kullanilir(self):
        os.makedirs(os.path.join(self.proje, "060-hook"))
        r = self.ac("060-hook")
        self.assertNotIn("yeni klasör", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.proje, "060-hook", "is.json")))


if __name__ == "__main__":
    unittest.main()
