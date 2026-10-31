"""İstek eşleme sorgusu (ADR-0112, I-296): eşanlamlı eşleme, kenar gezinmesi, eşleşmeyen istek; geçici graf dizininde koşar."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita_istek as I  # noqa: E402

KART = ("# Skill\n## Amaç\nSkill eklemek.\n## Eşanlamlılar\n- skill ekle\n- yeni yetenek\n"
        "## Yüzeyler\n- arayüz aç/kapa listesi (scripts/araclar_skill.py)\n- skill dosyası (skills/*/SKILL.md)\n"
        "## Değişmezler\nSKILL.md zorunlu\n")


def kenar(kaynak, iliski, hedef, koken="statik", guven="yuksek"):
    return {"kaynak": kaynak, "iliski": iliski, "hedef": hedef, "koken": koken, "guven": guven, "kanit": f"{kaynak}:1",
            "hash": "ab", "dogrulama_zamani": "2026-10-31T00:00:00"}


class Istek(unittest.TestCase):
    def setUp(self):
        self.graf = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.graf, "kartlar"))
        with open(os.path.join(self.graf, "kartlar", "skill.md"), "w", encoding="utf-8") as f:
            f.write(KART)
        with open(os.path.join(self.graf, "kenarlar.jsonl"), "w", encoding="utf-8") as f:
            for k in (kenar("scripts/panel.py", "import", "scripts/araclar_skill.py"),
                      kenar("scripts/araclar_skill.py", "atif", "**/SKILL.md"),
                      kenar("docs/x.md", "belgeler", "scripts/araclar_skill.py", "llm", "dusuk"),
                      kenar("scripts/baska.py", "import", "scripts/ilgisiz.py")):
                f.write(json.dumps(k) + "\n")

    def tearDown(self):
        shutil.rmtree(self.graf, ignore_errors=True)

    def test_yeni_skill_ekle_arayuz_yuzeyini_bulur(self):
        s = I.etki("Yeni skill ekle", self.graf)
        self.assertTrue(s["eslesti"])
        self.assertIn("arayüz aç/kapa listesi", [y["ad"] for y in s["yuzeyler"]])
        self.assertIn("arayüz aç/kapa listesi", I.metin(s))

    def test_kenar_gezinmesi_iki_yonlu_ve_ilgisizi_dislar(self):
        s = I.etki("yeni skill ekle", self.graf)
        kaynaklar = {k["kaynak"] for k in s["komsular"]}
        self.assertEqual(kaynaklar, {"scripts/panel.py", "scripts/araclar_skill.py"})
        self.assertEqual([k["kaynak"] for k in s["belirsiz"]], ["docs/x.md"])

    def test_ek_toleransi(self):
        self.assertTrue(I.etki("skilleri eklemek istiyorum", self.graf)["eslesti"])

    def test_esanlamli_ifade(self):
        self.assertEqual(I.etki("yeni yetenek lazım", self.graf)["konular"], ["skill"])

    def test_eslesmeyen_istek_bos_kume(self):
        s = I.etki("hava durumu nasıl", self.graf)
        self.assertEqual((s["eslesti"], s["yuzeyler"], s["komsular"]), (False, [], []))
        self.assertTrue(I.metin(s).startswith("eşleşmedi"))

    def test_graf_yoksa_eslesmedi(self):
        self.assertFalse(I.etki("skill ekle", os.path.join(self.graf, "yok"))["eslesti"])


if __name__ == "__main__":
    unittest.main()
