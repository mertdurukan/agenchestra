"""'Seni bekliyor' kartında ne beklendiği: niyet.bekleme_nedeni(), gorunum() 'bekleme' alanı ve isler.html çizimi.

`py -3.13 -m pytest plugins/orkestra/tests/test_bekleme_nedeni.py -q -p no:cacheprovider`
"""
import json
import os
import re
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import niyet  # noqa: E402
from test_kapanis_rozeti import KapanisTemel  # noqa: E402


def _arac(ad, girdi, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"content": [{"type": "tool_use", "name": ad, "input": girdi}]}}


class BeklemeNedeni(unittest.TestCase):
    def _transkript(self, satirlar, onceki=()):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8", newline="\n")
        self.addCleanup(os.remove, f.name)
        for s in onceki:
            f.write(json.dumps(s) + "\n")
        f.flush()
        ofset = os.path.getsize(f.name)
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
        f.close()
        return f.name, ofset

    def test_wrap_up_ask_once(self):
        yol, of = self._transkript([_arac("mcp__ccd_turn__wrap_up", {"recap": "Düzeltme yapıldı.", "ask": "Commit atılsın mı?"})])
        self.assertEqual(niyet.bekleme_nedeni(yol, of, "Bitti. Başka soru?"), "Commit atılsın mı?")

    def test_ask_user_question_en_once(self):
        yol, of = self._transkript([
            _arac("AskUserQuestion", {"questions": [{"question": "Hangi yöntem?"}]}),
            _arac("mcp__ccd_turn__wrap_up", {"recap": "x.", "ask": "Commit?"})])
        self.assertEqual(niyet.bekleme_nedeni(yol, of, ""), "Hangi yöntem?")

    def test_onceki_tur_sayilmaz(self):
        yol, of = self._transkript([], onceki=[_arac("mcp__ccd_turn__wrap_up", {"recap": "eski.", "ask": "Eski soru?"})])
        self.assertEqual(niyet.bekleme_nedeni(yol, of, "Tablo hazır. Sütunlar doğru mu?"), "Sütunlar doğru mu?")

    def test_yan_zincir_sayilmaz(self):
        yol, of = self._transkript([_arac("AskUserQuestion", {"questions": [{"question": "Alt ajan?"}]}, sidechain=True)])
        self.assertEqual(niyet.bekleme_nedeni(yol, of, "Rapor yazıldı."), "")  # soru yok: neden çıkarılamaz (G-095)

    def test_soru_yoksa_recap_bos(self):
        yol, of = self._transkript([_arac("mcp__ccd_turn__wrap_up", {"recap": "Testler geçti. Commit yok."})])
        self.assertEqual(niyet.bekleme_nedeni(yol, of, ""), "")  # yalnız recap: açık soru değil (G-095)

    def test_markdown_temizlenir_ve_kisaltilir(self):
        m = "Özet:\n- **Bir** madde\n\n```py\nx = 1?\n```\n" + "[Plan](a.md) " + "uzun " * 60 + "onaylıyor musun?"
        s = niyet.bekleme_nedeni(None, 0, m)
        self.assertLessEqual(len(s), niyet.BEKLEME_UZUNLUK)
        self.assertNotIn("**", s)
        self.assertNotIn("x = 1", s)
        self.assertTrue(s.startswith("Plan uzun"), s)

    def test_hicbir_sey_yoksa_bos(self):
        self.assertEqual(niyet.bekleme_nedeni(os.path.join(tempfile.gettempdir(), "yok_xyz.jsonl"), 0, None), "")


class GorunumBekleme(KapanisTemel):
    def test_sen_satirinda_bekleme(self):
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (50, "tur", {"bekleme": "Commit atılsın mı?"})])
        self.assertEqual(s["bekleyen"], "sen")
        self.assertEqual(s["bekleme"], "Commit atılsın mı?")

    def test_yeni_istek_beklemeyi_siler(self):
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (50, "tur", {"bekleme": "Eski?"}), (2, "istek", {"metin": "evet"})])
        self.assertEqual(s["bekleyen"], "claude")
        self.assertIsNone(s["bekleme"])

    def test_bitti_satirinda_bekleme_yok(self):
        s = self._gorunum(self.SAKIN[:3] + [(45, "tur", {"bekleme": "x?"})] + self.SAKIN[3:])
        self.assertEqual(s["bekleyen"], "bitti")
        self.assertIsNone(s["bekleme"])


class IslerHtmlBekleme(unittest.TestCase):
    def test_sen_karti_yalniz_bekleme(self):
        with open(os.path.join(KOK, "assets", "isler.js"), encoding="utf-8") as f:
            html = f.read()
        govde = html[html.index("function sohbetKarti(r)"):html.index("function sohbetCiz()")]
        self.assertRegex(govde, r"const sen = r\.bekleyen === 'sen'")
        self.assertLess(govde.index("const sen"), govde.index("if (sen)"))  # TDZ yok
        self.assertRegex(govde, r"metin\(r\.bekleme")
        self.assertRegex(govde, r"kp = sen \? null")
        self.assertRegex(govde, r"!sen && \(isChip")


if __name__ == "__main__":
    unittest.main()
