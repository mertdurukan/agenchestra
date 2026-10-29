"""I-255 P2: iki eklenti kopyası dönüşümlü çalışırken panel görevi her SessionStart'ta yeniden kurulmaz.
`py -3.13 -m pytest plugins/orkestra/tests/test_panel_servis_yol.py`
schtasks ve süreç başlatma taklit edilir; gerçek görev ve ~/.claude etkilenmez.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import panel_servis  # noqa: E402


class YolDalgalanmasiTest(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.mkdtemp(prefix="ork_psrv_yol_")
        self.isaret = os.path.join(self.dizin, "p.json")
        self.eski = os.path.join(self.dizin, "diger_kopya", "panel.py")
        os.makedirs(os.path.dirname(self.eski))
        with open(self.eski, "w", encoding="utf-8") as f:
            f.write("# diğer eklenti kopyası")
        for y in (mock.patch.object(panel_servis.os, "name", "nt"),
                  mock.patch.object(panel_servis, "ISARET", self.isaret),
                  mock.patch.dict(os.environ, {}, clear=False)):
            y.start()
            self.addCleanup(y.stop)
        os.environ.pop("ORKESTRA_PANEL_SERVIS", None)

    def _isaret(self, betik):
        with open(self.isaret, "w", encoding="utf-8") as f:
            json.dump({"durum": "kuruldu", "betik": betik}, f)

    def test_eski_yol_varsa_ve_gorev_kuruluysa_yeniden_kurulmaz(self):
        self._isaret(self.eski)
        with mock.patch.object(panel_servis, "kurulu", return_value=True), \
                mock.patch.object(panel_servis, "kur") as kur:
            for _ in range(3):
                self.assertIsNone(panel_servis.otomatik_kur())
        kur.assert_not_called()

    def test_eski_yol_varken_gorev_silinmisse_kurar(self):
        self._isaret(self.eski)
        with mock.patch.object(panel_servis, "kurulu", return_value=False), \
                mock.patch.object(panel_servis, "kur") as kur:
            self.assertEqual(panel_servis.otomatik_kur(), "kuruldu")
        kur.assert_called_once()

    def test_eski_yol_yoksa_yeniden_kaydeder(self):
        self._isaret(os.path.join(self.dizin, "silinmis", "panel.py"))
        with mock.patch.object(panel_servis, "kurulu", return_value=True), \
                mock.patch.object(panel_servis, "_gorev_betigi_guncel", return_value=False), \
                mock.patch.object(panel_servis, "kur") as kur:
            self.assertEqual(panel_servis.otomatik_kur(), "kuruldu")
        kur.assert_called_once()


if __name__ == "__main__":
    unittest.main()
