"""G-136 (F3): panel /teknik sayfası ve /teknik.json API (üç kip, negatifler, statik dosyalar, sözleşme denetimleri)."""
import http.client
import http.server
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(AD)
VARLIK = os.path.join(KOK, "assets")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402
import is_kaydi as IK  # noqa: E402
import panel  # noqa: E402


def oku(ad):
    with open(os.path.join(VARLIK, ad), encoding="utf-8") as f:
        return f.read()


class TeknikPanel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        yok = os.path.join(self.t.name, "orkestrasiz")
        os.makedirs(yok)
        self.yok = {"id": "alan-y", "ad": "o", "yol": yok, "orkestra": False, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.yok, self.alan])
        self.yama.start()
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()
        # iş + üç kart: G-010 yeni (teknik not var), G-002 eski (teknik not yok); olusturma sırası G-002 < G-010 < G-003
        self.is_id = IK.is_ac(self.sd, "001-20261013-PE-1-deneme-is", os.path.join(self.proje, "RNV", "001-20261013-PE-1-deneme-is"))["id"]
        self.kod = os.path.join(self.proje, "modul.py")
        with open(self.kod, "w", encoding="utf-8", newline="\n") as f:
            f.write("import json\nimport requests\n")
        teknik = {"yaklasim": "Yaklaşım metni yirmi karakterden uzun.", "neden_bu_yol": "Neden bu yol metni yirmi karakterden uzun.",
                  "alternatifler": [{"secenek": "A", "neden_elendi": "B"}], "entegrasyon": ["x → y: z"], "riskler": ["risk bir"]}
        self.kart("G-002", "2026-10-16T01:00:00+03:00", baslik="Eski kart", sinif="kod", basamak="T1")
        self.kart("G-010", "2026-10-16T02:00:00+03:00", baslik="Yeni kart", sinif="kod", basamak="T2", teknik=teknik,
                  ciktilar=[self.kod], soru="Çalışıyor mu?", denetimler=[{"sira": 1, "karar": "onay", "gerekce": "K1: tamam"}])
        self.kart("G-003", "2026-10-16T03:00:00+03:00", baslik="Belge kartı", sinif="belge", basamak="T1")
        for g in ("G-002", "G-010", "G-003"):
            IK.is_kart_ekle(self.sd, self.is_id, g)
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"gorev": "G-010", "ajan": "orkestra:isci-t2", "model": "claude-sonnet-5-5", "maliyet_usd": 1.25,
                                "zaman": "2026-10-16T02:30:00Z"}) + "\n")

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.t.cleanup()

    def kart(self, gid, olusturma, **alan):
        k = {"id": gid, "durum": "teslim", "bagimliliklar": [], "olusturma": olusturma, "is": self.is_id, "ciktilar": []}
        k.update(alan)
        d = os.path.join(self.sd, "gorevler")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{gid}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f, ensure_ascii=False)

    def get(self, yol):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", yol)
        r = c.getresponse()
        b = r.read()
        tip = r.getheader("Content-Type")
        c.close()
        return r.status, b, tip

    def getj(self, yol, kod=200):
        k, b, _ = self.get(yol)
        self.assertEqual(k, kod, b[:200])
        return json.loads(b)

    # ------------------------------------------------------------------ K1
    def test_k1_is_listesi(self):
        v = self.getj("/teknik.json?alan=alan-x")
        self.assertTrue(v["acik"])
        self.assertEqual(len(v["isler"]), 1)
        i = v["isler"][0]
        self.assertEqual((i["id"], i["kart_sayisi"]), (self.is_id, 3))
        self.assertEqual(i["usd"], 1.25)
        for a in ("ad", "durum"):
            self.assertIn(a, i)

    def test_k1_is_kartlari_olusturma_sirasi(self):
        v = self.getj(f"/teknik.json?alan=alan-x&is={self.is_id}")
        self.assertEqual([k["id"] for k in v["kartlar"]], ["G-002", "G-010", "G-003"])
        yeni = v["kartlar"][1]
        for a in ("id", "baslik", "sinif", "basamak", "durum", "usd", "sure", "teknik_var", "dosya_sayisi", "kutuphaneler"):
            self.assertIn(a, yeni)
        self.assertEqual(yeni["usd"], 1.25)
        self.assertEqual(yeni["dosya_sayisi"], 1)
        self.assertIn("requests", yeni["kutuphaneler"])
        self.assertIn("modul.py", yeni["dosyalar"])
        self.assertEqual(yeni["denetim"], "onay")

    def test_k1_tek_kart_yedi_blok(self):
        v = self.getj("/teknik.json?alan=alan-x&kart=G-010")
        for b in ("ne", "neden", "nasil", "degisen", "dogrulama", "maliyet_sure", "ogrenilen"):
            self.assertIn(b, v)
        self.assertEqual(v["nasil"]["teknik"]["yaklasim"], "Yaklaşım metni yirmi karakterden uzun.")
        self.assertEqual(v["maliyet_sure"]["toplam_usd"], 1.25)

    def test_k1_negatif(self):
        for yol in ("/teknik.json?alan=yok-alan", "/teknik.json?alan=alan-y",
                    "/teknik.json?alan=alan-x&is=I-999", "/teknik.json?alan=alan-x&kart=G-999",
                    "/teknik.json?alan=alan-x&kart=..%2F..%2Fx", "/teknik.json?alan=alan-x&is=%27x"):
            v = self.getj(yol, 404)
            self.assertFalse(v["acik"], yol)
            self.assertTrue(v["hata"], yol)
            self.assertNotIn("kod", v)

    # ------------------------------------------------------------------ ret kipi (I-143)
    def ret_kartlari(self):
        self.kart("G-020", "2026-10-16T04:00:00+03:00", baslik="Reddedilen kod", sinif="kod", basamak="T2", denetimler=[
            {"sira": 1, "karar": "ret", "neden": "kanit-yok", "kok": "dikkat", "zaman": "2026-10-16T04:10:00+03:00",
             "gerekce": "K1: kanıt yok\n<b>kalın</b> değil", "talimat": "kanıt ekle", "basamak": "T2"},
            {"sira": 2, "karar": "ret", "neden": "bicim", "kok": "dikkat", "zaman": "2026-10-16T04:20:00+03:00",
             "gerekce": "biçim bozuk", "talimat": "", "basamak": "T2"}])
        self.kart("G-021", "2026-10-16T05:00:00+03:00", baslik="Reddedilen belge", sinif="belge", basamak="T1", denetimler=[
            {"sira": 1, "karar": "ret", "neden": "uydurma", "zaman": "2026-10-16T05:10:00+03:00", "gerekce": "kodsuz ret"}])
        self.kart("G-022", "2026-10-16T06:00:00+03:00", baslik="İptal kart", sinif="kod", basamak="T2", durum="iptal", denetimler=[
            {"sira": 1, "karar": "ret", "neden": "bicim", "zaman": "2026-10-16T06:10:00+03:00", "gerekce": "iptal kartın reti"}])
        for g in ("G-020", "G-021", "G-022"):
            IK.is_kart_ekle(self.sd, self.is_id, g)

    def test_ret_kipi_liste_gerekce_ve_siralama(self):
        self.ret_kartlari()
        v = self.getj("/teknik.json?alan=alan-x&ret=1")
        r = v["ret"]
        self.assertEqual((r["toplam"], r["gosterilen"]), (3, 3))   # iptal kartın reti hariç
        self.assertEqual([x["kart"] for x in r["kayitlar"]], ["G-021", "G-020", "G-020"])   # en yeni önce
        ilk = r["kayitlar"][2]
        self.assertEqual((ilk["neden"], ilk["kok"], ilk["sira"]), ("kanit-yok", "dikkat", 1))
        self.assertEqual(ilk["gerekce"], "K1: kanıt yok\n<b>kalın</b> değil")
        self.assertEqual(ilk["talimat"], "kanıt ekle")
        self.assertEqual(r["kayitlar"][0]["neden"], "siniflanmamis")
        self.assertTrue(ilk["is_ad"])

    def test_ret_kipi_toplam_ders_ile_esit(self):
        import analitik
        self.ret_kartlari()
        r = self.getj("/teknik.json?alan=alan-x&ret=1")["ret"]
        self.assertEqual(r["toplam"], sum(n["ret"] for n in analitik._ders(L.kartlar(self.sd), [])["nedenler"]))

    def test_ret_kipi_suzgecler(self):
        self.ret_kartlari()
        f = lambda q: self.getj("/teknik.json?alan=alan-x&ret=1" + q)["ret"]   # noqa: E731
        self.assertEqual([x["neden"] for x in f("&neden=bicim")["kayitlar"]], ["bicim"])
        self.assertEqual(f("&sinif=belge")["toplam"], 1)
        self.assertEqual(f("&sinif=kod&basamak=T2")["toplam"], 2)
        self.assertEqual(f("&kok=siniflanmamis")["toplam"], 1)
        self.assertEqual(f("&neden=siniflanmamis")["toplam"], 1)
        self.assertEqual(f("&neden=bicim")["suzgec"], {"neden": "bicim"})

    def test_ret_kipi_basamaksiz_kart_tire_suzgeci(self):   # kart yükleyici eksik basamağa "-" yazar; Verim satırı aynı değeri bağlar
        self.ret_kartlari()
        self.kart("G-031", "2026-10-16T08:00:00+03:00", baslik="Basamaksız", sinif="kod", denetimler=[
            {"sira": 1, "karar": "ret", "neden": "bicim", "zaman": "2026-10-16T08:10:00+03:00", "gerekce": "basamak yok"}])
        IK.is_kart_ekle(self.sd, self.is_id, "G-031")
        v = self.getj("/teknik.json?alan=alan-x&ret=1&sinif=kod&basamak=-")["ret"]
        self.assertEqual([x["kart"] for x in v["kayitlar"]], ["G-031"])
        self.assertEqual(v["toplam"], 1)

    def test_ret_kipi_gecersiz_suzgec_400(self):
        self.ret_kartlari()
        for q in ("&neden=uydurma", "&kok=x", "&sinif=" + "a" * 61, "&sinif=olmayan", "&basamak=T9"):
            v = self.getj("/teknik.json?alan=alan-x&ret=1" + q, 400)
            self.assertFalse(v["acik"], q)
            self.assertTrue(v["hata"], q)

    def test_ret_kipi_sinir_ve_ret_olmadan_eski_kip(self):
        import panel as P
        self.ret_kartlari()
        with mock.patch.object(P, "_RET_SINIR", 2):
            r = self.getj("/teknik.json?alan=alan-x&ret=1")["ret"]
        self.assertEqual((r["toplam"], r["gosterilen"], len(r["kayitlar"])), (3, 2, 2))
        self.assertIn("isler", self.getj("/teknik.json?alan=alan-x"))   # ret parametresi yok: iş listesi
        self.assertIn("isler", self.getj("/teknik.json?alan=alan-x&ret=0"))

    def test_ret_kipi_arayuz_sozlesmesi(self):
        js, html, verim = oku("teknik.js"), oku("teknik.html"), oku("verim.js")
        self.assertIn('id="tRetGiris"', html)
        for parca in ("&ret=1", "t-ret-giris", "t-cip", "t-git", "gerekceHtml"):
            self.assertIn(parca, js, parca)
        self.assertIn("white-space: pre-wrap", oku("teknik.css"))
        self.assertIn("/teknik?", verim)       # ret hücreleri Teknik sayfasına gider; yeni sayfa yok
        self.assertEqual(len([n for n in os.listdir(VARLIK) if n.startswith("ret") and n.endswith(".html")]), 0)

    def test_ret_kipi_sir_maskelenir(self):
        self.kart("G-030", "2026-10-16T07:00:00+03:00", baslik="Sırlı", sinif="kod", basamak="T2", denetimler=[
            {"sira": 1, "karar": "ret", "neden": "bicim", "zaman": "2026-10-16T07:10:00+03:00",
             "gerekce": "anahtar sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 sızdı"}])
        IK.is_kart_ekle(self.sd, self.is_id, "G-030")
        g = self.getj("/teknik.json?alan=alan-x&ret=1")["ret"]["kayitlar"][0]["gerekce"]
        self.assertNotIn("sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", g)

    # ------------------------------------------------------------------ K2
    def test_k2_sayfa_ve_statik_200(self):
        for yol, tip in (("/teknik", "text/html"), ("/teknik.html", "text/html"),
                         ("/teknik.js", "application/javascript"), ("/teknik.css", "text/css")):
            k, b, t = self.get(yol)
            self.assertEqual(k, 200, yol)
            self.assertTrue(t.startswith(tip), (yol, t))
            self.assertGreater(len(b), 100, yol)

    def test_k2_surum_ve_sekme(self):
        self.assertEqual(panel.SURUM, "19")
        k, b, _ = self.get("/saglik")
        self.assertEqual(b.decode(), "ok 19")
        # Teknik sayfa menüden gizli (16.10.2026); adresle hâlâ açılır.
        self.assertNotIn("'/teknik'", oku("ortak.js"))

    # ------------------------------------------------------------------ K3
    def test_k3_sayfa_kartlar_ve_yedi_blok_adi(self):
        js = oku("teknik.js")
        for ad in ("Ne", "Neden", "Nasıl", "Değişen", "Doğrulama", "Maliyet ve süre", "Öğrenilen"):
            self.assertIn(f"blok('{ad}'", js)
        self.assertIn("/teknik.json?alan=", js)
        self.assertIn("&is=", js)
        self.assertIn("&kart=", js)
        h = oku("teknik.html")
        for kimlik in ("tIsler", "tZaman", "tAra"):
            self.assertIn(f'id="{kimlik}"', h)

    # ------------------------------------------------------------------ K4
    def test_k4_filtre_arama_sozlesmesi(self):
        js = oku("teknik.js")
        self.assertIn("Eşleşen kart yok", js)
        self.assertIn("k.dosyalar", js)
        self.assertIn("k.kutuphaneler", js)
        for ad in ("fSinif", "fBasamak", "fDenetim"):
            self.assertIn(ad, oku("teknik.html"))
        v = self.getj(f"/teknik.json?alan=alan-x&is={self.is_id}")
        a = "requests"
        bulunan = [k["id"] for k in v["kartlar"] if any(a in x.lower() for x in k["dosyalar"] + k["kutuphaneler"])]
        self.assertEqual(bulunan, ["G-010"])
        self.assertEqual([k["id"] for k in v["kartlar"] if any("yokboyle" in x for x in k["dosyalar"] + k["kutuphaneler"])], [])

    # ------------------------------------------------------------------ K5
    def test_k5_eski_kart_teknik_yok(self):
        v = self.getj(f"/teknik.json?alan=alan-x&is={self.is_id}")
        eski = v["kartlar"][0]
        self.assertFalse(eski["teknik_var"])
        self.assertEqual((eski["dosya_sayisi"], eski["kutuphaneler"]), (0, []))
        d = self.getj("/teknik.json?alan=alan-x&kart=G-002")
        self.assertIsNone(d["nasil"]["teknik"])
        self.assertIn("nasil", d["eksik"])
        self.assertIn("teknik not yok (eski kart)", oku("teknik.js"))

    # ------------------------------------------------------------------ K6
    def test_k6_stil_yalniz_degisken(self):
        css = oku("teknik.css")
        govde = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertNotRegex(govde, r"#[0-9a-fA-F]{3,8}\b")
        self.assertNotRegex(govde, r"\brgba?\(|\bhsla?\(")
        self.assertIn("var(--", govde)
        self.assertIn("@media (max-width: 900px)", govde)
        self.assertRegex(govde, r"grid-template-columns:\s*minmax\(0, 1fr\)")
        self.assertIn("overflow-wrap: anywhere", govde)

    # ------------------------------------------------------------------ K7
    def test_k7_isler_baglantisi_ve_secili_is(self):
        # İş başlığındaki "Teknik detay →" bağlantısı gizli (16.10.2026).
        self.assertNotIn("Teknik detay →", oku("isler.js"))
        self.assertIn("searchParams.get('is')", oku("teknik.js"))


if __name__ == "__main__":
    unittest.main()
