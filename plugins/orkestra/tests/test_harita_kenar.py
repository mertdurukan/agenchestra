"""Proje bilgi grafiği kenar çıkarıcı (ADR-0118, I-296): import, yol atfı, git birlikte-değişim; geçici projede koşar."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita_kenar as K  # noqa: E402
import harita_sema as S  # noqa: E402


class Kenar(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        self.yaz("scripts/panel.py", "import araclar_skill\nx = 1\n")
        self.yaz("scripts/araclar_skill.py", 'import os\nAD = "SKILL.md"\nAYAR = "ayarlar/a.json"\n')
        self.yaz("ayarlar/a.json", "{}")
        self.yaz("skills/s1/SKILL.md", "# s1")
        self.yaz("skills/s2/SKILL.md", "# s2")
        self.yaz("scripts/bozuk.py", "def (:\n")

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def yaz(self, rel, metin):
        yol = os.path.join(self.kok, rel)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)

    def test_import_kenari_kanit_satirli(self):
        k = [x for x in K.statik_kenarlar(self.kok) if x["iliski"] == "import"]
        self.assertEqual([(x["kaynak"], x["hedef"], x["kanit"]) for x in k],
                         [("scripts/panel.py", "scripts/araclar_skill.py", "scripts/panel.py:1")])

    def test_skill_md_atfi_desen_hedeflidir(self):
        k = [x for x in K.statik_kenarlar(self.kok) if x["kaynak"] == "scripts/araclar_skill.py"]
        hedefler = {x["hedef"] for x in k}
        self.assertEqual(hedefler, {"**/SKILL.md", "ayarlar/a.json"})
        self.assertTrue(all(x["kanit"].startswith("scripts/araclar_skill.py:") for x in k))

    def test_tum_kenarlar_semaya_uyar_ve_bozuk_dosya_atlanir(self):
        for x in K.statik_kenarlar(self.kok):
            self.assertEqual(S.kenar_hatalari(x), [], x)

    def test_hash_icerik_degisince_degisir(self):
        h1 = K.statik_kenarlar(self.kok)[0]["hash"]
        self.yaz("scripts/panel.py", "import araclar_skill\nx = 2\n")
        self.assertNotEqual(h1, [x for x in K.statik_kenarlar(self.kok) if x["kaynak"] == "scripts/panel.py"][0]["hash"])

    def test_git_birlikte_degisim(self):
        def git(*a):
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=self.kok, check=True, capture_output=True)
        git("init", "-q")
        for i in range(3):
            self.yaz("scripts/panel.py", f"import araclar_skill\nx = {i}\n")
            self.yaz("ayarlar/a.json", f'{{"i": {i}}}')
            git("add", "-A")
            git("commit", "-q", "-m", f"c{i}")
        k = K.gecmis_kenarlar(self.kok)
        self.assertEqual([(x["kaynak"], x["hedef"], x["koken"], x["kanit"]) for x in k],
                         [("ayarlar/a.json", "scripts/panel.py", "gecmis", "git:3 commit")])
        self.assertEqual(S.kenar_hatalari(k[0]), [])

    def test_yaz_gecersiz_kenari_yazmaz(self):
        yol = os.path.join(self.kok, "k.jsonl")
        iyi = K.statik_kenarlar(self.kok)[0]
        n, hata = K.yaz([iyi, dict(iyi, hash="")], yol)
        self.assertEqual((n, len(hata)), (1, 1))


if __name__ == "__main__":
    unittest.main()
