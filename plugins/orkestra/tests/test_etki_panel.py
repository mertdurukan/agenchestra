"""G-072 (E4): panel Etki sekmesi. /api/etki şeması, /etki sayfası, gezinti, grafik içeriği, doğru karar oranı.

Sunucu süreç içinde açılır (test_panel_onay.py ile aynı kalıp). Veri, plan.md veri modeline göre
sd/onaylar/O-nnn.json dosyalarına yazılır; /api/etki'nin kayıt şeması bu testte sabitlenir:
  {"acik", "alan", "ozet": {"dogru_karar_orani", "dogru", "yanlis", "kapali"}, "kayitlar": [kayıt], "uretim"}
  kayıt: id, olculebilir, uygulama_tarihi, gun, taban{deger,ornek}, birikim{deger,ornek}, gidisat,
         ayni_gidisat_gun, soru_bekliyor, izleme_durum, karar, seri[gün satırı], diger_uygulamalar[{id,tarih}]
"""
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
SCRIPTS = os.path.join(KOK, "scripts")
VARLIK = os.path.join(KOK, "assets")
sys.path.insert(0, SCRIPTS)
import ork_lib as L  # noqa: E402
import panel  # noqa: E402


def oku(ad):
    """Sayfa (.html) için HTML + ona bağlı sayfa .js/.css dosyaları (ortak.* hariç) birlikte döner."""
    with open(os.path.join(VARLIK, ad), encoding="utf-8") as f:
        h = f.read()
    if ad.endswith(".html"):
        for yol in re.findall(r'(?:src|href)="([\w-]+\.(?:js|css))"', h):
            if not yol.startswith("ortak."):
                with open(os.path.join(VARLIK, yol), encoding="utf-8") as g:
                    h += "\n" + g.read()
    return h


def _gun(n, tarih, gd, go, bd, bo, fark, gid):
    return {"gun": n, "tarih": tarih, "gunluk_deger": gd, "gunluk_ornek": go,
            "birikim_deger": bd, "birikim_ornek": bo, "fark_goreli": fark, "gidisat": gid}


def _kayit(oid, tarih, gunluk, durum="suruyor", karar=None, son="iyi", ayni=1, vaat=True, kapanis=None):
    k = {"id": oid, "tur": "oneri", "durum": "uygulandi", "baslik": f"Öneri {oid}",
         "olusturma": f"{tarih}T09:00:00+03:00", "guncelleme": f"{tarih}T10:00:00+03:00"}
    if vaat:
        k["vaat"] = {"metin": "Ret oranı azalır", "olculebilir": True, "metrik": "kpi:ret_orani",
                     "yon": "azalmali", "esik": {"goreli": 0.10, "min_ornek": 20}, "kapsam": "genel"}
        k["etki"] = {"taban": {"zaman": f"{tarih}T08:00:00+03:00", "deger": 0.37, "ornek": 38},
                     "uygulama_dogrulama": {"gecti": True, "kanit": "satır yok"},
                     "uygulama_tarihi": tarih, "gunluk": gunluk,
                     "izleme": {"durum": durum, "baslangic": tarih, "kapanis": kapanis,
                                "son_gidisat": son, "ayni_gidisat_gun": ayni},
                     "karar": karar}
    else:
        k["vaat"] = {"metin": "", "olculebilir": False}
        k["etki"] = {"taban": None, "uygulama_tarihi": tarih, "gunluk": [],
                     "izleme": {"durum": "olculemez", "baslangic": tarih, "kapanis": None,
                                "son_gidisat": "olculemez", "ayni_gidisat_gun": 0},
                     "karar": None}
    return k


class EtkiPanel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "onaylar"))
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        yok = os.path.join(self.t.name, "orkestrasiz")
        os.makedirs(yok)
        self.yok = {"id": "alan-y", "ad": "orkestrasiz", "yol": yok, "orkestra": False, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.yok, self.alan])
        self.yama.start()
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.t.cleanup()

    def yaz(self, k):
        with open(os.path.join(self.sd, "onaylar", k["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False)

    def al(self, yol):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("GET", yol, skip_host=True)
        c.putheader("Host", f"127.0.0.1:{self.port}")
        c.endheaders()
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def api(self, alan="alan-x"):
        k, b = self.al(f"/api/etki?alan={alan}")
        self.assertEqual(k, 200)
        return json.loads(b)

    # ---------------------------------------------------------- kriter 1: şema
    def test_bos_veri(self):
        v = self.api()
        self.assertTrue(v["acik"])
        self.assertEqual(v["kayitlar"], [])
        self.assertEqual(v["ozet"]["kapali"], 0)
        self.assertIsNone(v["ozet"]["dogru_karar_orani"])
        self.assertIn("uretim", v)
        self.assertEqual(v["alan"]["id"], "alan-x")

    def test_orkestrasiz_alan(self):
        v = self.api("alan-y")
        self.assertEqual(v, {"acik": False, "hata": "Bu çalışma alanında orkestra açık değil."})

    def test_kayit_semasi_ve_seri(self):
        gunluk = [_gun(1, "2026-10-15", 0.33, 11, 0.33, 11, -0.11, "yetersiz-veri"),
                  _gun(2, "2026-10-16", 0.29, 14, 0.31, 25, -0.16, "iyi")]
        self.yaz(_kayit("O-001", "2026-10-15", gunluk, ayni=1))
        v = self.api()
        self.assertEqual(len(v["kayitlar"]), 1)
        k = v["kayitlar"][0]
        for anahtar in ("id", "olculebilir", "uygulama_tarihi", "gun", "taban", "birikim", "gidisat",
                        "ayni_gidisat_gun", "soru_bekliyor", "izleme_durum", "karar", "seri", "diger_uygulamalar"):
            self.assertIn(anahtar, k)
        self.assertEqual(k["id"], "O-001")
        self.assertTrue(k["olculebilir"])
        self.assertEqual(k["uygulama_tarihi"], "2026-10-15")
        self.assertEqual(k["gun"], 2)
        self.assertEqual(k["taban"]["deger"], 0.37)
        self.assertEqual(k["taban"]["ornek"], 38)
        self.assertEqual(k["birikim"]["deger"], 0.31)
        self.assertEqual(k["birikim"]["ornek"], 25)
        self.assertEqual(k["gidisat"], "iyi")
        self.assertFalse(k["soru_bekliyor"])
        self.assertEqual(k["izleme_durum"], "suruyor")
        self.assertIsNone(k["karar"])
        self.assertEqual(len(k["seri"]), 2)
        for s, g in zip(k["seri"], gunluk):
            for a in ("gun", "tarih", "gunluk_deger", "gunluk_ornek", "birikim_deger", "birikim_ornek", "gidisat"):
                self.assertEqual(s[a], g[a])
        self.assertEqual(k["diger_uygulamalar"], [])

    def test_olculemez_kayit(self):
        self.yaz(_kayit("O-002", "2026-10-15", [], vaat=False))
        k = self.api()["kayitlar"][0]
        self.assertFalse(k["olculebilir"])
        self.assertEqual(k["gidisat"], "olculemez")
        self.assertEqual(k["seri"], [])
        self.assertFalse(k["soru_bekliyor"])
        self.assertIsNone(k["taban"])

    def test_uygulanmamis_kayit_listede_degil(self):
        k = _kayit("O-003", "2026-10-15", [])
        k["durum"] = "bekliyor"
        k.pop("etki")
        self.yaz(k)
        self.assertEqual(self.api()["kayitlar"], [])

    def test_ayni_donemde_baska_uygulama_isareti(self):
        gunluk = [_gun(1, "2026-10-15", 0.3, 20, 0.3, 20, -0.19, "iyi"),
                  _gun(2, "2026-10-16", 0.3, 20, 0.3, 40, -0.19, "iyi")]
        self.yaz(_kayit("O-004", "2026-10-15", gunluk))
        self.yaz(_kayit("O-005", "2026-10-16", [_gun(1, "2026-10-16", 0.3, 20, 0.3, 20, -0.19, "iyi")]))
        kayitlar = {k["id"]: k for k in self.api()["kayitlar"]}
        d4 = kayitlar["O-004"]["diger_uygulamalar"]
        self.assertEqual([d["id"] for d in d4], ["O-005"])
        self.assertEqual(d4[0]["tarih"], "2026-10-16")
        self.assertEqual([d["id"] for d in kayitlar["O-005"]["diger_uygulamalar"]], ["O-004"])

    # ---------------------------------------------------------- soru (3 gün üst üste kötü)
    def test_uc_gun_kotu_soru_bekliyor(self):
        gunluk = [_gun(i, f"2026-10-{14 + i}", 0.45, 25, 0.45, 25 * i, 0.22, "kotu") for i in (1, 2, 3)]
        self.yaz(_kayit("O-006", "2026-10-15", gunluk, son="kotu", ayni=3))
        k = self.api()["kayitlar"][0]
        self.assertEqual(k["gidisat"], "kotu")
        self.assertEqual(k["ayni_gidisat_gun"], 3)
        self.assertTrue(k["soru_bekliyor"])

    def test_iki_gun_kotu_soru_yok(self):
        gunluk = [_gun(i, f"2026-10-{14 + i}", 0.45, 25, 0.45, 25 * i, 0.22, "kotu") for i in (1, 2)]
        self.yaz(_kayit("O-007", "2026-10-15", gunluk, son="kotu", ayni=2))
        self.assertFalse(self.api()["kayitlar"][0]["soru_bekliyor"])

    def test_kapali_izlemede_soru_yok(self):
        gunluk = [_gun(i, f"2026-10-{14 + i}", 0.45, 25, 0.45, 25 * i, 0.22, "kotu") for i in (1, 2, 3)]
        self.yaz(_kayit("O-008", "2026-10-15", gunluk, durum="kapandi", son="kotu", ayni=3, kapanis="2026-10-18",
                        karar={"sonuc": "yanlis-karar", "not": "", "zaman": "2026-10-18T10:00:00+03:00"}))
        k = self.api()["kayitlar"][0]
        self.assertFalse(k["soru_bekliyor"])
        self.assertEqual(k["karar"]["sonuc"], "yanlis-karar")

    # ---------------------------------------------------------- kriter 4: doğru karar oranı
    def test_oran_yalniz_kapatilmislar(self):
        g = [_gun(1, "2026-10-15", 0.3, 20, 0.3, 20, -0.19, "iyi")]

        def kapat(s):
            return {"sonuc": s, "not": "", "zaman": "2026-10-18T10:00:00+03:00"}
        self.yaz(_kayit("O-010", "2026-10-15", g, durum="kapandi", karar=kapat("dogru-karar"), kapanis="2026-10-18"))
        self.yaz(_kayit("O-011", "2026-10-15", g, durum="kapandi", karar=kapat("yanlis-karar"), kapanis="2026-10-18"))
        # kapatılmamış: iyi gidiyor ama sayılmamalı
        self.yaz(_kayit("O-012", "2026-10-15", g))
        self.yaz(_kayit("O-013", "2026-10-15", g))
        o = self.api()["ozet"]
        self.assertEqual(o["kapali"], 2)
        self.assertEqual(o["dogru"], 1)
        self.assertEqual(o["yanlis"], 1)
        self.assertAlmostEqual(o["dogru_karar_orani"], 0.5)

    def test_oran_kapali_yoksa_bos(self):
        g = [_gun(1, "2026-10-15", 0.3, 20, 0.3, 20, -0.19, "iyi")]
        for i in range(20, 23):
            self.yaz(_kayit(f"O-0{i}", "2026-10-15", g))
        o = self.api()["ozet"]
        self.assertEqual(o["kapali"], 0)
        self.assertIsNone(o["dogru_karar_orani"])

    def test_oran_tum_kapalilar_dogru(self):
        g = [_gun(1, "2026-10-15", 0.3, 20, 0.3, 20, -0.19, "iyi")]
        self.yaz(_kayit("O-030", "2026-10-15", g, durum="kapandi", kapanis="2026-10-17",
                        karar={"sonuc": "dogru-karar", "not": "", "zaman": "2026-10-17T10:00:00+03:00"}))
        self.assertAlmostEqual(self.api()["ozet"]["dogru_karar_orani"], 1.0)

    # ---------------------------------------------------------- kriter 2: sayfa ve gezinti
    def test_sayfa_yollari(self):
        for yol in ("/etki", "/etki.html"):
            k, b = self.al(yol)
            self.assertEqual(k, 200)
            self.assertIn("Orkestra · Onaylar, etki ve kurallar", b.decode("utf-8"))

    def test_sayfalar_tablosu(self):
        self.assertEqual(panel.SAYFALAR["/etki"], "onaylar.html")
        self.assertEqual(panel.SAYFALAR["/etki.html"], "onaylar.html")

    def test_gezinti_sekmesi(self):
        js = oku("ortak.js")
        m = re.search(r"const SEKMELER = \[(.*?)\];", js, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("'/etki'", m.group(1))  # Etki ayrı düğme değil; Onaylar sayfasında
        self.assertNotIn("'/kurallar'", m.group(1))
        self.assertNotIn("'/verim'", m.group(1))
        for s in ("['onaylar', 'Onaylar, etki ve kurallar', '/onaylar']", "['maliyet', 'Maliyet ve verim', '/maliyet']"):
            self.assertIn(s, m.group(1))

    def test_onaylar_sayfasi_etkiyi_icerir(self):
        h = oku("onaylar.html")
        self.assertIn('id="eListe"', h)
        self.assertIn("/api/etki", h)

    # ---------------------------------------------------------- kriter 3: grafik içeriği
    def test_etki_sayfasi_yapisi(self):
        h = oku("onaylar.html")
        self.assertIn("<title>Orkestra · Onaylar, etki ve kurallar</title>", h)
        self.assertIn("/api/etki", h)
        self.assertIn('href="ortak.css"', h)
        # dış kütüphane / ağ kaynağı yok
        self.assertNotRegex(h, r'(src|href)="https?://')
        self.assertNotRegex(h, r"@import|cdn\.")

    def test_grafik_serileri(self):
        h = oku("onaylar.html")
        self.assertIn("svg", h.lower())
        # taban çizgisi, günlük ve birikim serileri veri alanlarından çizilir
        for alan in ("taban", "gunluk_deger", "birikim_deger", "uygulama_tarihi", "diger_uygulamalar",
                     "gunluk_ornek", "birikim_ornek"):
            self.assertIn(alan, h)
        self.assertRegex(h, r"polyline|<path")
        self.assertRegex(h, r"createElementNS|<svg")
        # üç çizgi ve uygulama günü işareti ayrı adla ayırt edilir
        for ad in ("taban", "gunluk", "birikim", "uygulama"):
            self.assertRegex(h, rf"(?:cizgi|isaret|seri)[-_]{ad}\b")
        self.assertIn("stroke-dasharray", h)  # dondurulmuş taban kesikli ayırt edilir

    def test_liste_alanlari(self):
        h = oku("onaylar.html")
        for alan in ("uygulama_tarihi", "gun", "gidisat", "ayni_gidisat_gun", "soru_bekliyor", "dogru_karar_orani"):
            self.assertIn(alan, h)
        for rozet in ("iyi", "kotu", "etkisiz", "yetersiz-veri", "olculemez"):
            self.assertIn(rozet, h)

    def test_panel_ucu_tanimli(self):
        with open(os.path.join(SCRIPTS, "panel.py"), encoding="utf-8") as f:
            kaynak = f.read()
        self.assertIn("/api/etki", kaynak)
        self.assertIn("etki.html", kaynak)


if __name__ == "__main__":
    unittest.main()
