"""Panel POST /api/isler-sifirla: başlık, Host ve onay kapıları; onayla IK.sifirla çağrılır."""
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
import is_kaydi  # noqa: E402
import panel  # noqa: E402


class IslerSifirlaUc(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        os.makedirs(os.path.join(self.proje, ".claude", "orkestra"))
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.alan])
        self.yama.start()
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.t.cleanup()

    def post(self, govde=b'{"onay": true}', baslik=None, host=None):
        h = {"Host": host or f"127.0.0.1:{self.port}", "X-Orkestra": "1", "Content-Type": "application/json"}
        h.update(baslik or {})
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("POST", "/api/isler-sifirla?alan=alan-x", skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        c.putheader("Content-Length", str(len(govde)))
        c.endheaders(govde)
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def test_onayla_sifirlanir(self):
        with mock.patch.object(is_kaydi, "sifirla", return_value={"silinen": 2, "yedek": None}) as s:
            k, b = self.post()
        self.assertEqual(k, 200)
        self.assertEqual(json.loads(b)["silinen"], 2)
        s.assert_called_once()

    def test_onaysiz_basliksiz_ve_yabanci_host_sifirlamaz(self):
        with mock.patch.object(is_kaydi, "sifirla") as s:
            self.assertEqual(self.post(govde=b"{}")[0], 400)
            self.assertEqual(self.post(govde=b'{"onay": "evet"}')[0], 400)
            self.assertEqual(self.post(baslik={"X-Orkestra": "0"})[0], 403)
            self.assertEqual(self.post(host="evil.example:80")[0], 403)
        s.assert_not_called()


if __name__ == "__main__":
    unittest.main()
