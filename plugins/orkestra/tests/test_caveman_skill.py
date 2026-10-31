"""Caveman skill'leri (I-291, ADR-0095): sabit kopya, kaynak satırı, panelde görünür ve varsayılan açık.

Caveman'in MCP girdisi yoktur (kullanıcı kararı 31.10); `test_mcp_kayit_girdileri.test_caveman_kayitta_degil` bunu sınar.
"""
import os
import re
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import araclar_skill as AS  # noqa: E402

SKILLLER = ("caveman", "ultracave", "megacave", "caveman-commit", "caveman-review", "caveman-help")
DISLANAN = ("cavecrew", "caveman-compress", "caveman-setup", "caveman-manage")
SIR = re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}")


class CavemanSkill(unittest.TestCase):
    def yol(self, ad):
        return os.path.join(KOK, "skills", ad, "SKILL.md")

    def test_skill_dosyalari_var_ve_adi_klasorle_ayni(self):
        for ad in SKILLLER:
            with open(self.yol(ad), encoding="utf-8") as f:
                metin = f.read()
            self.assertRegex(metin, r"(?m)^name:\s*" + re.escape(ad) + r"\s*$", ad)

    def test_her_skill_source_satiri_tasir_ve_sabit_surume_baglidir(self):
        for ad in SKILLLER:
            with open(self.yol(ad), encoding="utf-8") as f:
                metin = f.read()
            self.assertRegex(metin, r"(?m)^source: https://github\.com/JuliusBrussee/caveman/blob/[0-9a-f]{40}/", ad)

    def test_sir_degeri_yok(self):
        for ad in SKILLLER:
            with open(self.yol(ad), encoding="utf-8") as f:
                self.assertIsNone(SIR.search(f.read()), ad)

    def test_kapsam_disi_parcalar_eklenmedi(self):
        for ad in DISLANAN:
            self.assertFalse(os.path.exists(os.path.join(KOK, "skills", ad)), ad)

    def test_panelde_gorunur_ve_varsayilan_acik(self):
        with tempfile.TemporaryDirectory() as proje, tempfile.TemporaryDirectory() as kul:
            satirlar = {s["ad"]: s for s in AS.liste(proje, kullanici_dizin=kul)}
        for ad in SKILLLER:
            s = satirlar.get(AS.EKLENTI_ADI + ":" + ad)
            self.assertIsNotNone(s, ad)
            self.assertEqual(s["durum"], "acik", ad)


if __name__ == "__main__":
    unittest.main()
