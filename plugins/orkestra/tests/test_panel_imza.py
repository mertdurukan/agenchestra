"""P3 (I-315): kaynak imzası değişmediyse ağır üretici yeniden koşmaz; değişince ya da IMZA_AZAMI aşılınca koşar."""
import http.server
import os
import sys
import threading
import time
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import panel  # noqa: E402

ALANLAR = [{"id": "x", "ad": "x", "yol": "x", "orkestra": True}]


class ImzaTesti(unittest.TestCase):
    def _kur(self, imza):
        sayac = {"n": 0}

        def ozet(alan):
            sayac["n"] += 1
            return {"acik": True}
        for p in (mock.patch.object(panel, "ISITMA_ADIM", 0.05), mock.patch.object(panel, "ISITMA_TABAN", 0.3),
                  mock.patch.object(panel, "_ozet_json", ozet), mock.patch.object(panel, "_imza_alan", lambda a: imza["v"]),
                  mock.patch.object(panel.L, "calisma_alanlari", return_value=ALANLAR)):
            p.start()
            self.addCleanup(p.stop)
        sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.addCleanup(sunucu.RequestHandlerClass.isitmayi_durdur)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        self.addCleanup(sunucu.server_close)
        self.addCleanup(sunucu.shutdown)
        al = lambda: urllib.request.urlopen(f"http://127.0.0.1:{sunucu.server_port}/ozet.json?alan=x", timeout=5).read()  # noqa: E731
        return al, sayac

    def test_imza_ayniysa_yeniden_hesaplanmaz(self):
        al, sayac = self._kur({"v": 1})
        al()
        time.sleep(2.6)   # TTL 1 sn: ısıtıcı ve istekler eskir; imza aynı
        al()
        self.assertEqual(sayac["n"], 1)

    def test_imza_degisince_hesaplanir(self):
        imza = {"v": 1}
        al, sayac = self._kur(imza)
        al()
        imza["v"] = 2
        time.sleep(1.4)
        al()
        time.sleep(0.5)
        self.assertGreaterEqual(sayac["n"], 2)

    def test_imza_azami_asilinca_hesaplanir(self):
        al, sayac = self._kur({"v": 1})
        with mock.patch.object(panel, "IMZA_AZAMI", 0.5):
            al()
            time.sleep(1.4)
            al()
            time.sleep(0.5)
        self.assertGreaterEqual(sayac["n"], 2)


if __name__ == "__main__":
    unittest.main()
