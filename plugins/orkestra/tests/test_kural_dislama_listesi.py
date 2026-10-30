"""yukle=hook kuralları kural dosyasında tek satırla anılır; bakım sapmayı uyarır (I-271/P3)."""
import os
import sys
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
sys.path.insert(0, AD)
from test_kural_katman import Temel, kural, yaz_json  # noqa: E402
from komutlar import bakim  # noqa: E402
import onay  # noqa: E402

SATIR = "Hook ile yüklenen kurallar (bu dosyada yok, ilgili anda hook söyler): P-005, P-010."


class DislamaListesi(Temel):
    def hazirla(self, kimlikler=("P-005", "P-010")):
        kurallar = [kural("P-001", "Normal kural.")]
        kurallar += [kural(k, f"Hook kuralı {k}.", yukle="hook") for k in kimlikler]
        yaz_json(self.depo, {"kurallar": kurallar})
        onay._kural_dosyasini_yaz(self.sd)

    def test_k1_satir_kimlikler_kayittan_turer(self):
        self.hazirla()
        self.assertIn(SATIR, self.md_oku())
        self.assertNotIn("Hook kuralı", self.md_oku())

    def test_k1_hook_kurali_yoksa_satir_yok(self):
        self.hazirla(())
        self.assertNotIn("Hook ile yüklenen", self.md_oku())

    def test_k2_uyusmazlikta_uyari(self):
        self.hazirla()
        yaz_json(self.depo, {"kurallar": [kural("P-001", "Normal."), kural("P-005", "a", yukle="hook"),
                                          kural("P-010", "b", yukle="hook"), kural("P-009", "c", yukle="hook")]})
        u = bakim.hook_kural_uyari(self.sd)
        self.assertIn("P-009", u)
        self.assertEqual(len(u.splitlines()), 1)

    def test_k2_uyusmada_uyari_yok(self):
        self.hazirla()
        self.assertEqual(bakim.hook_kural_uyari(self.sd), "")


if __name__ == "__main__":
    unittest.main()
