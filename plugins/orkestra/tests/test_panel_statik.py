"""Panel sayfaları bölündü (G-099): tekrarlı JS ortak.js'te, sayfa başına ayrı .js/.css.

Kriterler:
  K1  ciz, yerlestir, bayatCiz tanımları assets altında yalnız ortak.js'te, birer kez.
  K2  Her .html dosyasında satır içi <script> gövdesi <= 2 KB.
  K3  panel.py yeni .js/.css dosyalarını doğru Content-Type ile sunar; listede olmayan yol 404.
  K4  Panel test portunda (--test) başlar; her sayfa ve bağlı tüm .js/.css HTTP 200 verir.
"""
import glob
import http.client
import http.server
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(AD)
SCRIPTS = os.path.join(KOK, "scripts")
ASSETS = os.path.join(KOK, "assets")
sys.path.insert(0, SCRIPTS)
import panel  # noqa: E402

ORTAK_ADLAR = ("ciz", "yerlestir", "bayatCiz")
SATIR_ICI = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
BAGLI = re.compile(r'(?:<script[^>]*\bsrc|<link[^>]*\bhref)="([^"]+\.(?:js|css))"')


def oku(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read()


def tanim_say(ad, metin):
    """Tanım biçimleri: function ad(, const|let|var ad =, ad = (atama, O.ad = ). Çağrı ve kaçınma sayılmaz."""
    kaliplar = (rf"\bfunction\s+{ad}\s*\(", rf"\b(?:const|let|var)\s+{ad}\s*=", rf"\bO\.{ad}\s*=")
    return sum(len(re.findall(k, metin)) for k in kaliplar)


UYGULAMA = "app.html"  # panel v2 tek sayfa uygulaması: ortak.js'i kullanmaz, kendi app.js/app.css'i vardır


def html_dosyalari(uygulama_dahil=False):
    """Klasik sayfalar (ortak.js tabanlı); uygulama_dahil=True ile panel v2 de."""
    tum = sorted(glob.glob(os.path.join(ASSETS, "*.html")))
    return tum if uygulama_dahil else [h for h in tum if os.path.basename(h) != UYGULAMA]


def js_css_dosyalari():
    return sorted(glob.glob(os.path.join(ASSETS, "*.js")) + glob.glob(os.path.join(ASSETS, "*.css")))


class TanimlarYalnizOrtakta(unittest.TestCase):
    def test_sayfa_betikleri_var(self):
        sayfalar = [os.path.basename(h)[:-5] for h in html_dosyalari()]
        self.assertGreaterEqual(len(sayfalar), 5)
        for s in sayfalar:
            self.assertTrue(os.path.isfile(os.path.join(ASSETS, s + ".js")), s + ".js yok")

    def test_ortak_adlar_ortak_js_te_birer_kez(self):
        for ad in ORTAK_ADLAR:
            toplam = {}
            for yol in glob.glob(os.path.join(ASSETS, "*.js")) + glob.glob(os.path.join(ASSETS, "*.html")):
                n = tanim_say(ad, oku(yol))
                if n:
                    toplam[os.path.basename(yol)] = n
            # ortak.js'te function + O.ad ataması: aynı tanımın iki yüzü (iki kez geçer), başka dosyada hiç
            self.assertEqual(set(toplam), {"ortak.js"}, f"{ad} tanımları: {toplam}")
            self.assertEqual(len(re.findall(rf"\bfunction\s+{ad}\s*\(", oku(os.path.join(ASSETS, "ortak.js")))), 1, ad)
            self.assertEqual(len(re.findall(rf"\bO\.{ad}\s*=", oku(os.path.join(ASSETS, "ortak.js")))), 1, ad)

    def test_sayfalar_ortak_olani_kullanir(self):
        for s in ("simdi", "verim", "maliyet"):
            js = oku(os.path.join(ASSETS, s + ".js"))
            self.assertRegex(js, r"const \{[^}]*\bciz\b[^}]*\} = O;", s)
            self.assertRegex(js, r"const \{[^}]*\bbayatCiz\b[^}]*\} = O;", s)
        for s in ("isler", "kurallar", "onaylar", "etki", "maliyet", "simdi", "verim"):
            self.assertRegex(oku(os.path.join(ASSETS, s + ".js")), r"const \{[^}]*\byerlestir\b[^}]*\} = O;", s)

    def test_satir_ici_betik_kucuk(self):
        for yol in html_dosyalari():
            for govde in SATIR_ICI.findall(oku(yol)):
                self.assertLessEqual(len(govde.encode("utf-8")), 2048, os.path.basename(yol))

    def test_her_sayfa_kendi_betigini_baglar(self):
        for yol in html_dosyalari():
            ad = os.path.basename(yol)[:-5]
            h = oku(yol)
            self.assertIn('<script src="ortak.js"></script>', h, ad)
            self.assertIn(f'<script src="{ad}.js"></script>', h, ad)
            self.assertLess(h.index("ortak.js"), h.index(f"{ad}.js"), ad)  # ortak önce yüklenir

    def test_bagli_dosyalar_var_ve_sunulur(self):
        for yol in html_dosyalari(uygulama_dahil=True):
            for hedef in BAGLI.findall(oku(yol)):
                self.assertTrue(os.path.isfile(os.path.join(ASSETS, hedef)), hedef)
                self.assertIn("/" + hedef, panel.STATIK, hedef)


class PanelV2(unittest.TestCase):
    """Panel v2 (I-049): / adresinde tek sayfa uygulaması; klasik sayfalar yerinde kalır."""

    def test_kok_uygulamaya_simdi_klasige(self):
        self.assertEqual(panel.SAYFALAR["/"], UYGULAMA)
        self.assertEqual(panel.SAYFALAR["/index.html"], UYGULAMA)
        self.assertEqual(panel.SAYFALAR["/simdi"], "simdi.html")
        for ad in ("isler", "maliyet", "onaylar", "yapilacaklar", "teknik"):
            self.assertEqual(panel.SAYFALAR["/" + ad], ad + ".html" if ad != "onaylar" else "onaylar.html")

    def test_uygulama_dosyalari_ve_yollari(self):
        h = oku(os.path.join(ASSETS, UYGULAMA))
        self.assertIn('<script src="app.js"></script>', h)
        self.assertIn('href="app.css"', h)
        js = oku(os.path.join(ASSETS, "app.js"))
        for rota in ("#/gelen", "#/isler", "#/kosular", "#/maliyet", "#/kurallar", "#/kart/", "#/is/"):
            self.assertIn(rota, js, rota)
        self.assertIn("/akis?alan=", js)
        self.assertIn("'X-Orkestra': '1'", js)

    def test_kart_sohbeti_acar(self):
        """Gelen kutusu kartı ve kart ayrıntısı, kartı başlatan sohbeti açar; "İzi aç" koşu izine gider."""
        js = oku(os.path.join(ASSETS, "app.js"))
        self.assertIn("async function sohbetAc(", js)
        self.assertIn("gonder('/ac?oturum='", js)  # sunucu yolu: gonder() X-Orkestra başlığını ekler
        self.assertIn("data-eylem=\"sohbet-ac\" data-oturum=\"${k.oturum}\"", js)  # Gelen kutusu kartı
        self.assertIn("data-eylem=\"sohbet-ac\" data-oturum=\"${bilgi.oturum}\"", js)  # kart ayrıntısı
        self.assertIn("ey === 'sohbet-ac'", js)
        self.assertIn("article[data-oturum]", js)  # kart gövdesine tıklama
        self.assertIn("href=\"#/kart/${enc(k.id)}\"", js)  # İzi aç korunur

    def test_tasarim_belirtecleri_iki_tema(self):
        c = oku(os.path.join(ASSETS, "app.css"))
        self.assertIn("prefers-color-scheme: dark", c)
        self.assertIn('[data-tema="koyu"]', c)
        self.assertIn('[data-tema="acik"]', c)


class StatikSunum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        cls.port = cls.sunucu.server_address[1]
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()

    def al(self, yol):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", yol)
        r = c.getresponse()
        return r.status, r.getheader("Content-Type"), r.read()

    def test_js_ve_css_dogru_icerik_turuyle(self):
        for yol in js_css_dosyalari():
            ad = os.path.basename(yol)
            durum, tur, govde = self.al("/" + ad)
            self.assertEqual(durum, 200, ad)
            beklenen = "application/javascript" if ad.endswith(".js") else "text/css"
            self.assertTrue(tur.startswith(beklenen + ";"), f"{ad}: {tur}")
            self.assertEqual(govde, open(yol, "rb").read(), ad)

    def test_listede_olmayan_yol_404(self):
        for yol in ("/yok.js", "/yok.css", "/panel.py", "/ortak.js.bak", "/isler.js/x", "/../scripts/panel.py",
                    "/%2e%2e/scripts/panel.py", "/assets/isler.js", "/isler.JS"):
            durum, _, _ = self.al(yol)
            self.assertEqual(durum, 404, yol)

    def test_kok_uygulamayi_sunar(self):
        durum, tur, govde = self.al("/")
        self.assertEqual(durum, 200)
        self.assertIn(b'src="app.js"', govde)

    def test_akis_bilinmeyen_alan_400(self):
        durum, tur, _ = self.al("/akis?alan=olmayan-alan-xyz")
        self.assertEqual(durum, 400)
        self.assertTrue(tur.startswith("application/json"))

    def test_statik_listesi_yalniz_beklenen_uzantilar(self):
        for yol, (dosya, tur) in panel.STATIK.items():
            self.assertEqual(yol, "/" + dosya)
            self.assertRegex(dosya, r"^[a-z]+\.(js|css|png)$")
            self.assertTrue(os.path.isfile(os.path.join(ASSETS, dosya)), dosya)


class TestPortundaTumSayfalar(unittest.TestCase):
    def test_her_sayfa_ve_bagli_dosya_200(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        with tempfile.TemporaryDirectory() as ev:
            env = dict(os.environ, USERPROFILE=ev, HOME=ev)
            p = subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "panel.py"), "_kos", str(port), "--test"],
                                 env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                son = time.time() + 20
                ok = False
                while time.time() < son and p.poll() is None:
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=1) as r:
                            ok = r.status == 200
                            break
                    except Exception:
                        time.sleep(0.1)
                self.assertTrue(ok, "test sunucusu ayağa kalkmadı")
                sayfa_yollari = sorted({y for y in panel.SAYFALAR if not y.endswith(".html")})
                self.assertGreaterEqual(len(sayfa_yollari), 8)
                gorulen = set()
                for yol in sayfa_yollari:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}{yol}", timeout=10) as r:
                        self.assertEqual(r.status, 200, yol)
                        html = r.read().decode("utf-8")
                    self.assertNotIn("hazırlanıyor", html.lower(), yol)
                    for hedef in BAGLI.findall(html):
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/{hedef}", timeout=10) as r2:
                            self.assertEqual(r2.status, 200, hedef)
                            self.assertGreater(len(r2.read()), 0, hedef)
                        gorulen.add(hedef)
                # her sayfa kendi betiğini bağladığı için sayfa .js dosyaları da çekilmiş olmalı
                for ad in ("isler.js", "maliyet.js", "verim.js", "simdi.js", "ortak.js", "ortak.css", "isler.css"):
                    self.assertIn(ad, gorulen)
            finally:
                p.kill()
                p.wait()


if __name__ == "__main__":
    unittest.main()
