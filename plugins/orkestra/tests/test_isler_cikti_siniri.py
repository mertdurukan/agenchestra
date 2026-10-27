"""`orkestra is todo` / `is devam` varsayılan çıktı sınırı ve `--tum` (ADR-0086, I-232 P4)."""
import os
import unittest

import test_cekirdek as TC

MADDE_SAYISI = 55
SINIR = 3000


def yaz(yol, metin):
    with open(yol, "w", encoding="utf-8", newline="") as f:
        f.write(metin)


class CiktiSiniri(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def ac(self, maddeler):
        klasor = os.path.join(self.proje, "is1")
        r = self.cli("is", "ac", "Sınır işi", "--klasor", klasor, "--etiket", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        yaz(os.path.join(klasor, "todo.md"), "# t\n" + "".join(f"- [ ] {m}\n" for m in maddeler))
        return r.stdout.strip()

    @staticmethod
    def uzun_maddeler(n=MADDE_SAYISI):
        return [f"P{k}: " + "açıklama " * 7 + f"son{k}" for k in range(1, n + 1)]

    def test_todo_varsayilan_sinirli_tum_eski_cikti(self):
        i = self.ac(self.uzun_maddeler())
        varsayilan = self.cli("is", "todo", i)
        tum = self.cli("is", "todo", i, "--tum")
        self.assertEqual(varsayilan.returncode, 0, varsayilan.stderr)
        self.assertEqual(tum.returncode, 0, tum.stderr)
        self.assertLessEqual(len(varsayilan.stdout), SINIR)
        self.assertIn("--tum", varsayilan.stdout)
        self.assertIn("açık madde daha", varsayilan.stdout)
        self.assertIn("son1\n", varsayilan.stdout)  # ilk madde hep görünür
        self.assertGreater(len(tum.stdout), SINIR)
        self.assertEqual(tum.stdout.count("  [ ] "), MADDE_SAYISI)
        self.assertNotIn("açık madde daha", tum.stdout)
        self.assertIn(f"son{MADDE_SAYISI}", tum.stdout)

    def test_todo_kalan_sayisi_dogru(self):
        i = self.ac(self.uzun_maddeler())
        cikti = self.cli("is", "todo", i).stdout
        gosterilen = cikti.count("  [ ] ")
        self.assertIn(f"… {MADDE_SAYISI - gosterilen} açık madde daha", cikti)

    def test_todo_kisa_liste_degismez(self):
        i = self.ac(["bir", "iki", "üç"])
        varsayilan = self.cli("is", "todo", i).stdout
        tum = self.cli("is", "todo", i, "--tum").stdout
        self.assertEqual(varsayilan, tum)
        self.assertNotIn("daha", varsayilan)

    def test_todo_yazma_sonrasi_sinirli(self):
        i = self.ac(self.uzun_maddeler())
        r = self.cli("is", "todo", i, "--ekle", "yeni madde")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLessEqual(len(r.stdout), SINIR)
        self.assertIn("1. [ ] ", r.stdout)  # numaralar --bitti <n> ile aynı sıra
        tum = self.cli("is", "todo", i, "--tum").stdout
        self.assertEqual(tum.count("  [ ] "), MADDE_SAYISI + 1)

    def test_devam_varsayilan_sinirli_tum_eski_cikti(self):
        i = self.ac(self.uzun_maddeler())
        varsayilan = self.cli("is", "devam", i)
        tum = self.cli("is", "devam", i, "--tum")
        self.assertEqual(varsayilan.returncode, 0, varsayilan.stderr)
        self.assertEqual(tum.returncode, 0, tum.stderr)
        self.assertLessEqual(len(varsayilan.stdout), SINIR)
        self.assertIn("--tum", varsayilan.stdout)
        self.assertEqual(tum.stdout.count("  [ ] "), MADDE_SAYISI)
        self.assertNotIn("açık madde daha", tum.stdout)

    def test_devam_kisa_liste_degismez(self):
        i = self.ac(["bir", "iki"])
        self.assertEqual(self.cli("is", "devam", i).stdout, self.cli("is", "devam", i, "--tum").stdout)


if __name__ == "__main__":
    unittest.main()
