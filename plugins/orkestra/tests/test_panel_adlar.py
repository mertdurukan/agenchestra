"""Panel sayfa adları (G-061): Şimdi → Son olaylar, İşler → Dashboard; sohbetler Dashboard'un üstünde."""
import os
import re
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARLIK = os.path.join(KOK, "assets")


def oku(ad):
    """Sayfa (.html) için HTML + ona bağlı sayfa .js/.css dosyaları (ortak.* hariç) birlikte döner."""
    with open(os.path.join(VARLIK, ad), encoding="utf-8") as f:
        h = f.read()
    if ad.endswith(".html"):
        for yol in re.findall(r'(?:src|href)="([\w-]+\.(?:js|css))"', h):
            if not yol.startswith("ortak."):
                with open(os.path.join(VARLIK, yol), encoding="utf-8") as g:
                    h += "\n" + g.read()
    return h


class PanelAdlar(unittest.TestCase):
    def test_sekme_adlari(self):
        js = oku("ortak.js")
        m = re.search(r"const SEKMELER = \[(.*?)\];", js, re.S)
        self.assertIsNotNone(m)
        sekmeler = m.group(1)
        self.assertNotIn("Son olaylar", sekmeler)  # menüden gizli; sayfa GET / ile açılır
        self.assertIn("['isler', 'Dashboard', '/isler']", sekmeler)
        self.assertNotIn("'Şimdi'", sekmeler)
        self.assertNotIn("'İşler'", sekmeler)

    def test_simdi_sayfasi(self):
        h = oku("simdi.html")
        self.assertIn("<title>Orkestra · Son olaylar</title>", h)
        self.assertNotIn('id="sohbetListe"', h)
        self.assertNotIn("sohbetCiz", h)

    def test_isler_sayfasi(self):
        h = oku("isler.html")
        self.assertIn("<title>Orkestra · Dashboard</title>", h)
        s = h.index('id="sohbetler"')
        self.assertLess(s, h.index('class="duzen"'))
        self.assertIn('id="sohbetListe"', h)
        # iş süzgeci ve sohbet süzgeci ayrı öznitelik kullanır
        self.assertIn('data-sfiltre=', h)


if __name__ == "__main__":
    unittest.main()
