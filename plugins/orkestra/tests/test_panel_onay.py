"""panel.py onay uçları: sunucu süreç içinde açılır (panel.calistir/baslat kullanılmaz, panel.json'a dokunulmaz)."""
import http.client
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
FIXTURE = os.path.join(AD, "fixtures", "ruya_20261013_1500.md")
sys.path.insert(0, SCRIPTS)
import ork_lib as L  # noqa: E402
import onay  # noqa: E402
import panel  # noqa: E402


class PanelOnay(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "ruya"))
        shutil.copy(FIXTURE, os.path.join(self.sd, "ruya", "ruya_20261013_1500.md"))
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        yok = os.path.join(self.t.name, "orkestrasiz")
        os.makedirs(yok)
        self.yok = {"id": "alan-y", "ad": "orkestrasiz", "yol": yok, "orkestra": False, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.yok, self.alan])
        self.yama.start()
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()
        self.durum_yolu = panel.DURUM
        self.once = os.path.getmtime(self.durum_yolu) if os.path.exists(self.durum_yolu) else None

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.t.cleanup()
        sonra = os.path.getmtime(self.durum_yolu) if os.path.exists(self.durum_yolu) else None
        self.assertEqual(self.once, sonra, "panel.json değişmemeli")

    def istek(self, yontem, yol, govde=None, baslik=None, ham=None):
        h = {"Host": f"127.0.0.1:{self.port}"}
        if baslik is not None:
            h.update(baslik)
        veri = ham if ham is not None else (json.dumps(govde).encode("utf-8") if govde is not None else None)
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

    def post(self, alan, govde, **kw):
        b = {"X-Orkestra": "1", "Content-Type": "application/json"}
        b.update(kw.pop("baslik", {}))
        return self.istek("POST", f"/onay?alan={alan}", govde, baslik=b, **kw)

    def getj(self, yol):
        k, b = self.istek("GET", yol)
        self.assertEqual(k, 200)
        return json.loads(b)

    # ------------------------------------------------------------ GET
    def test_get_uclar(self):
        o = self.getj("/onaylar.json?alan=alan-x")
        self.assertTrue(o["acik"])
        self.assertEqual(o["alan"], {"id": "alan-x", "ad": "proje", "yol": self.proje})
        self.assertGreater(o["sayac"]["bekliyor"], 0)
        self.assertTrue(o["kayitlar"])
        self.assertTrue(o["perspektif"]["rapor"].endswith("ruya_20261013_1500.md"))
        self.assertIn("uretim", o)
        k = self.getj("/kurallar.json?alan=alan-x")
        self.assertTrue(k["acik"])
        for anahtar in ("etkin", "oneriler", "gecmis", "kaynaklar", "uretim"):
            self.assertIn(anahtar, k)
        s = self.getj("/onay-sayac.json")
        self.assertEqual(list(s), ["alan-x"])
        self.assertIn("bekliyor", s["alan-x"])

    def test_get_geri_dusus_ve_orkestrasiz(self):
        self.assertEqual(self.getj("/onaylar.json?alan=yok")["alan"]["id"], "alan-x")
        o = self.getj("/onaylar.json?alan=alan-y")
        self.assertEqual(o, {"acik": False, "hata": "Bu çalışma alanında orkestra açık değil."})

    def test_perspektif_klasoru_tercih(self):
        os.makedirs(os.path.join(self.sd, "perspektif"))
        yeni = os.path.join(self.sd, "perspektif", "perspektif_20261014_0900.md")
        open(yeni, "w", encoding="utf-8").write("# x\n")
        self.assertEqual(panel._perspektif(self.sd)["rapor"], yeni)

    def test_perspektif_iki_klasorde_en_yeni_damga(self):
        os.makedirs(os.path.join(self.sd, "perspektif"))
        p = os.path.join(self.sd, "perspektif", "perspektif_20261012_0900.md")
        open(p, "w", encoding="utf-8").write("# x\n")
        # sd/ruya/ruya_20261013_1500.md daha yeni damgalı: klasör değil damga belirler (onay.esitle ile aynı seçim).
        self.assertTrue(panel._perspektif(self.sd)["rapor"].endswith("ruya_20261013_1500.md"))
        self.assertEqual(panel._perspektif(self.sd)["rapor"], onay.en_yeni_rapor(self.sd))
        self.assertNotEqual(panel._perspektif(self.sd)["rapor"], p)

    def test_perspektif_modulu_yoksa_null(self):
        with mock.patch.dict(sys.modules, {"perspektif": None}):
            p = panel._perspektif(self.sd)
        self.assertIsNone(p["durum"])
        self.assertTrue(p["rapor"])

    def test_sayfalar_ve_surum(self):
        self.assertEqual(panel.SURUM, "11")
        for yol in ("/onaylar", "/onaylar.html", "/kurallar", "/kurallar.html"):
            k, _ = self.istek("GET", yol)
            self.assertEqual(k, 200)
        k, b = self.istek("GET", "/saglik")
        self.assertEqual(b, b"ok 11")

    # ------------------------------------------------------------ POST güvenliği
    def test_post_basliksiz_403(self):
        k, _ = self.istek("POST", "/onay?alan=alan-x", {"islem": "kural-ekle", "metin": "a"},
                          baslik={"Content-Type": "application/json"})
        self.assertEqual(k, 403)
        self.assertFalse(os.path.exists(os.path.join(self.proje, ".claude", "rules", "orkestra_kurallari.md")))

    def test_post_yabanci_host_403(self):
        k, _ = self.post("alan-x", {"islem": "kural-ekle", "metin": "a"}, baslik={"Host": "evil.example:80"})
        self.assertEqual(k, 403)
        k, _ = self.post("alan-x", {"islem": "kural-ekle", "metin": "a"}, baslik={"Host": "127.0.0.1:1"})
        self.assertEqual(k, 403)
        k, _ = self.post("alan-x", {"islem": "kural-ekle", "metin": "a"}, baslik={"Host": f"localhost:{self.port}"})
        self.assertEqual(k, 200)

    def test_post_buyuk_govde_413(self):
        k, b = self.post("alan-x", None, ham=b"x" * (64 * 1024 + 1))
        self.assertEqual(k, 413)
        self.assertFalse(json.loads(b)["tamam"])

    def test_post_dev_content_length_kisa_govde_413(self):
        # Başlık 50 MB der, gövde kısa: sunucu gövdeyi beklemeden 413 verir ve bağlantıyı kapatır.
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("POST", "/onay?alan=alan-x", skip_host=True)
        for k, v in {"Host": f"127.0.0.1:{self.port}", "X-Orkestra": "1", "Content-Type": "application/json",
                     "Content-Length": str(50 * 1024 * 1024)}.items():
            c.putheader(k, v)
        c.endheaders(b"{}")
        r = c.getresponse()
        b = r.read()
        c.close()
        self.assertEqual(r.status, 413)
        self.assertEqual((r.getheader("Connection") or "").lower(), "close")
        self.assertFalse(json.loads(b)["tamam"])

    def test_post_gecersiz_icerik(self):
        k, _ = self.post("alan-x", {"islem": "karar"}, baslik={"Content-Type": "text/plain"})
        self.assertEqual(k, 400)
        k, _ = self.post("alan-x", None, ham=b"{bozuk")
        self.assertEqual(k, 400)
        k, b = self.post("alan-x", {"islem": "yok"})
        self.assertEqual(k, 400)
        self.assertFalse(json.loads(b)["tamam"])

    def test_post_bilinmeyen_alan_degisiklik_yapmaz(self):
        for alan in ("yok", "alan-y", ""):
            k, b = self.post(alan, {"islem": "kural-ekle", "metin": "yasak kural"})
            self.assertEqual(k, 400)
            self.assertFalse(json.loads(b)["tamam"])
        self.assertFalse(os.path.exists(os.path.join(self.sd, "kurallar", "kurallar.json")))
        self.assertFalse(os.path.exists(os.path.join(self.proje, ".claude", "rules", "orkestra_kurallari.md")))
        self.assertFalse(os.path.exists(os.path.join(self.t.name, "orkestrasiz", ".claude")))

    def test_post_yanlis_tur_400_dosya_yazilmaz(self):
        for g in ({"islem": "kural-ekle", "metin": ["a"]},
                  {"islem": "kural-ekle", "metin": "a", "neden": 5},
                  {"islem": "karar", "id": 1, "sonuc": "onay"},
                  {"islem": "karar", "id": "O-001", "sonuc": "onay", "secim": 3},
                  {"islem": ["x"]}):
            k, b = self.post("alan-x", g)
            self.assertEqual(k, 400, g)
            self.assertFalse(json.loads(b)["tamam"])
        k, b = self.post("alan-x", {"islem": "kural-ekle", "metin": ["a"]})
        self.assertEqual(json.loads(b)["hata"], "metin metin olmalı.")
        self.assertFalse(os.path.exists(os.path.join(self.sd, "kurallar", "kurallar.json")))
        self.assertFalse(os.path.exists(os.path.join(self.proje, ".claude", "rules", "orkestra_kurallari.md")))

    def test_post_beklenmeyen_istisna_500_json(self):
        with mock.patch.object(panel, "_onay_islemi", side_effect=RuntimeError("bozuk")):
            k, b = self.post("alan-x", {"islem": "kural-ekle", "metin": "a"})
        self.assertEqual(k, 500)
        self.assertFalse(json.loads(b)["tamam"])

    def test_perspektif_yalniz_rapor_adlari(self):
        d = os.path.join(self.sd, "ruya")
        for ad in ("ruya_hata_20261020.md", "notlar.md", "zzz.md"):
            open(os.path.join(d, ad), "w", encoding="utf-8").write("x")
        self.assertTrue(panel._perspektif(self.sd)["rapor"].endswith("ruya_20261013_1500.md"))

    # ------------------------------------------------------------ POST akışları
    def test_karar_akisi(self):
        o = self.getj("/onaylar.json?alan=alan-x")
        bekleyen = [k for k in o["kayitlar"] if k["durum"] == "bekliyor"][0]
        k, b = self.post("alan-x", {"islem": "karar", "id": bekleyen["id"], "sonuc": "onay", "not": "tamam"})
        self.assertEqual(k, 200)
        r = json.loads(b)
        self.assertTrue(r["tamam"])
        self.assertEqual(r["kayit"]["durum"], "onaylandi")
        self.assertEqual(r["kayit"]["karar"]["kim"], "panel")
        # önbellek temizlendi: sayaç hemen güncel
        o2 = self.getj("/onaylar.json?alan=alan-x")
        self.assertEqual(o2["sayac"]["bekliyor"], o["sayac"]["bekliyor"] - 1)
        # ikinci karar: Türkçe hata
        k, b = self.post("alan-x", {"islem": "karar", "id": bekleyen["id"], "sonuc": "ret"})
        self.assertEqual(k, 400)
        self.assertIn("bekliyor durumunda değil", json.loads(b)["hata"])

    def _onayli_perspektif(self):
        o = self.getj("/onaylar.json?alan=alan-x")
        ids = [k["id"] for k in o["kayitlar"] if k["durum"] == "bekliyor" and k["tur"] == "perspektif"][:2]
        for i in ids:
            self.assertEqual(self.post("alan-x", {"islem": "karar", "id": i, "sonuc": "onay"})[0], 200)
        return ids

    def test_simdi_uygula_onaylisiz_400(self):
        k, b = self.post("alan-x", {"islem": "simdi-uygula"})
        self.assertEqual(k, 400)
        self.assertIn("Uygulanacak onaylı", json.loads(b)["hata"])

    def test_simdi_uygula_oturumsuz_400_ve_kosu_yok(self):
        self._onayli_perspektif()
        with mock.patch("perspektif.claude_exe", lambda: "x.exe"), mock.patch("perspektif.headless_mumkun", lambda sd, e: False):
            k, b = self.post("alan-x", {"islem": "simdi-uygula"})
        self.assertEqual(k, 400)
        self.assertIn("claude auth login", json.loads(b)["hata"])
        self.assertIsNone(self.getj("/onaylar.json?alan=alan-x")["uygulama"])

    def test_simdi_uygula_baslar_ve_ikinci_istek_reddedilir(self):
        ids = self._onayli_perspektif()
        with mock.patch("perspektif.claude_exe", lambda: "x.exe"), mock.patch("perspektif.headless_mumkun", lambda sd, e: True),                 mock.patch("subprocess.Popen") as popen:
            k, b = self.post("alan-x", {"islem": "simdi-uygula"})
            self.assertEqual(k, 200)
            self.assertEqual(json.loads(b)["kayit"]["idler"], sorted(ids))
            self.assertEqual(popen.call_count, 1)
            k2, b2 = self.post("alan-x", {"islem": "simdi-uygula"})
        self.assertEqual(k2, 400)
        self.assertIn("zaten sürüyor", json.loads(b2)["hata"])
        self.assertEqual(self.getj("/onaylar.json?alan=alan-x")["uygulama"]["idler"], sorted(ids))
        onay._kosu_bitir(self.sd, "tamam")
        self.assertIsNone(onay.uygulama_durumu(self.sd))

    def test_kural_ekle_duzenle_kaldir(self):
        k, b = self.post("alan-x", {"islem": "kural-ekle", "metin": "Testsiz commit yok", "neden": "kalite"})
        self.assertEqual(k, 200)
        kid = json.loads(b)["kayit"]["id"]
        kd = self.getj("/kurallar.json?alan=alan-x")
        self.assertEqual([r["id"] for r in kd["etkin"]], [kid])
        dosya = os.path.join(self.proje, ".claude", "rules", "orkestra_kurallari.md")
        self.assertIn("Testsiz commit yok", open(dosya, encoding="utf-8").read())
        k, _ = self.post("alan-x", {"islem": "kural-duzenle", "id": kid, "metin": "Testsiz commit atma"})
        self.assertEqual(k, 200)
        self.assertIn("Testsiz commit atma", open(dosya, encoding="utf-8").read())
        k, _ = self.post("alan-x", {"islem": "kural-kaldir", "id": kid, "not": "gereksiz"})
        self.assertEqual(k, 200)
        self.assertFalse(os.path.exists(dosya))
        kd = self.getj("/kurallar.json?alan=alan-x")
        self.assertEqual(kd["etkin"], [])
        self.assertEqual([r["id"] for r in kd["gecmis"]], [kid])
        k, b = self.post("alan-x", {"islem": "kural-kaldir", "id": "K-999", "not": "x"})
        self.assertEqual(k, 400)


if __name__ == "__main__":
    unittest.main()
