"""P4 (I-315): kayıtlı olmayan alan kimliği hesaplanmadan 404 olur; geçerli ve '*' yolları etkilenmez."""
import json
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import panel as P  # noqa: E402

ALANLAR = [{"id": "A", "ad": "A", "yol": "C:/a", "orkestra": True}]


class BilinmeyenAlan(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(P.L, "calisma_alanlari", return_value=ALANLAR)
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_tanimsiz_alan_404_govdesi_ve_hizli(self):
        t = time.time()
        r = P._bilinmeyen_alan_reddi("/ozet.json", {"alan": ["tum"]})
        self.assertLess(time.time() - t, 2)
        self.assertEqual(json.loads(r)["alan"], "tum")

    def test_gecerli_bos_ve_yildiz_gecer(self):
        for q in ({"alan": ["A"]}, {}, {"alan": [""]}, {"alan": ["*"]}):
            self.assertIsNone(P._bilinmeyen_alan_reddi("/ozet.json", q), q)

    def test_sayfa_statik_ve_hafif_yollar_gecer(self):
        for yol in ("/", "/app.js", "/api/guncelleme", "/onaylar.json", "/teknik.json"):
            self.assertIsNone(P._bilinmeyen_alan_reddi(yol, {"alan": ["tum"]}), yol)

    def test_kapi_ortam_degiskeniyle_kapanir(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_PANEL_ALAN_KAPISI": "0"}):
            self.assertIsNone(P._bilinmeyen_alan_reddi("/ozet.json", {"alan": ["tum"]}))


if __name__ == "__main__":
    unittest.main()
