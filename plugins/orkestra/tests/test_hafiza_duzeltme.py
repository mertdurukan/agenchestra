"""hafiza_duzeltme: birebir aynı düzeltme notunun tekrarını bulur; tek notu ve farklı notları bulgu saymaz (ADR-0029)."""
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hafiza_duzeltme as H  # noqa: E402

NOT = "(teyidi 13.10'da kapsam daralması olarak düzeltildi)"
SATIR = "- ML çöküşü kesin sanıldı " + NOT


class Notlar(unittest.TestCase):
    def test_parantezli_not_bulunur(self):
        self.assertEqual(len(H.notlar(SATIR)), 1)

    def test_koseli_not_bulunur(self):
        self.assertEqual(len(H.notlar("kayıt [düzeltme: 13.10 prod teyidi kapsam daralması]")), 1)

    def test_baglanti_not_degil(self):
        self.assertEqual(H.notlar("bkz [[klibre-db]] ve [[düzeltme-kaydi-uzun-ad]]"), [])

    def test_isaretsiz_parantez_not_degil(self):
        self.assertEqual(H.notlar("tablo (rnv.ml_forecast kolonu için ayrıntı var)"), [])

    def test_kisa_isaret_not_degil(self):
        self.assertEqual(H.notlar("madde (düzeltildi) tamam"), [])

    def test_normallestirme_buyuk_kucuk_ve_bosluk(self):
        a = H.notlar("x (Düzeltme:   KAPSAM daralması oldu)")[0][1]
        b = H.notlar("y (düzeltme: kapsam daralması   oldu.)")[0][1]
        self.assertEqual(a, b)

    def test_turkce_buyuk_i(self):
        a = H.notlar("x (DÜZELTME: IŞIK ve İZ kaydı değişti)")[0][1]
        b = H.notlar("y (düzeltme: ışık ve iz kaydı değişti)")[0][1]
        self.assertEqual(a, b)

    def test_satir_numarasi(self):
        self.assertEqual(H.notlar("a\nb\n" + SATIR)[0][0], 3)


class Tekrarlar(unittest.TestCase):
    def test_uc_yerde_ayni_not_bir_grup_adet_uc(self):
        g = H.tekrarlar({"a.md": SATIR, "b.md": "x\n" + SATIR, "c.md": SATIR + "\ny"})
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["adet"], 3)

    def test_tek_not_bulgu_degil(self):
        self.assertEqual(H.tekrarlar({"a.md": SATIR, "b.md": "temiz"}), [])

    def test_farkli_notlar_bulgu_degil(self):
        self.assertEqual(H.tekrarlar({"a.md": "(düzeltme: [[klibre-db]])", "b.md": "(düzeltme: [[baska-kayit]])"}), [])

    def test_ayni_dosyada_iki_kez(self):
        self.assertEqual(H.tekrarlar({"a.md": SATIR + "\n" + SATIR})[0]["adet"], 2)

    def test_esik_ayardan(self):
        a = dict(H.ayar(), esik=3)
        self.assertEqual(H.tekrarlar({"a.md": SATIR + "\n" + SATIR}, a), [])


class Yol(unittest.TestCase):
    def test_hafiza_yolu(self):
        self.assertTrue(H.hafiza_yolu_mu(r"C:\Users\PC\.claude\projects\C--Mert-McD\memory\klibre.md"))
        self.assertTrue(H.hafiza_yolu_mu("/home/u/.claude/projects/x/memory/alt/k.md"))

    def test_hafiza_disi_yol(self):
        self.assertFalse(H.hafiza_yolu_mu(r"C:\Mert\McD\README.md"))
        self.assertFalse(H.hafiza_yolu_mu(r"C:\Users\PC\.claude\projects\x\memory\k.txt"))


class Yazim(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_hd_")
        self.mem = os.path.join(self.kok, ".claude", "projects", "p", "memory")
        os.makedirs(self.mem)

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def yaz(self, ad, metin):
        with open(os.path.join(self.mem, ad), "w", encoding="utf-8") as f:
            f.write(metin)
        return os.path.join(self.mem, ad)

    def test_ilk_not_serbest(self):
        y = self.yaz("a.md", "temiz")
        self.assertIsNone(H.yazim_ihlali(y, "temiz", "temiz\n" + SATIR))

    def test_ikinci_ayni_not_dosya_disinda_reddedilir(self):
        self.yaz("a.md", SATIR)
        y = self.yaz("b.md", "temiz")
        self.assertIn("2 kez", H.yazim_ihlali(y, "temiz", SATIR) or "")

    def test_ayni_dosyada_ikinci_not_reddedilir(self):
        y = self.yaz("a.md", SATIR)
        self.assertIsNotNone(H.yazim_ihlali(y, SATIR, SATIR + "\n" + SATIR))

    def test_mevcut_tekrar_artmadan_duzenleme_serbest(self):
        self.yaz("a.md", SATIR)
        y = self.yaz("b.md", SATIR)
        self.assertIsNone(H.yazim_ihlali(y, SATIR, SATIR + "\nbaşka satır"))

    def test_tekrari_azaltan_yazim_serbest(self):
        self.yaz("a.md", SATIR)
        y = self.yaz("b.md", SATIR)
        self.assertIsNone(H.yazim_ihlali(y, SATIR, "temizlendi"))

    def test_farkli_sozcuklu_not_serbest(self):
        self.yaz("a.md", SATIR)
        y = self.yaz("b.md", "x")
        self.assertIsNone(H.yazim_ihlali(y, "x", "(düzeltme: [[baska-kayit-adi]])"))

    def test_hafiza_disi_dosya_serbest(self):
        d = os.path.join(self.kok, "doc.md")
        self.assertIsNone(H.yazim_ihlali(d, "", SATIR + "\n" + SATIR))

    def test_kapali_mod_serbest(self):
        y = self.yaz("a.md", SATIR)
        self.assertIsNone(H.yazim_ihlali(y, SATIR, SATIR + "\n" + SATIR, a=dict(H.ayar(), mod="kapali")))

    def test_tara_klasoru(self):
        self.yaz("a.md", SATIR)
        self.yaz("b.md", SATIR)
        self.yaz("c.md", SATIR)
        g = H.tara(self.mem)
        self.assertEqual((len(g), g[0]["adet"]), (1, 3))


class Ayar(unittest.TestCase):
    def test_ayar_dosyasi_gecerli_json_ve_okunur(self):
        import json
        with open(os.path.join(KOK, "ayarlar", "hafiza_duzeltme.json"), encoding="utf-8") as f:
            d = json.load(f)  # bozuk dosya sessizce varsayılana düşer; burada yakalanır
        self.assertEqual(H.ayar()["hafiza_yolu"], d["hafiza_yolu"])
        self.assertEqual(H.ayar()["isaret_kokleri"], d["isaret_kokleri"])

    def test_varsayilan_mod_ihlal(self):
        self.assertEqual(H.ayar()["mod"], "ihlal")

    def test_ortam_anahtari(self):
        eski = os.environ.get("ORKESTRA_HAFIZA_DUZELTME")
        try:
            os.environ["ORKESTRA_HAFIZA_DUZELTME"] = "0"
            self.assertFalse(H.acik())
            os.environ.pop("ORKESTRA_HAFIZA_DUZELTME")
            self.assertTrue(H.acik())
        finally:
            if eski is not None:
                os.environ["ORKESTRA_HAFIZA_DUZELTME"] = eski


if __name__ == "__main__":
    unittest.main()
