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
        with mock.patch("os.startfile", create=True) as sf, mock.patch("subprocess.Popen") as p:
            k, b = self.post()
        self.assertEqual(k, 200)
        self.assertTrue(json.loads(b)["tamam"])
        link = (sf.call_args or p.call_args)[0][0]
        link = link if isinstance(link, str) else link[-1]
        self.assertTrue(link.startswith("claude://code/new?q="))
        self.assertIn("%2Forkestra%3Aperspektif", link)
        self.assertIn("folder=", link)

    def test_baglanti_proje_ve_klasoru_tasir(self):
        """I-148: istem projeyi açıkça taşır, folder= alan yoludur (sohbet klasörsüz açılsa da koşu yanlış projeye yazmasın)."""
        import urllib.parse
        with mock.patch("os.startfile", create=True) as sf, mock.patch("subprocess.Popen") as p:
            self.post()
        link = (sf.call_args or p.call_args)[0][0]
        link = link if isinstance(link, str) else link[-1]
        sorgu = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
        self.assertEqual(sorgu["q"], [f"/orkestra:perspektif şimdi proje={self.proje}"])
        self.assertEqual(sorgu["folder"], [self.proje])

    def test_proje_uyusmazligi(self):
        a = self.proje
        b = os.path.join(self.t.name, "baska")
        os.makedirs(b)
        self.assertIsNone(perspektif.proje_uyusmazligi(None, a))
        self.assertIsNone(perspektif.proje_uyusmazligi(a, a))
        mesaj = perspektif.proje_uyusmazligi(a, b)
        self.assertIn("yanlış klasör", mesaj)
        self.assertIn("change_directory", mesaj)

    def test_basladi_yanlis_klasorde_reddeder_ve_yazmaz(self):
        from komutlar import onay
        sd = os.path.join(self.proje, ".claude", "orkestra")
        baska = os.path.join(self.t.name, "baska")
        os.makedirs(baska)
        a = mock.Mock(islem="basladi", yol=None, proje=baska, komut="perspektif")
        with mock.patch.object(onay, "sd_gerekli", return_value=sd), \
                mock.patch.object(L, "proje_dizini", return_value=self.proje), \
                mock.patch.object(perspektif, "basladi_isaretle") as bi, \
                self.assertRaises(SystemExit):
            onay.cmd_perspektif(a)
        bi.assert_not_called()
        a.proje = self.proje
        with mock.patch.object(onay, "sd_gerekli", return_value=sd), \
                mock.patch.object(L, "proje_dizini", return_value=self.proje), \
                mock.patch.object(perspektif, "basladi_isaretle") as bi:
            onay.cmd_perspektif(a)
        bi.assert_called_once_with(sd)

    def test_baglanti_acilamazsa_hata(self):
        with mock.patch("os.startfile", create=True, side_effect=OSError("yok")),                 mock.patch("subprocess.Popen", side_effect=OSError("yok")):
            k, b = self.post()
        self.assertEqual(k, 200)
        self.assertFalse(json.loads(b)["tamam"])

    def test_basliksiz_ve_yabanci_host_403(self):
        with mock.patch("subprocess.Popen") as p:
            self.assertEqual(self.post(baslik={"X-Orkestra": "0"})[0], 403)
            self.assertEqual(self.post(host="evil.example:80")[0], 403)
        p.assert_not_called()

    def test_bilinmeyen_alan_400(self):
        with mock.patch("subprocess.Popen") as p:
            self.assertEqual(self.post(alan="yok")[0], 400)
        p.assert_not_called()

    def test_yeni_arayuz_gelen_kutusunda_perspektif_ogesi_var(self):
        """ADR-0026: zamanı gelen perspektif Gelen kutusunda öğe + düğme; başlatma elle, aynı uca gider."""
        with open(os.path.join(AD, "..", "assets", "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("pd?.zamani_geldi && !pd.calisiyor", js)
        self.assertIn("data-eylem=\"perspektif\"", js)
        self.assertIn("gonder('/perspektif-calistir'", js)

if __name__ == "__main__":
    unittest.main()
