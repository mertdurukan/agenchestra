"""Panel responsive kuralları (I-120): kırılma ölçeği, dokunma hedefi, yazı alt sınırı.

Kriterler:
  K1  Her .html dosyasında viewport meta var.
  K2  CSS ve HTML'deki max-width kırılmaları yalnız 380, 600, 900, 1200.
  K3  ortak.css pointer: coarse bloğu 44 px hedef verir.
  K4  Satır içi font-size değerleri 12 px altına inmez (ikon glifi gorsel.css hariç).
  K5  .bolum:empty gizlenir; tek kalan KPI kartı tam genişlik olur.
"""
import glob
import os
import re
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(KOK, "assets")
IZINLI = {380, 600, 900, 1200}


def _oku(ad):
    with open(os.path.join(ASSETS, ad), encoding="utf-8") as f:
        return f.read()


class ResponsiveKurallar(unittest.TestCase):
    def test_k1_viewport_meta(self):
        for yol in glob.glob(os.path.join(ASSETS, "*.html")):
            with open(yol, encoding="utf-8") as f:
                self.assertIn('name="viewport"', f.read(), os.path.basename(yol))

    def test_k2_kirilma_olcegi(self):
        bulunan = set()
        for yol in glob.glob(os.path.join(ASSETS, "*.css")) + glob.glob(os.path.join(ASSETS, "*.html")):
            with open(yol, encoding="utf-8") as f:
                for m in re.finditer(r"@media[^{]*max-width:\s*(\d+)px", f.read()):
                    bulunan.add(int(m.group(1)))
        self.assertLessEqual(bulunan, IZINLI, f"tanımsız kırılma: {sorted(bulunan - IZINLI)}")

    def test_k3_dokunma_hedefi_44(self):
        t = _oku("ortak.css")
        blok = t[t.index("@media (pointer: coarse)"):]
        blok = blok[:blok.index("\n}\n")]
        self.assertGreaterEqual(blok.count("min-height: 44px"), 2)
        self.assertIn("input", blok)
        self.assertIn(".sekmeler a", blok)

    def test_k4_yazi_alt_siniri(self):
        for yol in glob.glob(os.path.join(ASSETS, "*.css")):
            ad = os.path.basename(yol)
            if ad == "gorsel.css":
                continue
            with open(yol, encoding="utf-8") as f:
                for no, satir in enumerate(f, 1):
                    for m in re.finditer(r"font-size:\s*(\d+(?:\.\d+)?)px", satir):
                        self.assertGreaterEqual(float(m.group(1)), 12, f"{ad}:{no}")
            if ad == "app.css":
                self.assertNotIn("--y11: 11px", open(yol, encoding="utf-8").read())

    def test_k5_bos_bolum_ve_yetim_kart(self):
        t = _oku("ortak.css")
        self.assertIn(".bolum:empty { display: none; }", t)
        self.assertIn(".karolar > .karo:last-child:nth-child(odd) { grid-column: 1 / -1; }", t)


if __name__ == "__main__":
    unittest.main()
