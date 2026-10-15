"""SURECLER 'test-yaz' içerir; #SUREC:test-yaz etiketi transkriptte 'test-yaz' olarak çözülür."""
import json
import os
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import ork_lib as L  # noqa: E402


class SurecTestYaz(unittest.TestCase):
    def test_surecler_icerir(self):
        self.assertIn("test-yaz", L.SURECLER)

    def test_bilinmiyor_ve_digerleri_korunur(self):
        for s in ("is", "denetim", "bilinmiyor"):
            self.assertIn(s, L.SURECLER)

    def test_etiketler_metinden_cozer(self):
        g, s = L.etiketler("#GOREV:G-004 #SUREC:test-yaz\nGörev: x")
        self.assertEqual((g, s), ("G-004", "test-yaz"))

    def test_transkriptten_cozer(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "t.jsonl")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "user", "message": {"content": "#GOREV:G-004 #SUREC:test-yaz\nGörev"}}) + "\n")
            o = L.transkript_oku(yol)
        g, s = L.etiketler(o["ilk_kullanici"])
        self.assertEqual(g, "G-004")
        self.assertEqual(s, "test-yaz")

    def test_bilinmeyen_surec_hala_bilinmiyor(self):
        self.assertEqual(L.etiketler("#GOREV:G-1 #SUREC:test-yazx")[1], "bilinmiyor")
        self.assertEqual(L.etiketler("#SUREC:uydurma")[1], "bilinmiyor")

    def test_bos_girdi(self):
        self.assertEqual(L.etiketler(None), ("-", "bilinmiyor"))
        self.assertEqual(L.etiketler(""), ("-", "bilinmiyor"))


if __name__ == "__main__":
    unittest.main()
