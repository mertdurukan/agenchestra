"""G-164: SessionStart model politikası uyarısı (_model_sapma_satiri).
`py -3.13 -m pytest plugins/orkestra/tests/test_hook_model_politika.py`
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import model_politika as MP  # noqa: E402


class ModelPolitikaUyariTest(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_mpol_")
        os.makedirs(os.path.join(self.proje, ".claude"))

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def sat(self, model):
        return hook._model_sapma_satiri({"model": model, "cwd": self.proje})

    def test_k1_yasak(self):
        s = self.sat("claude-fable-5-1")
        self.assertIn("YASAK", s)
        self.assertNotIn("\n", s)
        self.assertLessEqual(len(s), 250)

    def test_k1_yukseltme_modeli_uyarisiz(self):
        self.assertEqual(self.sat("claude-opus-5"), "")

    def test_k1_haiku_politika_disi(self):
        self.assertIn("politika dışı", self.sat("claude-haiku-4-5"))

    def test_k1_varsayilan_bos(self):
        self.assertEqual(self.sat("claude-sonnet-5-5"), "")

    def test_k2_politika_yoksa_settings_yedegi(self):
        with open(os.path.join(self.proje, ".claude", "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"model": "claude-sonnet-5-5"}, f)
        with mock.patch.object(MP, "AYAR_DOSYASI", os.path.join(self.proje, "yok.json")):
            s = self.sat("claude-opus-5")
            self.assertTrue(s.startswith("UYARI: ana ajan modeli ayar dışı: oturum claude-opus-5"))
            self.assertEqual(self.sat("claude-sonnet-5-5"), "")


if __name__ == "__main__":
    unittest.main()
