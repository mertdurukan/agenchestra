"""Panel arka plan ısıtma: istenen önbellek anahtarı, istek gelmese de aralıkla yenilenir; ORKESTRA_PANEL_ISITMA=0 kapatır.

`python -m unittest discover -s plugins/orkestra/tests -p test_panel_isitma.py -v`
"""
import http.server
import os
import sys
import threading
import time
import unittest
import urllib.request
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import panel  # noqa: E402


class IsitmaTesti(unittest.TestCase):
    def _sunucu(self):
        sayac = {"n": 0}

        def ozet(alan):
            sayac["n"] += 1
            return {"acik": True}

        for p in (mock.patch.object(panel, "ISITMA_ADIM", 0.05), mock.patch.object(panel, "ISITMA_TABAN", 0.3),
                  mock.patch.object(panel, "_ozet_json", ozet),
                  mock.patch.object(panel, "_imza_alan", lambda alan: time.time()),   # kaynak sürekli değişiyor: ısıtıcı yeniler
                  mock.patch.object(panel.L, "calisma_alanlari", return_value=[{"id": "x", "ad": "x", "yol": "x", "orkestra": True}])):
            p.start()
            self.addCleanup(p.stop)
        sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.addCleanup(sunucu.RequestHandlerClass.isitmayi_durdur)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        self.addCleanup(sunucu.server_close)
        self.addCleanup(sunucu.shutdown)
        return sunucu, sayac

    def _al(self, sunucu):
        return urllib.request.urlopen(f"http://127.0.0.1:{sunucu.server_port}/ozet.json?alan=x", timeout=5).read()

    def test_istek_gelmese_de_yenilenir(self):
        sunucu, sayac = self._sunucu()
        self._al(sunucu)
        self.assertEqual(sayac["n"], 1)
        time.sleep(3.2)  # istek yok; ozet TTL'i 1 sn; ısıtıcı aralığı max(TTL, taban)=1 sn, istek olmadan yeniler
        self.assertGreaterEqual(sayac["n"], 3)

    def test_ortam_degiskeniyle_kapanir(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_PANEL_ISITMA": "0"}):
            sunucu, sayac = self._sunucu()
            self._al(sunucu)
            time.sleep(1.0)
        self.assertEqual(sayac["n"], 1)


if __name__ == "__main__":
    unittest.main()
