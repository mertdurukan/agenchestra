"""I-292 P4: arsivci elle yedek yolu taşımaz; skill başarısızsa durup raporlar."""
import os
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METIN = open(os.path.join(KOK, "agents", "arsivci.md"), encoding="utf-8").read()


class ArsivciMetin(unittest.TestCase):
    def test_elle_yedek_yok(self):
        for yasak in ("Kaynak klasörü hedef", "db.py ve şifre içeren", "Sır taraması yap", "tek satır ekle", "şunu yap:"):
            self.assertNotIn(yasak, METIN, yasak)

    def test_dur_ve_raporla_var(self):
        self.assertIn("DUR", METIN)
        self.assertIn("raporla", METIN)
        self.assertIn("/orkestra:arsivle", METIN)


if __name__ == "__main__":
    unittest.main()
