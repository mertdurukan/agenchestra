"""Panel yeniden tasarımı (I-046): hiçbir gösterilen veri silinmez.

Kriterler:
  K1  Yeniden tasarım öncesi sayfalardaki her kimlik (id="...") bugünkü sayfada da vardır.
      Betikler bu kimliklere yazar; kimlik kaybolursa o veri sessizce kaybolur.
  K2  Yeni görsel kitap (gorsel.js, gorsel.css) panel.py STATIK listesindedir.
"""
import os
import re
import subprocess
import sys
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(AD)
ASSETS = os.path.join(KOK, "assets")
sys.path.insert(0, os.path.join(KOK, "scripts"))

# Yeniden tasarımdan önceki son ortak commit (I-046 dalının ayrıldığı yer)
TEMEL = "69b60eedae070f342213aa3496c6b7a7a5e95228"
SAYFALAR = ("isler", "maliyet", "onaylar", "yapilacaklar", "teknik", "simdi")
KIMLIK = re.compile(r'\bid="([^"]+)"')


def _temel(sayfa):
    r = subprocess.run(["git", "-c", "safe.directory=*", "show", f"{TEMEL}:plugins/orkestra/assets/{sayfa}.html"],
                       cwd=KOK, capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


class VeriKorunumu(unittest.TestCase):
    def test_k1_kimlikler_korunur(self):
        denendi = 0
        for sayfa in SAYFALAR:
            eski = _temel(sayfa)
            if eski is None:
                continue  # temel commit bu kopyada yok (ör. kırpılmış klon)
            with open(os.path.join(ASSETS, sayfa + ".html"), encoding="utf-8") as f:
                yeni = f.read()
            kayip = sorted(set(KIMLIK.findall(eski)) - set(KIMLIK.findall(yeni)))
            self.assertEqual(kayip, [], f"{sayfa}.html: kaybolan kimlikler")
            denendi += 1
        if denendi == 0:
            self.skipTest("temel commit okunamadı")

    def test_k2_gorsel_kitap_sunulur(self):
        import panel
        kaynak = open(panel.__file__, encoding="utf-8").read()
        for yol in ("/gorsel.css", "/gorsel.js"):
            self.assertIn(f'"{yol}"', kaynak)


if __name__ == "__main__":
    unittest.main()
