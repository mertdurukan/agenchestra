"""niyet.gorunum() 'bekleyen' kararı: kancasız durgun sohbet ve arka plan turu.

`python -m unittest discover -s plugins/orkestra/tests -p test_niyet_durum.py -v`
Gerçek ~/.claude/orkestra-panel/niyet.jsonl'a dokunmaz (NIYET_YOLU geçici dosya).
"""
import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import niyet  # noqa: E402

PROJE = "C:/proje_deneme"  # Temp altında olmamalı (_gecici süzer)


def _z(dk_once: float) -> str:
    return (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=dk_once)).isoformat(timespec="seconds")


class NiyetDurumTesti(unittest.TestCase):
    def _durum(self, olaylar):
        """olaylar: [(dk_once, tur, ekstra_alanlar)] → tek oturumun 'bekleyen' değeri."""
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "niyet.jsonl")
            with open(yol, "w", encoding="utf-8") as f:
                for dk, tur, ek in olaylar:
                    f.write(json.dumps({"zaman": _z(dk), "oturum": "oturum-1", "proje": PROJE, "tur": tur, **ek}) + "\n")
            with mock.patch.object(niyet, "NIYET_YOLU", yol), \
                    mock.patch.object(niyet, "masaustu_oturumlari", return_value={}), \
                    mock.patch.object(niyet, "_basliklar", return_value={}), \
                    mock.patch.object(niyet, "_gunluk_istekleri", return_value=[]), \
                    mock.patch.object(niyet.L, "calisma_alanlari", return_value=[], create=True):
                g = niyet.gorunum()
        self.assertEqual(len(g["oturumlar"]), 1)
        return g["oturumlar"][0]["bekleyen"]

    def test_kancasiz_istek_durgun_beklemede(self):
        self.assertEqual(self._durum([(15, "istek", {"metin": "merhaba"})]), "beklemede")

    def test_kancasiz_istek_taze_claude(self):
        self.assertEqual(self._durum([(2, "istek", {"metin": "merhaba"})]), "claude")

    def test_kancali_tur_sen(self):
        self.assertEqual(self._durum([(20, "istek", {}), (15, "tur", {})]), "sen")

    def test_tur_arka_plan_claude(self):
        self.assertEqual(self._durum([(20, "istek", {}), (15, "tur", {"arka_plan": True})]), "claude")

    def test_arka_plan_sonrasi_duz_tur_sen(self):
        self.assertEqual(self._durum([(30, "istek", {}), (25, "tur", {"arka_plan": True}), (5, "tur", {})]), "sen")

    def test_kancali_istek_claude(self):
        self.assertEqual(self._durum([(40, "tur", {}), (20, "istek", {})]), "claude")

    def test_sonraki_istek_arka_plani_sifirlar(self):
        self.assertEqual(self._durum([(30, "tur", {"arka_plan": True}), (20, "istek", {}), (15, "tur", {})]), "sen")

    def test_kapandi_oncelikli(self):
        self.assertEqual(self._durum([(30, "tur", {"arka_plan": True}), (10, "kapandi", {})]), "kapandi")


if __name__ == "__main__":
    unittest.main()
