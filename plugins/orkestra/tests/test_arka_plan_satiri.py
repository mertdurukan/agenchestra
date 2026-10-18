"""Arka plan durum satırı: `python -m unittest discover -s plugins/orkestra/tests -v`

Stop kancası arka plan görevi sürerken tek satır systemMessage basar; hiçbir şey sürmüyorsa sessiz kalır.
Geçici projede çalışır; gerçek ~/.claude ya da proje durum dizinine yazılmaz.
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
import onay  # noqa: E402
import perspektif  # noqa: E402


class ArkaPlanSatiri(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_arka_")

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def satir(self, gorevler, persp=None, uygulama=None):
        with mock.patch.object(perspektif, "durum", return_value={"calisiyor": persp}), \
                mock.patch.object(onay, "uygulama_durumu", return_value=uygulama):
            return hook.arka_plan_satiri(self.sd, gorevler)

    def test_surmeyen_yok_bos(self):  # K1
        self.assertEqual(self.satir([]), "")
        self.assertEqual(self.satir(None), "")

    def test_gorev_adi_ve_sayi(self):  # K2
        s = self.satir([{"description": "Tam test takımını arka planda koş"}, {"id": "x"}])
        self.assertTrue(s.startswith("Arka planda sürüyor (2): "))
        self.assertIn("Tam test takımını", s)
        self.assertIn("görev", s)
        self.assertNotIn("\n", s)

    def test_dort_gorevde_artik_sayisi(self):
        s = self.satir([{"name": f"g{i}"} for i in range(4)])
        self.assertTrue(s.endswith("+1"))

    def test_perspektif_ve_onay(self):  # K3
        s = self.satir([], persp="2026-10-18T10:00:00+03:00", uygulama={"baslangic": "x"})
        self.assertIn("Perspektif koşusu", s)
        self.assertIn("Onaylı kararlar uygulanıyor", s)

    def test_bozuk_sema_hata_vermez(self):  # K4
        self.assertTrue(self.satir([1, None, "metin", {"description": 5}]).startswith("Arka planda sürüyor (4)"))
        self.assertEqual(self.satir("liste değil"), "")

    def test_workflow_acik_gorev_izine_girer(self):  # K5
        yol = os.path.join(self.sd, "t.jsonl")
        satirlar = [
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "w1", "name": "Workflow", "input": {"run_in_background": True}}]}},
            {"type": "user", "message": {"content": "<task-notification><tool-use-id>w1</tool-use-id><status>completed</status></task-notification>"}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "w2", "name": "Workflow", "input": {"run_in_background": True}}]}},
        ]
        with open(yol, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in satirlar) + "\n")
        self.assertEqual(hook._acik_arka_plan(yol, 0, os.path.getsize(yol), []), ["w2"])


if __name__ == "__main__":
    unittest.main()
