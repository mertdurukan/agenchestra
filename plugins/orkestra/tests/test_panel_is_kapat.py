"""Panel POST /api/is-kapat: başlık/Host kapıları, açık todo engeli, özet/ADR kapıları, gerekçeli özetsiz kapatma."""
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
import is_kaydi as IK  # noqa: E402
import panel  # noqa: E402
from komutlar import isler as KI  # noqa: E402


class IsKapatUc(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        self.yamalar = [mock.patch.object(L, "calisma_alanlari", lambda: [self.alan]),
                        mock.patch.object(KI, "_harita_yenile", lambda sd: None),
                        mock.patch.object(KI, "_teknik_detay_yaz", lambda sd, i: None)]
        # kapat_uygula os.getcwd() deposunda dal temizliği ve kapanış birleştirmesi koşar (ADR-0050, ADR-0086): testte
        # gerçek depoya git işlemi yapılmasın (ölçülen 23 sn; mod ihlal = dal silme)
        self.yamalar.append(mock.patch.dict(os.environ, {"ORKESTRA_DAL_TEMIZLE": "0", "ORKESTRA_KAPANIS_BIRLESTIRME": "0",
                                                         "ORKESTRA_OZET_KAPISI": "1"}))  # conftest kapıyı kapatır; test kapıyı sınar
        for y in self.yamalar:
            y.start()
        self.klasor = os.path.join(self.proje, "is1")
        os.makedirs(self.klasor)
        self.kayit = IK.is_ac(self.sd, "deneme", self.klasor)
        self.id = self.kayit["id"]
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        for y in self.yamalar:
            y.stop()
        self.t.cleanup()

    def post(self, govde, baslik=None, host=None):
        h = {"Host": host or f"127.0.0.1:{self.port}", "X-Orkestra": "1", "Content-Type": "application/json"}
        h.update(baslik or {})
        b = json.dumps(govde).encode()
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("POST", "/api/is-kapat?alan=alan-x", skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        c.putheader("Content-Length", str(len(b)))
        c.endheaders(b)
        r = c.getresponse()
        d = r.read()
        c.close()
        return r.status, json.loads(d) if d.startswith(b"{") else d

    def durum(self):
        return IK.is_al(self.sd, self.id)["durum"]

    def test_basliksiz_ve_yabanci_host_reddedilir(self):
        self.assertEqual(self.post({"is": self.id}, baslik={"X-Orkestra": "0"})[0], 403)
        self.assertEqual(self.post({"is": self.id}, host="evil.example:80")[0], 403)
        self.assertNotEqual(self.durum(), "kapandi")

    def test_gecersiz_govde(self):
        self.assertEqual(self.post({})[0], 400)
        self.assertEqual(self.post({"is": "../x"})[0], 400)
        self.assertEqual(self.post({"is": self.id, "ozetsiz": "  "})[0], 400)

    def test_bilinmeyen_is_404(self):
        self.assertEqual(self.post({"is": "I-99999"})[0], 404)

    def test_acik_todo_varsa_kapanmaz(self):
        with open(os.path.join(self.klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("# Todo\n\n- [ ] yapılacak iş\n")
        k, v = self.post({"is": self.id, "ozetsiz": "neden"})
        self.assertEqual(k, 409)
        self.assertNotEqual(self.durum(), "kapandi")

    def test_ozet_kapisi_engeller_gerekceyle_kapanir(self):
        k, v = self.post({"is": self.id})
        self.assertEqual((k, v.get("kapi")), (422, "ozet"))
        self.assertNotEqual(self.durum(), "kapandi")
        k, v = self.post({"is": self.id, "ozetsiz": "iş yapılmadı"})
        self.assertEqual(k, 200, v)
        self.assertEqual(self.durum(), "kapandi")
        self.assertEqual(self.post({"is": self.id, "ozetsiz": "x"})[0], 409)   # zaten kapalı


if __name__ == "__main__":
    unittest.main()
