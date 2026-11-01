"""I-323 P5: kuyruk kapısı golge modunda kayıtlı (P-028) ve todo şablonu kuyruğa teslimi söyler."""
import json
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))

import kapi_mod as KM  # noqa: E402
from komutlar import kapi as KAPI  # noqa: E402


class KuyrukKapi(unittest.TestCase):
    def test_ayar_golge_ve_kapatma_anilir(self):
        with open(os.path.join(KOK, "ayarlar", "kuyruk.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["mod"], "golge")
        self.assertIn("ORKESTRA_KUYRUK_KAPISI=0", d["aciklama"])
        self.assertIn("P-028", d["aciklama"])

    def test_kapi_mod_golge(self):
        self.assertEqual(KM.mod("kuyruk"), "golge")

    def test_kapi_durum_listesinde(self):
        satir = [r for r in KAPI.kapi_satirlari(None) if r["kapi"] == "kuyruk"]
        self.assertEqual(len(satir), 1)
        self.assertEqual(satir[0]["etkin"], "golge")

    def test_todo_sablonu_kuyruga_teslim(self):
        with open(os.path.join(KOK, "sablonlar", "todo.md"), encoding="utf-8") as f:
            self.assertIn("orkestra teslim kuyruk ekle", f.read())


if __name__ == "__main__":
    unittest.main()
