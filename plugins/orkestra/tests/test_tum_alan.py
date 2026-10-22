"""panel.py 'Tüm çalışma alanları' (alan=*): yalnız /simdi.json kabul eder; tek alan isteyen yollar 400 döner,
sessizce ilk alana düşmez (sunucu süreç içinde açılır, panel.json'a dokunulmaz)."""
import http.client
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import ork_lib as L  # noqa: E402
import panel  # noqa: E402


class TumAlan(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        proje = os.path.join(self.t.name, "proje")
        os.makedirs(os.path.join(proje, ".claude", "orkestra"))
        alan = {"id": "alan-x", "ad": "proje", "yol": proje, "orkestra": True, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [alan])
        self.yama.start()
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.t.cleanup()

    def istek(self, yontem, yol, govde=None, baslik=None):
        h = {"Host": f"127.0.0.1:{self.port}"}
        h.update(baslik or {})
        veri = json.dumps(govde).encode("utf-8") if govde is not None else None
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(yontem, yol, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        if veri is not None:
            c.putheader("Content-Length", str(len(veri)))
        c.endheaders(veri)
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def test_simdi_tum_alanlari_verir(self):
        k, b = self.istek("GET", "/simdi.json?alan=*")
        self.assertEqual(k, 200)
        v = json.loads(b)
        self.assertIsInstance(v["oturumlar"], list)
        self.assertNotIn("alan", v)  # tek alana süzülmedi

    def test_birlesen_yollar_200_ve_alan_etiketli(self):
        for yol in ("/onaylar.json", "/isler.json", "/kurallar.json", "/ozet.json", "/analitik.json",
                    "/api/kullanici-todo", "/teknik.json"):
            k, b = self.istek("GET", f"{yol}?alan=*")
            self.assertEqual(k, 200, yol)
            v = json.loads(b)
            self.assertTrue(v["acik"], yol)
            self.assertEqual(v["alan"]["id"], "*", yol)
            self.assertTrue(v["birlesik"], yol)
            self.assertEqual([a["id"] for a in v["alanlar"]], ["alan-x"], yol)

    def test_tek_alan_isteyen_get_yollari_400(self):
        for yol in ("/api/todo", "/api/etki", "/teknik.json?is=I-001", "/teknik.json?kart=G-001", "/teknik.json?ret=1"):
            k, b = self.istek("GET", yol + ("&" if "?" in yol else "?") + "alan=*")
            self.assertEqual(k, 400, yol)
            self.assertIn("tek bir çalışma alanı", json.loads(b)["hata"], yol)

    def test_yazma_400(self):
        basliklar = {"X-Orkestra": "1", "Content-Type": "application/json"}
        for yol in ("/onay", "/api/isler-sifirla", "/perspektif-calistir", "/api/kullanici-todo", "/api/kural-dosya"):
            k, b = self.istek("POST", f"{yol}?alan=*", {"onay": True}, basliklar)
            self.assertEqual(k, 400, yol)
            self.assertIn("tek bir çalışma alanı", json.loads(b)["hata"], yol)

    def test_gercek_alan_ve_sayfalar_etkilenmez(self):
        k, _ = self.istek("GET", "/ozet.json?alan=alan-x")
        self.assertEqual(k, 200)
        for yol in ("/isler?alan=*", "/maliyet?alan=*", "/ortak.js?alan=*", "/alanlar.json", "/analitik-tum.json"):
            k, _ = self.istek("GET", yol)
            self.assertEqual(k, 200, yol)


if __name__ == "__main__":
    unittest.main()
