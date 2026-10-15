"""niyet.gorunum(): arka plan turunda 60 dk zaman aşımı.

`python -m unittest discover -s plugins/orkestra/tests -p test_niyet_zaman_asimi.py -v`
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


class ArkaPlanZamanAsimiTesti(unittest.TestCase):
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

    def test_sabit_60(self):
        self.assertEqual(niyet.ARKA_PLAN_ZAMAN_ASIMI_DK, 60)

    def test_61_dk_durgun_beklemede(self):
        self.assertEqual(self._durum([(70, "istek", {}), (61, "tur", {"arka_plan": True})]), "beklemede")

    def test_10_dk_claude(self):
        self.assertEqual(self._durum([(20, "istek", {}), (10, "tur", {"arka_plan": True})]), "claude")

    def test_59_dk_claude(self):
        self.assertEqual(self._durum([(65, "istek", {}), (59, "tur", {"arka_plan": True})]), "claude")

    def test_arka_plan_sonrasi_istek_mevcut_davranis(self):
        # istek taze (2 dk) ve kancalı: Claude çalışıyor
        self.assertEqual(self._durum([(90, "tur", {"arka_plan": True}), (2, "istek", {})]), "claude")
        # sonuncu olay normal 'tur' (arka plan değil): tur bitti, kullanıcı sırası → 'sen'
        self.assertEqual(self._durum([(120, "tur", {"arka_plan": True}), (90, "istek", {}), (80, "tur", {})]), "sen")

    def test_kapandi_zaman_asimindan_once(self):
        self.assertEqual(self._durum([(120, "tur", {"arka_plan": True}), (90, "kapandi", {})]), "kapandi")


if __name__ == "__main__":
    unittest.main()
