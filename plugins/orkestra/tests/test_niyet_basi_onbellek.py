"""niyet._transkript_basi: 12 satırı dolan transkriptin başı dosya büyüse de yeniden okunmaz; diske yazılır.

`python -m unittest discover -s plugins/orkestra/tests -p test_niyet_basi_onbellek.py -v`
Gerçek ~/.claude/orkestra-panel dizinine dokunmaz (_BASI_SABIT_YOL ve proje_oturum_dizini geçici).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import niyet  # noqa: E402


def _satir(i: int) -> str:
    if i == 0:
        return json.dumps({"type": "queue-operation", "operation": "enqueue", "content": "merhaba",
                           "timestamp": "2026-10-30T01:00:00+00:00", "entrypoint": "claude-desktop"}) + "\n"
    return json.dumps({"type": "x", "i": i}) + "\n"


class BasiOnbellekTesti(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.disk = os.path.join(self.d.name, "onb.json")
        for p in (mock.patch.object(niyet, "_BASI_SABIT_YOL", self.disk), mock.patch.object(niyet, "_BASI_SABIT", None),
                  mock.patch.object(niyet, "_BASI_ONBELLEK", {}),
                  mock.patch.object(niyet.L, "proje_oturum_dizini", lambda proje: self.d.name)):
            p.start()
            self.addCleanup(p.stop)
        self.yol = os.path.join(self.d.name, "s1.jsonl")

    def _yaz(self, n, mod="w"):
        with open(self.yol, mod, encoding="utf-8") as f:
            for i in range(n):
                f.write(_satir(i))

    def test_tam_baslik_buyuyen_dosyada_bir_kez_okunur(self):
        self._yaz(20)
        with mock.patch.object(niyet, "_transkript_basi_oku", wraps=niyet._transkript_basi_oku) as oku:
            for _ in range(3):
                b = niyet._transkript_basi("p", "s1")
                with open(self.yol, "a", encoding="utf-8") as f:  # dosya büyüyor: imza değişir
                    f.write(_satir(99))
            self.assertEqual(oku.call_count, 1)
        self.assertEqual(b["metin"], "merhaba")
        self.assertTrue(b["masaustu"])
        self.assertIsNotNone(b["zaman"])

    def test_diske_yazilir_ve_yeniden_baslatmada_okunmaz(self):
        self._yaz(20)
        niyet._transkript_basi("p", "s1")
        niyet._basi_diske_yaz()  # _yetimler sonunda toplu yazılır
        self.assertTrue(os.path.isfile(self.disk))
        niyet._BASI_SABIT = None  # panel yeniden başladı
        with mock.patch.object(niyet, "_transkript_basi_oku") as oku:
            b = niyet._transkript_basi("p", "s1")
            oku.assert_not_called()
        self.assertEqual(b["metin"], "merhaba")

    def test_eksik_baslik_imzali_kalir(self):
        self._yaz(5)
        with mock.patch.object(niyet, "_transkript_basi_oku", wraps=niyet._transkript_basi_oku) as oku:
            niyet._transkript_basi("p", "s1")
            self._yaz(5, "a")  # hâlâ 10 satır: baş tamamlanmadı
            niyet._transkript_basi("p", "s1")
            self.assertEqual(oku.call_count, 2)
        self.assertFalse(os.path.isfile(self.disk))

    def test_olmayan_dosya_none(self):
        self.assertIsNone(niyet._transkript_basi("p", "yok"))


if __name__ == "__main__":
    unittest.main()
