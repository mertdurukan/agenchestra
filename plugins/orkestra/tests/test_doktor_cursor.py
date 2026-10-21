"""I-139 P6 (bce F14): doktor Cursor hook sınırını tek satırda söyler; iz yoksa atlanır; BOM'lu hooks.json uyarı verir."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import doktor  # noqa: E402


class CursorSiniri(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_cur_")
        self.ev = tempfile.mkdtemp(prefix="ork_cur_ev_")
        self._p = mock.patch.object(doktor.os.path, "expanduser", return_value=self.ev)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.ev, ignore_errors=True)

    def _kontrol(self):
        return doktor.k_cursor_siniri(doktor.Baglam(proje=self.proje))

    def test_iz_yoksa_atlandi(self):
        s = self._kontrol()
        self.assertEqual(s.durum, "atlandi")

    def test_proje_cursor_klasoru_varsa_sinir_satiri(self):
        os.makedirs(os.path.join(self.proje, ".cursor"))
        s = self._kontrol()
        self.assertEqual(s.durum, "gecti")
        self.assertIn("IDE sürümü sınanmadı", s.mesaj)
        self.assertEqual(len(s.mesaj.splitlines()), 1)

    def test_kullanici_cursor_klasoru_yeter(self):
        os.makedirs(os.path.join(self.ev, ".cursor"))
        self.assertEqual(self._kontrol().durum, "gecti")

    def test_bomlu_hooks_json_uyari(self):
        d = os.path.join(self.proje, ".cursor")
        os.makedirs(d)
        with open(os.path.join(d, "hooks.json"), "wb") as f:
            f.write(b"\xef\xbb\xbf{}")
        s = self._kontrol()
        self.assertEqual(s.durum, "uyari")
        self.assertIn("BOM", s.mesaj)

    def test_kayitli_ve_opsiyonel(self):
        k = next(x for x in doktor.KONTROLLER if x.id == "cursor_siniri")
        self.assertEqual(k.sinif, "opsiyonel")
        ids = [x.id for x in doktor.KONTROLLER]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
