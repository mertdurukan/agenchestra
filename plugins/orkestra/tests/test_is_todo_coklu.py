"""`orkestra is todo` çoklu --bitti/--ekle/--not (G-144)."""
import datetime
import os
import unittest

import test_cekirdek as TC

bugun = datetime.date.today().isoformat()


def oku(yol):
    with open(yol, encoding="utf-8", newline="") as f:
        return f.read()


def yaz(yol, metin):
    with open(yol, "w", encoding="utf-8", newline="") as f:
        f.write(metin)


class TodoCoklu(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def ac(self, icerik="- [ ] a\n- [ ] b\n- [ ] c\n"):
        klasor = os.path.join(self.proje, "is1")
        r = self.cli("is", "ac", "Todo işi", "--klasor", klasor, "--etiket", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        todo = os.path.join(klasor, "todo.md")
        yaz(todo, icerik)
        return r.stdout.strip(), todo

    def test_k1_iki_bitti_tek_cagri_liste_bir_kez(self):
        i, todo = self.ac()
        r = self.cli("is", "todo", i, "--bitti", "1", "--bitti", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(todo), "- [x] a\n- [x] b\n- [ ] c\n")
        self.assertEqual(r.stdout.count("todo 2/3"), 1)
        self.assertEqual(r.stdout.count("[ ] c"), 1)
        self.assertEqual(len(r.stdout.strip().splitlines()), 2)

    def test_k1_alt_dize_ve_sayi_karisik_ozgun_listeye_gore(self):
        i, todo = self.ac()
        r = self.cli("is", "todo", i, "--bitti", "c", "--bitti", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(todo), "- [x] a\n- [ ] b\n- [x] c\n")

    def test_k2_iki_ekle_sirayla(self):
        i, todo = self.ac("- [ ] a\n")
        r = self.cli("is", "todo", i, "--ekle", "A", "--ekle", "B")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(todo), "- [ ] a\n- [ ] A\n- [ ] B\n")
        self.assertIn("todo 0/3", r.stdout)

    def test_k2_bitti_ve_ekle_birlikte_once_bitir_sonra_ekle(self):
        i, todo = self.ac("- [ ] a\n- [ ] b\n")
        r = self.cli("is", "todo", i, "--ekle", "yeni", "--bitti", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(todo), "- [x] a\n- [ ] b\n- [ ] yeni\n")
        self.assertEqual(r.stdout.splitlines()[1:], ["  1. [ ] b", "  2. [ ] yeni"])

    def test_k3_tek_not_tumune(self):
        i, todo = self.ac()
        r = self.cli("is", "todo", i, "--bitti", "1", "--bitti", "2", "--not", "N")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(todo), f"- [x] a — {bugun}: N\n- [x] b — {bugun}: N\n- [ ] c\n")

    def test_k3_sayi_kadar_not_sirayla(self):
        i, todo = self.ac()
        r = self.cli("is", "todo", i, "--bitti", "2", "--bitti", "1", "--not", "N2", "--not", "N1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(todo), f"- [x] a — {bugun}: N1\n- [x] b — {bugun}: N2\n- [ ] c\n")

    def test_k3_baska_sayida_not_cikis2_dosya_ayni(self):
        i, todo = self.ac()
        r = self.cli("is", "todo", i, "--bitti", "1", "--bitti", "2", "--bitti", "3", "--not", "x", "--not", "y")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(oku(todo), "- [ ] a\n- [ ] b\n- [ ] c\n")

    def test_k4_eslesmeyen_secici_hicbir_yazma_yok(self):
        i, todo = self.ac()
        r = self.cli("is", "todo", i, "--bitti", "1", "--bitti", "yok-boyle", "--ekle", "z")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(oku(todo), "- [ ] a\n- [ ] b\n- [ ] c\n")

    def test_k4_ayni_madde_iki_kez_hata_dosya_ayni(self):
        i, todo = self.ac()
        r = self.cli("is", "todo", i, "--bitti", "1", "--bitti", "a")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(oku(todo), "- [ ] a\n- [ ] b\n- [ ] c\n")

    def test_k5_tek_deger_eski_cikti(self):
        i, todo = self.ac("- [ ] a\n- [ ] b\n")
        r = self.cli("is", "todo", i, "--bitti", "1", "--not", "N")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [f"{i} todo 1/2", "  1. [ ] b"])
        self.assertEqual(oku(todo), f"- [x] a — {bugun}: N\n- [ ] b\n")
        r = self.cli("is", "todo", i, "--ekle", "X")
        self.assertEqual(r.stdout.splitlines(), [f"{i} todo 1/3", "  1. [ ] b", "  2. [ ] X"])

    def test_kapali_ise_ekle_hata(self):
        i, todo = self.ac("- [ ] a\n")
        self.assertEqual(self.cli("is", "kapat", i).returncode, 0)
        r = self.cli("is", "todo", i, "--ekle", "A", "--ekle", "B")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(oku(todo), "- [ ] a\n")


if __name__ == "__main__":
    unittest.main()
