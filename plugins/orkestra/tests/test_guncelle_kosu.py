"""guncelle.Kosu: panelin güncellemeyi arka planda çalıştırması (tek koşu, satır toplama, hata durumu).

`py -3.13 -m pytest plugins/orkestra/tests/test_guncelle_kosu.py`
"""
import os
import sys
import threading

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guncelle as G  # noqa: E402
import test_guncelle as TG  # noqa: E402


class KosuMantikTest(TG.unittest.TestCase):
    """Sahte `calistir` ile: durum geçişleri ve eşzamanlılık."""

    def test_baslangicta_bosta(self):
        s = G.Kosu(calistir=lambda **k: 0).anlik()
        self.assertEqual((s["durum"], s["satirlar"], s["neden"], s["sure"]), ("bosta", [], None, None))

    def test_satirlar_sirayla_toplanir_ve_bitti(self):
        def sahte(kuru, yaz, ev, ortam):
            for i in range(3):
                yaz(f"satir {i}")
            return 0
        k = G.Kosu(calistir=sahte)
        self.assertTrue(k.baslat())
        k.bekle(5)
        s = k.anlik()
        self.assertEqual(s["durum"], "bitti")
        self.assertEqual(s["satirlar"], ["satir 0", "satir 1", "satir 2"])
        self.assertIsNone(s["neden"])
        self.assertIsNotNone(s["sure"])

    def test_ikinci_baslatma_reddedilir(self):
        serbest = threading.Event()
        cagri = []

        def sahte(kuru, yaz, ev, ortam):
            cagri.append(1)
            serbest.wait(5)
            return 0
        k = G.Kosu(calistir=sahte)
        self.assertTrue(k.baslat())
        self.assertEqual(k.anlik()["durum"], "calisiyor")
        self.assertFalse(k.baslat())
        serbest.set()
        k.bekle(5)
        self.assertEqual(len(cagri), 1)
        self.assertEqual(k.anlik()["durum"], "bitti")
        self.assertTrue(k.baslat())  # bittikten sonra yeniden başlatılabilir
        k.bekle(5)

    def test_hata_sonucu_hata_durumuna_dusar_neden_son_hata_satiri(self):
        def sahte(kuru, yaz, ev, ortam):
            yaz("")
            yaz("HATA: GitHub'dan çekilemedi")
            return 1
        k = G.Kosu(calistir=sahte)
        k.baslat()
        k.bekle(5)
        s = k.anlik()
        self.assertEqual(s["durum"], "hata")
        self.assertEqual(s["neden"], "GitHub'dan çekilemedi")

    def test_beklenmedik_istisna_hata_durumuna_dusar(self):
        def sahte(kuru, yaz, ev, ortam):
            raise RuntimeError("patladi")
        k = G.Kosu(calistir=sahte)
        k.baslat()
        k.bekle(5)
        s = k.anlik()
        self.assertEqual(s["durum"], "hata")
        self.assertIn("patladi", s["neden"])

    def test_hata_sonrasi_yeniden_denenebilir_ve_satirlar_sifirlanir(self):
        sonuclar = iter([1, 0])

        def sahte(kuru, yaz, ev, ortam):
            yaz("deneme")
            return next(sonuclar)
        k = G.Kosu(calistir=sahte)
        k.baslat()
        k.bekle(5)
        self.assertEqual(k.anlik()["durum"], "hata")
        self.assertTrue(k.baslat())
        k.bekle(5)
        s = k.anlik()
        self.assertEqual((s["durum"], s["satirlar"], s["neden"]), ("bitti", ["deneme"], None))

    def test_satir_siniri(self):
        def sahte(kuru, yaz, ev, ortam):
            for i in range(G.Kosu.SATIR_SINIRI + 50):
                yaz(str(i))
            return 0
        k = G.Kosu(calistir=sahte)
        k.baslat()
        k.bekle(5)
        self.assertEqual(len(k.anlik()["satirlar"]), G.Kosu.SATIR_SINIRI)


class KosuGercekCalistirTest(TG.Ortam):
    """Gerçek `calistir` (sahte claude.exe): Kosu CLI ile aynı satırları üretir."""

    def test_kosu_cikti_cli_ile_ayni(self):
        dogrudan = []
        self.assertEqual(G.calistir(yaz=dogrudan.append, ev=self.ev, ortam={}), 0)
        k = G.Kosu(ev=self.ev, ortam={})
        self.assertTrue(k.baslat())
        k.bekle(30)
        s = k.anlik()
        self.assertEqual(s["durum"], "bitti")
        self.assertEqual(s["satirlar"], dogrudan)
        self.assertTrue(any(x.startswith("ZATEN GÜNCEL") for x in s["satirlar"]))

    def test_kosu_gercek_hata_nedeni(self):
        self.claude_hatasi = {"marketplace update": 2}
        k = G.Kosu(ev=self.ev, ortam={})
        k.baslat()
        k.bekle(30)
        s = k.anlik()
        self.assertEqual(s["durum"], "hata")
        self.assertIn("pazar yeri güncellenemedi", s["neden"])


if __name__ == "__main__":
    TG.unittest.main()
