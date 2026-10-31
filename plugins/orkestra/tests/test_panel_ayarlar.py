"""Panel Ayarlar sayfası: Bildirim aç/kapat. `python -m pytest plugins/orkestra/tests/test_panel_ayarlar.py -q`

(a) Ayar makine config'ine yazılır ve bildirim.aktif() onu izler; (b) ORKESTRA_BILDIRIM ortam değişkeni panel ayarından önce gelir;
(c) panel uç noktası ayarı döner/yazar, ortam kilidinde 409 verir, geçersiz gövdeyi reddeder; (d) arayüzde sayfa ve anahtar bağlıdır.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import bildirim  # noqa: E402
import panel  # noqa: E402


class AyarlarTesti(unittest.TestCase):
    def setUp(self):
        self.ev = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ev, True)
        env = mock.patch.dict(os.environ, {"ORKESTRA_HOME": self.ev})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("ORKESTRA_BILDIRIM", None)

    def test_varsayilan_acik(self):
        self.assertEqual(bildirim.ayar(), (True, "varsayilan"))

    def test_kapat_ve_ac_makineye_yazilir(self):
        bildirim.ayar_yaz(False)
        self.assertEqual(bildirim.ayar(), (False, "makine"))
        with mock.patch.object(sys, "platform", "win32"):
            self.assertFalse(bildirim.aktif())
            bildirim.ayar_yaz(True)
            self.assertTrue(bildirim.aktif())

    def test_ortam_degiskeni_oncelikli(self):
        bildirim.ayar_yaz(True)
        with mock.patch.dict(os.environ, {"ORKESTRA_BILDIRIM": "0"}):
            self.assertEqual(bildirim.ayar(), (False, "ortam"))
            sonuc = panel._ayarlar_yaz(True)
            self.assertFalse(sonuc["tamam"])
            self.assertEqual(bildirim.ayar(), (False, "ortam"))

    def test_panel_durum_ve_yazma(self):
        self.assertTrue(panel._ayarlar_durum()["bildirim"]["acik"])
        sonuc = panel._ayarlar_yaz(False)
        self.assertTrue(sonuc["tamam"])
        self.assertEqual(sonuc["bildirim"]["acik"], False)
        self.assertEqual(sonuc["bildirim"]["kaynak"], "makine")
        json.dumps(sonuc)

    def test_arayuz_baglantisi(self):
        js = open(os.path.join(KOK, "assets", "app.js"), encoding="utf-8").read()
        for parca in ("'/api/ayarlar'", "ayarlar: gAyarlar", "data-eylem=\"ayar-bildirim\"", "'#/ayarlar'", "role=\"switch\""):
            self.assertIn(parca, js)
        self.assertIn("/api/ayarlar", panel.KULLANICI_YOLLARI)


class VarsayilanModTesti(unittest.TestCase):
    """GET/POST /api/ayarlar?alan=<id>: seçili alanın varsayılan çalışma modu (ADR-0103)."""

    def setUp(self):
        self.ev = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ev, True)
        self.sd = os.path.join(self.ev, ".claude", "orkestra")
        os.makedirs(self.sd)
        alan = {"id": "a1", "ad": "Proje", "yol": self.ev, "orkestra": True}
        p = mock.patch.object(panel.L, "calisma_alanlari", return_value=[alan])
        p.start()
        self.addCleanup(p.stop)
        self.dosya = os.path.join(self.sd, "yetki.json")

    def test_get_kaynak_etiketi(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from mod_yalitim import eklenti_varsayilani
        for eklenti in ("plan", "auto"):
            for dosya in (self.dosya, self.dosya + ".bak"):
                if os.path.exists(dosya):
                    os.remove(dosya)
            with eklenti_varsayilani(eklenti):
                d = panel._ayarlar_durum("a1")["varsayilan_mod"]
                self.assertEqual(d["deger"], eklenti)
                self.assertEqual(d["kaynak"], "eklenti")  # eklentinin ayarlar/ dosyasındaki değer
                self.assertEqual(d["alan"], "Proje")
                panel._mod_yaz("a1", "plan" if eklenti == "auto" else "auto")
                d = panel._ayarlar_durum("a1")["varsayilan_mod"]
                self.assertEqual((d["deger"], d["kaynak"]), ("plan" if eklenti == "auto" else "auto", "proje"))

    def test_alan_yoksa_mod_yok_bildirim_kalir(self):
        for alan in (None, "*", "yok"):
            d = panel._ayarlar_durum(alan)
            self.assertNotIn("varsayilan_mod", d)
            self.assertIn("bildirim", d)

    def test_post_yazar_ve_diger_anahtarlari_korur(self):
        with open(self.dosya, "w", encoding="utf-8") as f:
            json.dump({"surum": 1, "not": "x"}, f)
        sonuc = panel._mod_yaz("a1", "auto")
        self.assertTrue(sonuc["tamam"])
        veri = json.load(open(self.dosya, encoding="utf-8"))
        self.assertEqual((veri["varsayilan_mod"], veri["not"]), ("auto", "x"))
        self.assertFalse(os.path.exists(self.dosya + ".tmp"))
        import is_onay
        self.assertEqual(is_onay.varsayilan_mod(self.sd), "auto")

    def test_gecersiz_deger_dosya_yazmaz(self):
        for v in ("AUTO", "", None, 1, "full"):
            self.assertFalse(panel._mod_yaz("a1", v)["tamam"])
        self.assertFalse(os.path.exists(self.dosya))

    def test_arayuz_mod_secici(self):
        js = open(os.path.join(KOK, "assets", "app.js"), encoding="utf-8").read()
        for parca in ('data-eylem="ayar-mod"', 'role="radiogroup"', "ey === 'ayar-mod'", "varsayilan_mod: hedef", 'data-eylem="ayar-bildirim"', 'role="switch"'):
            self.assertIn(parca, js)

    def test_bilinmeyen_alan_404(self):
        self.assertEqual(panel._mod_yaz("yok", "auto")["kod"], 404)

    def test_uc_noktada_400_404_ve_bildirim_eski_govdesi(self):
        import http.client
        import threading
        sunucu = panel.http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.addCleanup(sunucu.server_close)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        self.addCleanup(sunucu.shutdown)
        port = sunucu.server_address[1]

        def post(yol, govde):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            b = json.dumps(govde)
            c.request("POST", yol, b, {"X-Orkestra": "1", "Content-Type": "application/json", "Content-Length": str(len(b))})
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"{}")

        with mock.patch.dict(os.environ, {"ORKESTRA_HOME": self.ev}):
            os.environ.pop("ORKESTRA_BILDIRIM", None)
            self.assertEqual(post("/api/ayarlar?alan=a1", {"varsayilan_mod": "auto"})[0], 200)
            self.assertEqual(post("/api/ayarlar?alan=a1", {"varsayilan_mod": "full"})[0], 400)
            self.assertEqual(post("/api/ayarlar", {"varsayilan_mod": "auto"})[0], 404)
            self.assertEqual(post("/api/ayarlar?alan=a1", {"bildirim": False})[0], 200)
            self.assertEqual(post("/api/ayarlar?alan=a1", {"x": 1})[0], 400)


if __name__ == "__main__":
    unittest.main()
