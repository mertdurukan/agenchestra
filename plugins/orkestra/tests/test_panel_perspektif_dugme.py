"""Panel 'Perspektif çalıştır' düğmesi: POST /perspektif-calistir yeni masaüstü sohbeti başlatır (Popen taklit edilir)."""
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
import niyet  # noqa: E402
import panel  # noqa: E402
import perspektif  # noqa: E402


class PerspektifDugme(unittest.TestCase):
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

    def post(self, alan="alan-x", baslik=None, host=None):
        h = {"Host": host or f"127.0.0.1:{self.port}", "X-Orkestra": "1", "Content-Type": "application/json"}
        h.update(baslik or {})
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("POST", f"/perspektif-calistir?alan={alan}", skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        c.putheader("Content-Length", "2")
        c.endheaders(b"{}")
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def test_yeni_sohbet_istemle_acilir(self):
        with mock.patch.object(perspektif, "claude_exe", return_value="claude.exe"), \
                mock.patch("subprocess.Popen") as p:
            k, b = self.post()
        self.assertEqual(k, 200)
        self.assertTrue(json.loads(b)["tamam"])
        args, kw = p.call_args
        self.assertEqual(args[0], ["claude.exe", "--desktop", "/orkestra:perspektif şimdi"])
        self.assertEqual(kw["cwd"], self.proje)

    def test_basliksiz_ve_yabanci_host_403(self):
        with mock.patch("subprocess.Popen") as p:
            self.assertEqual(self.post(baslik={"X-Orkestra": "0"})[0], 403)
            self.assertEqual(self.post(host="evil.example:80")[0], 403)
        p.assert_not_called()

    def test_bilinmeyen_alan_400_ve_claude_yok_hatasi(self):
        with mock.patch("subprocess.Popen") as p:
            self.assertEqual(self.post(alan="yok")[0], 400)
        p.assert_not_called()
        with mock.patch.object(perspektif, "claude_exe", return_value=None):
            k, b = self.post()
        self.assertEqual(k, 200)
        self.assertFalse(json.loads(b)["tamam"])


if __name__ == "__main__":
    unittest.main()
