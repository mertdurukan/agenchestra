"""I-312: panel veri alma gecikmesi — süre günlüğü (P1), is_serit N+1 düzeltmesi (P3), istemci yeniden deneme (P4)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))

import panel  # noqa: E402
import is_kaydi as IK  # noqa: E402


class GecikmeGunluguTest(unittest.TestCase):
    def test_yavas_istek_isaretlenir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "g.jsonl")
            with mock.patch.object(panel, "GECIKME_GUNLUK", yol):
                panel.gecikme_yaz("/isler.json?alan=*", 1.5, 200)
                panel.gecikme_yaz("/saglik", 0.01, 200)
            satirlar = [json.loads(s) for s in open(yol, encoding="utf-8")]
        self.assertEqual([s["yol"] for s in satirlar], ["/isler.json", "/saglik"])
        self.assertTrue(satirlar[0]["yavas"])
        self.assertEqual(satirlar[0]["alan"], "*")
        self.assertFalse(satirlar[1]["yavas"])

    def test_gunluk_hatasi_istegi_bozmaz(self):
        with mock.patch.object(panel, "GECIKME_GUNLUK", os.path.join(os.devnull, "x", "g.jsonl")):
            panel.gecikme_yaz("/saglik", 0.0, 200)   # istisna fırlatmamalı


class IsSeritTekGirisTest(unittest.TestCase):
    def test_is_serit_tum_is_listesini_cozmez(self):
        """Gerileme: is_serit is_liste(sd) çağırırsa panel iş sayısının karesi kadar dosya sistemi çağrısı yapar."""
        with mock.patch.object(IK, "is_liste", side_effect=AssertionError("is_liste çağrıldı")), \
                mock.patch.object(IK, "is_al", return_value={"id": "I-1"}), \
                mock.patch.object(IK, "merkez_giris", return_value={"klasor": "yok", "baslik": "x", "durum": "acik"}) as mg, \
                mock.patch.object(IK, "todo_maddeleri", return_value=[]):
            try:
                IK.is_serit("sd", "I-1", tum_kartlar=[])
            except AssertionError:
                raise
            except Exception:  # noqa: BLE001  (ileri adımlar sahte veriyle düşebilir; yalnız çağrı biçimi sınanır)
                pass
            mg.assert_called_once_with("sd", "I-1")


class IstemciYenidenDenemeTest(unittest.TestCase):
    def test_getir_zaman_asiminda_yeniden_dener_ve_bayat_isaretler(self):
        js = open(os.path.join(KOK, "assets", "app.js"), encoding="utf-8").read()
        self.assertIn("const DENEME = 2", js)
        self.assertIn("k.bayat = !!k.veri", js)
        self.assertIn("e.sunucu", js)   # HTTP/JSON hatası yeniden denenmez


if __name__ == "__main__":
    unittest.main()
