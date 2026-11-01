"""I-003 hız: oturumlar/ budaması yalnız eski ara dosyaları siler; durum/denetim kayıtları kalır; ad süzgeci sonucu değiştirmez."""
import datetime, json, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import ozet  # noqa: E402

ESKI = time.time() - 72 * 3600


def _yaz(d, ad, yas_eski=True):
    y = os.path.join(d, ad)
    open(y, "w", encoding="utf-8").write("{}")
    if yas_eski:
        os.utime(y, (ESKI, ESKI))


class Budama(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self.d = os.path.join(self.sd, "oturumlar")
        os.makedirs(self.d)

    def test_eski_ara_dosyalar_silinir_digerleri_kalir(self):
        silinecek = ["a.devir", "a.isdeg", "a.soguk", "a.json.lock", "a.devir_esigi.json", "panel_ac_a.json",
                     "yonlendirme_a.json", "devir_a.log"]
        kalacak = ["a.json", "a.baglanti.json", "alan_a.json", "onay_kaydi_a.json", "devir_a.md", "acik_ajan_x.json",
                   "is_I-1.json"]
        for ad in silinecek + kalacak:
            _yaz(self.d, ad)
        self.assertEqual(ozet.oturum_budama(self.sd), len(silinecek))
        self.assertEqual(sorted(os.listdir(self.d)), sorted(kalacak))

    def test_taze_dosya_silinmez(self):
        _yaz(self.d, "b.devir", yas_eski=False)
        self.assertEqual(ozet.oturum_budama(self.sd), 0)
        self.assertTrue(os.path.exists(os.path.join(self.d, "b.devir")))

    def test_dizin_yoksa_sifir(self):
        self.assertEqual(ozet.oturum_budama(os.path.join(self.sd, "yok")), 0)

    def test_budama_6_saatte_bir(self):
        self.assertTrue(ozet._budama_zamani_geldi(self.sd))
        self.assertFalse(ozet._budama_zamani_geldi(self.sd))

    def test_ad_suzgeci_acik_gorevi_kaybetmez(self):
        simdi = datetime.datetime.now().astimezone()
        with open(os.path.join(self.d, "s1.json"), "w", encoding="utf-8") as f:
            json.dump({"acik_gorevler": [{"id": 1}], "guncelleme": simdi.isoformat()}, f)
        for ad in ("panel_ac_s1.json", "s1.baglanti.json", "alan_s1.json", "s1.devir_esigi.json"):
            _yaz(self.d, ad, yas_eski=False)
        self.assertEqual(ozet.arka_plan_oturumlari(self.sd, simdi), {"s1": 1})


if __name__ == "__main__":
    unittest.main()
