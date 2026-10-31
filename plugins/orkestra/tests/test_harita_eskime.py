"""Kenar düzeyinde eskime takibi (ADR-0112, I-296): kaynak değişince yalnız o kaynağın kenarı eskir; yenileme ikisini de günceller."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita as H  # noqa: E402
import harita_kenar as K  # noqa: E402


class Eskime(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        self.graf = os.path.join(self.kok, "graf")
        os.makedirs(self.graf)
        self.yaz("scripts/panel.py", "import araclar_skill\n")
        self.yaz("scripts/araclar_skill.py", 'AD = "SKILL.md"\n')
        self.yaz("skills/s1/SKILL.md", "# s1")
        self.yol = os.path.join(self.graf, "kenarlar.jsonl")
        K.yaz(K.statik_kenarlar(self.kok), self.yol)

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def yaz(self, rel, metin):
        yol = os.path.join(self.kok, rel)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)

    def test_degismeyen_kenarlar_guncel(self):
        d = H.kenar_denetle(self.kok, self.graf)
        self.assertEqual((len(d["guncel"]), len(d["eskimis"])), (2, 0))

    def test_kaynak_degisince_yalniz_ilgili_kenar_eskir_ve_yenilemede_guncellenir(self):
        self.yaz("scripts/panel.py", "import araclar_skill\n\nx = 1\n")
        d = H.kenar_denetle(self.kok, self.graf)
        self.assertEqual([k["kaynak"] for k in d["eskimis"]], ["scripts/panel.py"])
        self.assertEqual([k["kaynak"] for k in d["guncel"]], ["scripts/araclar_skill.py"])
        s = H.kenar_yenile(self.kok, self.graf)
        self.assertEqual(s["yenilenen"], 1)
        d2 = H.kenar_denetle(self.kok, self.graf)
        self.assertEqual((len(d2["guncel"]), len(d2["eskimis"])), (2, 0))

    def test_llm_kenari_dogrulanana_kadar_eskimis_ve_dusuk_guvenli_kalir(self):
        self.yaz("docs/a.md", "a")
        llm = dict(K.statik_kenarlar(self.kok)[0], kaynak="docs/a.md", iliski="belgeler", koken="llm", guven="orta",
                   kanit="docs/a.md:1", hash=K._hash(self.kok, "docs/a.md"))
        K.yaz(K.statik_kenarlar(self.kok) + [llm], self.yol)
        self.yaz("docs/a.md", "a değişti")
        s = H.kenar_yenile(self.kok, self.graf)
        self.assertEqual(s["dogrulanmayi_bekleyen"], 1)
        d = H.kenar_denetle(self.kok, self.graf)
        self.assertEqual([(k["koken"], k["guven"]) for k in d["eskimis"]], [("llm", "dusuk")])

    def test_kenar_dosyasi_yoksa_bos(self):
        os.remove(self.yol)
        self.assertEqual(H.kenar_denetle(self.kok, self.graf), {"guncel": [], "eskimis": []})


if __name__ == "__main__":
    unittest.main()
