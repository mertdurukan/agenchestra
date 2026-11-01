"""P3 (I-315): ağır üreticiler işçi süreçte koşar; işçi yoksa/çökerse panel sürecinde hesap sürer."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import panel_isci as I  # noqa: E402


class IsciTesti(unittest.TestCase):
    def tearDown(self):
        I.ETKIN = False
        I._havuzu_at()

    def test_varsayilan_kapali_ayni_surecte_hesaplar(self):
        self.assertFalse(I.aktif())
        self.assertEqual(I.uret("ozet", "x", lambda: "yerel"), "yerel")

    def test_ortam_degiskeni_isciyi_kapatir(self):
        I.ETKIN = True
        with mock.patch.dict(os.environ, {"ORKESTRA_PANEL_ISCI": "0"}):
            self.assertFalse(I.aktif())
            self.assertEqual(I.uret("ozet", "x", lambda: "yerel"), "yerel")

    def test_isci_hatasinda_yerel_hesaba_duser_ve_havuz_yenilenir(self):
        I.ETKIN = True
        # bilinmeyen üretici işçide ValueError verir -> istek düşmez, yerel sonuç döner, havuz atılır
        self.assertEqual(I.uret("yok-boyle-uretici", None, lambda: "yerel"), "yerel")
        self.assertIsNone(I._havuz)

    def test_isci_surecte_gercek_sonuc_doner(self):
        I.ETKIN = True
        pid = I._havuz_al().submit(os.getpid).result(timeout=60)
        self.assertNotEqual(pid, os.getpid())


if __name__ == "__main__":
    unittest.main()
