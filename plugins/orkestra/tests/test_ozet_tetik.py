"""Çalışma özeti erken tetik (P-009): son todo maddesi bitince özet iskeleti açılır ve doldurma istenir."""
import datetime
import glob
import os
import unittest

import test_cekirdek as TC

GUN = datetime.datetime.now().strftime("%Y%m%d")


class OzetTetik(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def cli(self, *args, kapi="1"):
        return TC.kos([TC.CLI, *args], self.proje, ortam={"ORKESTRA_OZET_KAPISI": kapi})

    def ac(self, maddeler):
        klasor = os.path.join(self.proje, "is1")
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        i = r.stdout.strip()
        if maddeler:
            args = ["is", "todo", i]
            for m in maddeler:
                args += ["--ekle", m]
            self.assertEqual(self.cli(*args, kapi="0").returncode, 0)
        return i, klasor

    @staticmethod
    def ozetler(klasor):
        return glob.glob(os.path.join(klasor, "calisma_ozeti_*.md"))

    def test_son_madde_bitince_iskelet_ve_uyari(self):
        i, klasor = self.ac(["a", "b"])
        r = self.cli("is", "todo", i, "--bitti", "1")
        self.assertEqual(self.ozetler(klasor), [])
        self.assertNotIn("çalışma özetini doldur", r.stdout)
        r = self.cli("is", "todo", i, "--bitti", "1")
        self.assertEqual(len(self.ozetler(klasor)), 1)
        self.assertIn("çalışma özetini doldur", r.stdout)

    def test_kapi_kapaliyken_sessiz(self):
        i, klasor = self.ac(["a"])
        r = self.cli("is", "todo", i, "--bitti", "1", kapi="0")
        self.assertEqual(self.ozetler(klasor), [])
        self.assertNotIn("çalışma özetini doldur", r.stdout)

    def test_todosuz_is_tetiklemez(self):
        i, klasor = self.ac([])
        self.cli("is", "todo", i)
        self.assertEqual(self.ozetler(klasor), [])

    def test_dolu_ozet_ezilmez_ve_uyari_vermez(self):
        i, klasor = self.ac(["a", "b"])
        yol = os.path.join(klasor, f"calisma_ozeti_{GUN}.md")
        dolu = "# Deneme işi: çalışma özeti\n\n**Ana bulgu:**\n\nBitti.\n"
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(dolu)
        r = self.cli("is", "todo", i, "--bitti", "a", "--bitti", "b")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("çalışma özetini doldur", r.stdout)
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(f.read(), dolu)


if __name__ == "__main__":
    unittest.main()
