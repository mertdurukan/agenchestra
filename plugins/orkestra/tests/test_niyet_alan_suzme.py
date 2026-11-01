"""Sohbet görünümü çalışma alanına göre süzülür.

Kabul kriterleri:
  K1  Alan klasörü ve altındaki projeler o alana aittir; kardeş klasör ait değildir.
  K2  İç içe daha özgül alan (worktree) varsa sohbet ona aittir, üst alana değil.
  K3  Boş yol hiçbir alana ait sayılmaz.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import niyet  # noqa: E402


class AlanSuzme(unittest.TestCase):
    def test_k1_alan_ve_alt_klasor(self):
        self.assertTrue(niyet.alan_sohbeti_mi("C:/Work/DemoRoot", "C:/Work/DemoRoot"))
        self.assertTrue(niyet.alan_sohbeti_mi("C:/Work/DemoRoot/ACMECO", "C:/Work/DemoRoot"))
        self.assertFalse(niyet.alan_sohbeti_mi("C:/Work/DemoRoot2", "C:/Work/DemoRoot"))
        self.assertFalse(niyet.alan_sohbeti_mi("C:/Work", "C:/Work/DemoRoot"))

    def test_k2_ic_ice_alan(self):
        tum = ["C:/Work/DemoRoot", "C:/Work/DemoRoot/.claude/worktrees/x"]
        p = "C:/Work/DemoRoot/.claude/worktrees/x"
        self.assertTrue(niyet.alan_sohbeti_mi(p, tum[1], tum))
        self.assertFalse(niyet.alan_sohbeti_mi(p, tum[0], tum))

    def test_k3_bos_yol(self):
        self.assertFalse(niyet.alan_sohbeti_mi("", "C:/Work/DemoRoot"))
        self.assertFalse(niyet.alan_sohbeti_mi(None, "C:/Work/DemoRoot"))


if __name__ == "__main__":
    unittest.main()
