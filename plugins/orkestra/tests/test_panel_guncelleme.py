"""Panel eklenti güncelleme ucu: durum makinesi (panel_guncelleme) ve HTTP uçları (/api/guncelleme, /api/guncelle, /api/guncelle-ertele).

Git ve ağ yok: `kontrol` ve koşu sahtedir; sunucu süreç içinde açılır (panel.json'a dokunulmaz).
`py -3.13 -m pytest plugins/orkestra/tests/test_panel_guncelleme.py`
"""
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
import guncelle as G  # noqa: E402
import panel  # noqa: E402
import panel_guncelleme as PG  # noqa: E402

YENI = {"durum": "yeni", "kurulu": "aaaaaaaaaaaa", "yeni": "bbbbbbb", "fark": 3, "yenilik_say": 1, "klon_kirli": False, "klon": "x",
        "degisiklikler": [{"sha": "bbbbbbb", "konu": "bir"}], "neden": None}
GUNCEL = {"durum": "guncel", "kurulu": "bbbbbbbbbbbb", "yeni": "bbbbbbb", "fark": 0, "klon_kirli": False, "klon": "x",
          "degisiklikler": [], "neden": None}
HATA = {"durum": "hata", "neden": "GitHub'a ulaşılamadı"}


class Saat:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Ortak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saat = Saat()
        self.sonuclar = [YENI]
        self.kontrol_cagri = []
        self.serbest = threading.Event()
        self.serbest.set()
        self.kosu_sonuc = 0

    def sahte_kontrol(self, ev=None, getir=True):
        self.kontrol_cagri.append(getir)
        return dict(self.sonuclar[min(len(self.kontrol_cagri), len(self.sonuclar)) - 1])

    def sahte_calistir(self, kuru, yaz, ev, ortam):
        yaz("ORKESTRA GÜNCELLE")
        self.serbest.wait(5)
        if self.kosu_sonuc:
            yaz("HATA: pazar yeri güncellenemedi (çıkış 2).")
        return self.kosu_sonuc

    def yap(self):
        kosu = G.Kosu(calistir=self.sahte_calistir, saat=self.saat)
        return PG.Guncelleme(dizin=self.tmp.name, kontrol=self.sahte_kontrol, kosu=kosu, saat=self.saat)


class DurumTest(Ortak):
    def test_yoklama_yokken_durum_yok(self):
        d = self.yap().durum()
        self.assertEqual((d["durum"], d["kontrol"], d["kosu"], d["ertelendi"]), ("yok", None, None, False))

    def test_yeni_surum_yeni_durumu(self):
        g = self.yap()
        g.yokla()
        d = g.durum()
        self.assertEqual(d["durum"], "yeni")
        self.assertEqual(d["kontrol"]["yeni"], "bbbbbbb")
        self.assertEqual(d["kontrol"]["fark"], 3)
        self.assertEqual(d["kontrol"]["degisiklikler"][0]["konu"], "bir")

    def test_onekli_commit_yoksa_da_surum_farkinda_kart_cikar(self):
        self.sonuclar = [dict(YENI, yenilik_say=0, degisiklikler=[])]
        g = self.yap()
        g.yokla()
        self.assertEqual(g.durum()["durum"], "yeni")

    def test_guncelse_yok(self):
        self.sonuclar = [GUNCEL]
        g = self.yap()
        g.yokla()
        self.assertEqual(g.durum()["durum"], "yok")

    def test_ag_hatasi_bulunmus_yeni_sonucu_silmez(self):
        self.sonuclar = [YENI, HATA]
        g = self.yap()
        g.yokla()
        g.yokla()
        self.assertEqual(g.durum()["durum"], "yeni")

    def test_ilk_yoklama_hata_ise_sessiz_yok(self):
        self.sonuclar = [HATA]
        g = self.yap()
        g.yokla()
        d = g.durum()
        self.assertEqual(d["durum"], "yok")
        self.assertEqual(d["kontrol"]["neden"], "GitHub'a ulaşılamadı")

    def test_kontrol_istisnasi_sunucuyu_dusurmez(self):
        def patlat(ev=None, getir=True):
            raise RuntimeError("beklenmedik")
        g = PG.Guncelleme(dizin=self.tmp.name, kontrol=patlat, kosu=G.Kosu(calistir=self.sahte_calistir))
        g.yokla()
        self.assertEqual(g.durum()["durum"], "yok")


class ErtelemeTest(Ortak):
    def test_ertele_bu_sha_icin_gizler_yeni_sha_gelince_doner(self):
        self.sonuclar = [YENI, dict(YENI, yeni="ccccccc")]
        g = self.yap()
        g.yokla()
        self.assertFalse(g.durum()["ertelendi"])
        self.assertEqual(g.ertele(), {"tamam": True, "sha": "bbbbbbb"})
        self.assertTrue(g.durum()["ertelendi"])
        g.yokla()   # daha yeni sürüm yayınlandı
        self.assertFalse(g.durum()["ertelendi"])
        self.assertEqual(g.durum()["kontrol"]["yeni"], "ccccccc")

    def test_erteleme_yeniden_baslatmada_kalir(self):
        g = self.yap()
        g.yokla()
        g.ertele()
        g2 = self.yap()
        g2.yokla()
        self.assertTrue(g2.durum()["ertelendi"])

    def test_yeni_surum_yokken_ertelenemez(self):
        self.sonuclar = [GUNCEL]
        g = self.yap()
        g.yokla()
        self.assertFalse(g.ertele()["tamam"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, PG.ERTELEME_DOSYASI)))

    def test_bozuk_erteleme_dosyasi_kart_gizlenmez(self):
        g = self.yap()
        g.yokla()
        with open(os.path.join(self.tmp.name, PG.ERTELEME_DOSYASI), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertFalse(g.durum()["ertelendi"])


class KosuTest(Ortak):
    def test_guncelle_calisiyor_sonra_bitti_sonra_kontrol_yenilenir(self):
        self.sonuclar = [YENI, GUNCEL]
        self.serbest.clear()
        g = self.yap()
        g.yokla()
        self.assertEqual(g.guncelle(), {"tamam": True})
        for _ in range(100):   # iş parçacığı ilk satırı yazana kadar bekle
            if g.kosu.anlik()["satirlar"]:
                break
            threading.Event().wait(0.05)
        d = g.durum()
        self.assertEqual((d["durum"], d["kosu"]["durum"]), ("calisiyor", "calisiyor"))
        self.assertEqual(d["kosu"]["satirlar"][0], "ORKESTRA GÜNCELLE")
        self.serbest.set()
        g.kosu.bekle(5)
        d = g.durum()
        self.assertEqual(d["durum"], "bitti")
        self.assertEqual(self.kontrol_cagri, [True, False])   # koşu sonrası yerel yenileme: ağa çıkmadı
        self.assertEqual(d["kontrol"]["fark"], 0)

    def test_ikinci_guncelle_reddedilir(self):
        self.serbest.clear()
        g = self.yap()
        self.assertTrue(g.guncelle()["tamam"])
        r = g.guncelle()
        self.assertFalse(r["tamam"])
        self.assertIn("zaten çalışıyor", r["hata"])
        self.serbest.set()
        g.kosu.bekle(5)

    def test_hata_kartta_neden_ve_tekrar_denenebilir(self):
        self.kosu_sonuc = 1
        g = self.yap()
        g.yokla()
        g.guncelle()
        g.kosu.bekle(5)
        d = g.durum()
        self.assertEqual(d["durum"], "hata")
        self.assertIn("pazar yeri güncellenemedi", d["kosu"]["neden"])
        self.kosu_sonuc = 0
        self.assertTrue(g.guncelle()["tamam"])
        g.kosu.bekle(5)
        self.assertEqual(g.durum()["durum"], "bitti")

    def test_bitti_karti_suresi_dolunca_kontrol_durumuna_doner(self):
        self.sonuclar = [YENI, GUNCEL]
        g = self.yap()
        g.yokla()
        g.guncelle()
        g.kosu.bekle(5)
        self.assertEqual(g.durum()["durum"], "bitti")
        self.saat.t += PG.BITTI_GOSTER + 1
        self.assertEqual(g.durum()["durum"], "yok")


class YoklamaTest(Ortak):
    def test_yoklama_dongusu_acilista_bir_kez_fetch_eder_ikinci_baslatma_etkisiz(self):
        ilk = threading.Event()

        def kontrol(ev=None, getir=True):
            self.kontrol_cagri.append(getir)
            ilk.set()
            return dict(YENI)
        g = PG.Guncelleme(dizin=self.tmp.name, kontrol=kontrol, kosu=G.Kosu(calistir=self.sahte_calistir))
        g.yoklamayi_baslat()
        g.yoklamayi_baslat()
        self.assertTrue(ilk.wait(5))
        g.yoklamayi_durdur()
        g._is.join(5)
        self.assertEqual(self.kontrol_cagri, [True])
        self.assertEqual(g.durum()["durum"], "yeni")


class HttpTest(Ortak):
    def setUp(self):
        super().setUp()
        self.g = self.yap()
        self.g.yokla()
        self.yama = mock.patch.object(panel, "GUNCELLEME", self.g)
        self.yama.start()
        self.addCleanup(self.yama.stop)
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()
        self.addCleanup(self.sunucu.server_close)
        self.addCleanup(self.sunucu.shutdown)

    def istek(self, yontem, yol, baslik=None, host=None):
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        h.update({"X-Orkestra": "1", "Content-Type": "application/json"} if yontem == "POST" else {})
        h.update(baslik or {})
        h = {k: v for k, v in h.items() if v is not None}
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(yontem, yol, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        if yontem == "POST":
            c.putheader("Content-Length", "2")
        c.endheaders(b"{}" if yontem == "POST" else None)
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def test_get_durum(self):
        k, b = self.istek("GET", "/api/guncelleme")
        self.assertEqual(k, 200)
        v = json.loads(b)
        self.assertEqual(v["durum"], "yeni")
        self.assertEqual(v["kontrol"]["yeni"], "bbbbbbb")

    def test_tum_calisma_alanlari_kipinde_de_calisir(self):
        k, b = self.istek("GET", "/api/guncelleme?alan=*")
        self.assertEqual(k, 200)
        self.assertEqual(json.loads(b)["durum"], "yeni")
        k, b = self.istek("POST", "/api/guncelle-ertele?alan=*")
        self.assertEqual(k, 200)
        self.assertTrue(json.loads(b)["tamam"])

    def test_sohbet_ac_alan_yildizda_alan_hatasi_vermez(self):
        # geçersiz kimlik: sohbet açılmaz, ama istek alan denetiminden geçip niyet.ac'ye ulaşır (400 değil)
        k, b = self.istek("POST", "/ac?oturum=gecersiz&alan=*")
        self.assertEqual(k, 200)
        self.assertEqual(json.loads(b)["hata"], "geçersiz oturum kimliği")

    def test_diger_yazma_uclari_alan_yildizda_hala_reddedilir(self):
        k, b = self.istek("POST", "/onay?alan=*")
        self.assertEqual(k, 400)
        self.assertIn("tek bir çalışma alanı", json.loads(b)["hata"])

    def test_guncelle_baslik_ve_yerel_host_ister(self):
        self.serbest.clear()
        k, _ = self.istek("POST", "/api/guncelle", baslik={"X-Orkestra": None})
        self.assertEqual(k, 403)
        k, _ = self.istek("POST", "/api/guncelle", host="evil.example:80")
        self.assertEqual(k, 403)
        self.assertEqual(self.g.kosu.anlik()["durum"], "bosta")
        self.serbest.set()

    def test_guncelle_baslatir_ikincisi_409(self):
        self.serbest.clear()
        k, b = self.istek("POST", "/api/guncelle")
        self.assertEqual((k, json.loads(b)["tamam"]), (200, True))
        k, b = self.istek("POST", "/api/guncelle")
        self.assertEqual(k, 409)
        self.assertFalse(json.loads(b)["tamam"])
        k, b = self.istek("GET", "/api/guncelleme")
        self.assertEqual(json.loads(b)["durum"], "calisiyor")
        self.serbest.set()
        self.g.kosu.bekle(5)

    def test_ertele_ucu(self):
        k, b = self.istek("POST", "/api/guncelle-ertele")
        self.assertEqual(k, 200)
        k, b = self.istek("GET", "/api/guncelleme")
        self.assertTrue(json.loads(b)["ertelendi"])

    def test_ertele_yeni_surum_yokken_409(self):
        self.g._son = dict(GUNCEL)
        k, b = self.istek("POST", "/api/guncelle-ertele")
        self.assertEqual(k, 409)

    def test_get_post_yontem_ayrimi(self):
        k, _ = self.istek("GET", "/api/guncelle")
        self.assertEqual(k, 404)

    def test_surum_21(self):
        self.assertRegex(panel.SURUM, r"^[0-9]+$")  # sabit değil: her sürüm artışında kırılmasın


if __name__ == "__main__":
    unittest.main()
