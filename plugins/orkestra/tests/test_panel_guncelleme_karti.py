"""Gelen kutusu eklenti güncelleme kartı (ADR-0039): dört durumun çizimi, erteleme, Güncelle düğmesi ve ilerleme yoklaması.

Node'da sahte tarayıcıyla (tests/panel_duman.js) gerçek assets/app.js koşulur; ağ ve sunucu yoktur.
`py -3.13 -m pytest plugins/orkestra/tests/test_panel_guncelleme_karti.py`
"""
import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import test_panel_pencere_birim as TPB

YOL = "/api/guncelleme"
YENI = {"durum": "yeni", "ertelendi": False,
        "kontrol": {"kurulu": "838540496656", "yeni": "7a6e89c", "fark": 36, "klon_kirli": False, "neden": None, "zaman": 1.0,
                    "degisiklikler": [{"sha": "7a6e89c", "konu": "Panel: güncelleme kartı"}, {"sha": "1234567", "konu": "Başka değişiklik"}]},
        "kosu": None}
CALISIYOR = {"durum": "calisiyor", "ertelendi": False, "kontrol": YENI["kontrol"],
             "kosu": {"durum": "calisiyor", "satirlar": ["ORKESTRA GÜNCELLE", "", "> git fetch -q origin"], "neden": None, "sure": 4.2, "bitis": None}}
BITTI = {"durum": "bitti", "ertelendi": False, "kontrol": dict(YENI["kontrol"], fark=0, degisiklikler=[]),
         "kosu": {"durum": "bitti", "satirlar": ["GÜNCELLENDİ"], "neden": None, "sure": 12.3, "bitis": 2.0}}
HATA = {"durum": "hata", "ertelendi": False, "kontrol": YENI["kontrol"],
        "kosu": {"durum": "hata", "satirlar": ["ORKESTRA GÜNCELLE", "HATA: pazar yeri güncellenemedi (çıkış 2)."],
                 "neden": "pazar yeri güncellenemedi (çıkış 2).", "sure": 3.0, "bitis": 3.0}}
YOK = {"durum": "yok", "ertelendi": False, "kontrol": None, "kosu": None}


def kos(gunc, senaryo=None, ek=None, onay=False):
    fx = TPB.fixture()
    fx[YOL] = copy.deepcopy(gunc)
    if onay:
        fx["/onaylar.json"] = {"acik": True, "sayac": {"uygulanacak": 0}, "kayitlar": [
            {"id": "O-1", "durum": "bekliyor", "tur": "karar", "baslik": "DIGER-KARAR", "metin": "x", "olusturma": TPB.ISO}]}
    fx.update(copy.deepcopy(ek or {}))
    sn = senaryo or [{"depo": {}, "hash": "#/gelen"}]
    with tempfile.TemporaryDirectory() as t:
        y = {a: os.path.join(t, a + ".json") for a in ("fx", "sn", "cikti")}
        json.dump(fx, open(y["fx"], "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(sn, open(y["sn"], "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.run(["node", TPB.DUMAN, TPB.APP, y["fx"], y["sn"], y["cikti"]], check=True, timeout=180)
        c = json.load(open(y["cikti"], encoding="utf-8"))
    assert c["hatalar"] == [], c["hatalar"]
    return c["sonuc"]


def html(gunc, **k):
    return TPB._metin(kos(gunc, **k)[0])


def kart(h):
    m = re.search(r'<article class="oge oge-guncelleme".*?</article>', h, re.S)
    return m.group(0) if m else ""


@unittest.skipUnless(shutil.which("node"), "node yok")
class KartCizimTest(unittest.TestCase):
    def test_yeni_surum_karti_ve_eylemleri(self):
        k = kart(html(YENI))
        self.assertIn('data-guncelleme="yeni"', k)
        self.assertIn("Orkestra güncellemesi var", k)
        self.assertIn("36 yeni değişiklik", k)
        self.assertIn("<code>8385404</code> → <code>7a6e89c</code>", k.replace("838540496656", "8385404"))
        self.assertIn("Neler değişti", k)
        self.assertIn("Panel: güncelleme kartı", k)
        self.assertIn("ve 34 değişiklik daha", k)
        self.assertIn('data-eylem="guncelle"', k)
        self.assertIn('data-eylem="guncelle-ertele"', k)
        self.assertIn("Güncelleme yeni oturumda yüklenir", k)

    def test_kart_karar_ver_grubunda_ilk_siradadir(self):
        h = html(YENI, onay=True)
        self.assertLess(h.index("Orkestra güncellemesi var"), h.index("DIGER-KARAR"))
        self.assertLess(h.index("Karar ver"), h.index("Orkestra güncellemesi var"))

    def test_erteleneni_gizler_gelen_kutusu_bos_olabilir(self):
        h = html(dict(YENI, ertelendi=True))
        self.assertNotIn("Orkestra güncellemesi var", h)
        self.assertNotIn("oge-guncelleme", h)

    def test_yok_durumunda_kart_yok(self):
        self.assertNotIn("oge-guncelleme", html(YOK))

    def test_veri_yoksa_gelen_kutusu_yine_cizilir(self):
        h = html(YOK, ek={YOL: {"durum": "yok"}})
        self.assertIn("Gelen kutusu", h)

    def test_calisiyor_son_satir_canli_bolge_ve_pasif_dugme(self):
        k = kart(html(CALISIYOR))
        self.assertIn('data-guncelleme="calisiyor"', k)
        self.assertIn("Orkestra güncelleniyor", k)
        self.assertIn('aria-live="polite"', k)
        self.assertIn("&gt; git fetch -q origin", k)   # son boş olmayan satır, kaçışlı
        self.assertIn('aria-busy="true"', k)
        self.assertIn("disabled", k)
        self.assertNotIn('data-eylem="guncelle"', k)
        self.assertNotIn('data-eylem="guncelle-ertele"', k)

    def test_bitti_yeni_oturum_yonergesi(self):
        k = kart(html(BITTI))
        self.assertIn("Orkestra güncellendi", k)
        self.assertIn("/reload-plugins", k)
        self.assertIn("12 sn sürdü", k)
        self.assertNotIn("data-eylem", k)

    def test_hata_nedeni_tekrar_dene_ve_cikti(self):
        k = kart(html(HATA))
        self.assertIn("Güncelleme başarısız", k)
        self.assertIn('role="alert"', k)
        self.assertIn("pazar yeri güncellenemedi (çıkış 2).", k)
        self.assertIn("Tekrar dene", k)
        self.assertIn('data-eylem="guncelle"', k)
        self.assertIn("Koşu çıktısı", k)
        self.assertIn("orkestra update", k)

    def test_kirli_klon_uyarisi(self):
        g = copy.deepcopy(YENI)
        g["kontrol"]["klon_kirli"] = True
        self.assertIn("commitlenmemiş değişiklik", kart(html(g)))
        self.assertNotIn("commitlenmemiş", kart(html(YENI)))

    def test_commit_konusu_kacislanir(self):
        g = copy.deepcopy(YENI)
        g["kontrol"]["degisiklikler"][0]["konu"] = "<script>alert(1)</script>"
        h = kart(html(g))
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_fark_bilinmiyorsa_sayisiz_metin(self):
        g = copy.deepcopy(YENI)
        g["kontrol"]["fark"] = None
        k = kart(html(g))
        self.assertIn("Yeni değişiklikler var", k)
        self.assertNotIn("daha</li>", k)

    def test_tum_calisma_alanlari_kipinde_de_gorunur(self):
        h = TPB._metin(kos(YENI, senaryo=[{"depo": {"orkestra.tumAlan": "1"}, "hash": "#/gelen"}])[0])
        self.assertIn("Orkestra güncellemesi var", h)


@unittest.skipUnless(shutil.which("node"), "node yok")
class KartEtkilesimTest(unittest.TestCase):
    def test_sonra_erteler_ve_karti_gizler(self):
        ek = {"POST /api/guncelle-ertele": {"status": 200, "govde": {"tamam": True},
                                            "sonra": {YOL: dict(YENI, ertelendi=True)}}}
        s = kos(YENI, ek=ek, senaryo=[{"depo": {}, "hash": "#/gelen", "adimlar": [["tikla", "guncelle-ertele", {}]]}])[0]
        self.assertEqual([p["yol"].split("?")[0] for p in s["postlar"]], ["/api/guncelle-ertele"])
        self.assertNotIn("oge-guncelleme", TPB._metin(s))

    def test_guncelle_post_eder_calisiyor_gosterir_ilerlemeyi_yoklar_ve_biter(self):
        ek = {"POST /api/guncelle": {"status": 200, "govde": {"tamam": True},
                                     "sonra": {YOL: {"__sira": [CALISIYOR, BITTI]}}}}
        sn = [{"depo": {}, "hash": "#/gelen", "adimlar": [["tikla", "guncelle", {}], ["bekle", 100]]},
              {"adimlar": [["bekle", 1400]]},
              {"adimlar": [["bekle", 1400]]}]
        a, b, c = kos(YENI, ek=ek, senaryo=sn)
        self.assertEqual([p["yol"].split("?")[0] for p in a["postlar"]], ["/api/guncelle"])
        self.assertIn('data-guncelleme="calisiyor"', TPB._metin(a))
        self.assertIn("&gt; git fetch -q origin", TPB._metin(a))
        # bir saniye sonra yoklama bitti durumunu getirir
        self.assertIn('data-guncelleme="bitti"', TPB._metin(b))
        self.assertGreaterEqual(b["getler"].count(YOL), 1)
        # bitince yoklama durur
        self.assertEqual(c["getler"].count(YOL), 0)
        self.assertIn('data-guncelleme="bitti"', TPB._metin(c))

    def test_baslatilamazsa_kart_yeni_kalir_dugme_tekrar_acilir(self):
        ek = {"POST /api/guncelle": {"status": 500, "govde": {"tamam": False, "hata": "patladi"}}}
        s = kos(YENI, ek=ek, senaryo=[{"depo": {}, "hash": "#/gelen", "adimlar": [["tikla", "guncelle", {}]]}])[0]
        self.assertEqual(len(s["postlar"]), 1)
        self.assertIn('data-guncelleme="yeni"', TPB._metin(s))

    def test_baska_sekmede_calisiyorsa_409_sonrasi_calisiyor_gorunur(self):
        ek = {"POST /api/guncelle": {"status": 409, "govde": {"tamam": False, "hata": "Güncelleme zaten çalışıyor."},
                                     "sonra": {YOL: CALISIYOR}}}
        s = kos(YENI, ek=ek, senaryo=[{"depo": {}, "hash": "#/gelen", "adimlar": [["tikla", "guncelle", {}], ["bekle", 100]]}])[0]
        self.assertIn('data-guncelleme="calisiyor"', TPB._metin(s))

    def test_hata_kartinda_tekrar_dene_yeniden_baslatir(self):
        ek = {"POST /api/guncelle": {"status": 200, "govde": {"tamam": True}, "sonra": {YOL: CALISIYOR}}}
        s = kos(HATA, ek=ek, senaryo=[{"depo": {}, "hash": "#/gelen", "adimlar": [["tikla", "guncelle", {}], ["bekle", 100]]}])[0]
        self.assertEqual([p["yol"].split("?")[0] for p in s["postlar"]], ["/api/guncelle"])
        self.assertIn('data-guncelleme="calisiyor"', TPB._metin(s))

    def test_sayfa_acilisinda_calisan_koşu_yoklanir(self):
        """Sayfa yenilenince sunucuda sürmekte olan koşu görünür ve yoklama kendiliğinden başlar."""
        sn = [{"depo": {}, "hash": "#/gelen", "adimlar": [["bekle", 1400]]}]
        s = kos({"__sira": [CALISIYOR, BITTI]}, senaryo=sn)[0]
        self.assertIn('data-guncelleme="bitti"', TPB._metin(s))


if __name__ == "__main__":
    unittest.main()
