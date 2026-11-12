"""Kapanış yolu (I-461 P2): CLI, panel ve bakım çağıranları is_durum'a doğru `yol` ve `gerekce` geçirir (gerçek çağrı)."""
import argparse
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
import is_olu_yol as O  # noqa: E402
from komutlar import isler as KI  # noqa: E402
from komutlar import bakim as B  # noqa: E402

NEDEN = "iş yapılmadı"


class KapanisYoluCagiranlar(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        self.yamalar = [mock.patch.object(L, "calisma_alanlari", lambda: [self.alan]),
                        mock.patch.object(KI, "_harita_yenile", lambda sd: None),
                        mock.patch.object(KI, "_teknik_detay_yaz", lambda sd, i: None),
                        mock.patch.object(KI, "sd_gerekli", lambda: self.sd),
                        mock.patch.dict(os.environ, {"ORKESTRA_DAL_TEMIZLE": "0", "ORKESTRA_KAPANIS_BIRLESTIRME": "0",
                                                     "ORKESTRA_OZET_KAPISI": "1"})]
        for y in self.yamalar:
            y.start()
        self.klasor = os.path.join(self.proje, "is1")
        os.makedirs(self.klasor)
        self.id = IK.is_ac(self.sd, "deneme", self.klasor)["id"]
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        for y in self.yamalar:
            y.stop()
        self.t.cleanup()

    def olay(self):
        k = IK.is_al(self.sd, self.id)
        self.assertEqual(k["durum"], "kapandi")
        return [o for o in k["gecmis"] if o.get("olay") == "durum:kapandi"][-1]

    def test_cli_varsayilan_yol_cli(self):
        KI.cmd_is_kapat(argparse.Namespace(is_id=self.id, ozetsiz=NEDEN))
        o = self.olay()
        self.assertEqual((o["yol"], o.get("gerekce")), ("cli", NEDEN))

    def test_panel_yol_panel_ve_gerekce(self):
        b = json.dumps({"is": self.id, "ozetsiz": NEDEN}).encode()
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("POST", "/api/is-kapat?alan=alan-x", skip_host=True)
        for k, v in {"Host": f"127.0.0.1:{self.port}", "X-Orkestra": "1", "Content-Type": "application/json",
                     "Content-Length": str(len(b))}.items():
            c.putheader(k, v)
        c.endheaders(b)
        r = c.getresponse()
        r.read()
        c.close()
        self.assertEqual(r.status, 200)
        o = self.olay()
        self.assertEqual((o["yol"], o.get("gerekce")), ("panel", NEDEN))

    def test_bakim_yol_bakim_ve_ozetsiz_neden(self):
        a = argparse.Namespace(kapat=True, json=True, sohbet=False)
        rapor = {"kapatilan_is": []}
        with mock.patch.object(O, "olu_yollar", return_value=[]),                 mock.patch.object(O, "terk_isler", return_value=[{"id": self.id}]):
            B.olu_yol_ve_terk(self.sd, a, rapor, True)
        self.assertEqual(rapor["kapatilan_is"], [self.id])
        o = self.olay()
        self.assertEqual((o["yol"], o.get("gerekce")), ("bakim", B.OZETSIZ_NEDEN))


if __name__ == "__main__":
    unittest.main()
