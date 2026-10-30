"""Araçlar sayfası yerleşimi (ADR-0106): Açık/Kapalı düğmesi her kartta aynı sağ kenarda ve satırda durur.

Sahte DOM yerleşim hesaplamaz (tests/panel_duman.js); bu test gerçek Chrome/Edge'i headless koşturur ve
getBoundingClientRect ile ölçer. Tarayıcı yoksa test atlanır (skip mesajında yazar).
`python -m pytest plugins/orkestra/tests/test_panel_araclar_yerlesim.py`
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ADAYLAR = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "google-chrome", "chromium", "chrome", "msedge",
]
UZUN = ("Web tarama ve kazıma. Anahtar kimlik klasöründe firecrawl servisinde FIRECRAWL_API_KEY adıyla durur "
        "(orkestra kimlik ekle firecrawl FIRECRAWL_API_KEY). " * 2)


def tarayici():
    for a in ADAYLAR:
        yol = a if os.path.isabs(a) else shutil.which(a)
        if yol and os.path.exists(yol):
            return yol
    return None


def kart(ad, aciklama, rozet=""):
    return (f'<article class="kart"><div class="kart-ic yatay ayar-satir"><div class="yigin sik">'
            f'<div class="yatay"><b>{ad}</b>{rozet}</div><span class="soluk kucuk-y">{aciklama}</span></div>'
            f'<button type="button" class="anahtar" role="switch" aria-checked="true">'
            f'<span class="anahtar-durum">Açık</span></button></div></article>')


def sayfa(css):
    kartlar = [kart("kisa%02d" % i, "Kısa açıklama.") for i in range(8)]
    kartlar += [kart("uzun%02d" % i, UZUN, '<span class="rozet r-uyari">Ön koşul eksik: docker</span>'
                     '<span class="rozet r-notr">Anahtar eksik</span>') for i in range(11)]
    betik = ("const r=[...document.querySelectorAll('.anahtar')].map(b=>{const x=b.getBoundingClientRect();"
             "const k=b.closest('.kart').getBoundingClientRect();return {sag:Math.round(x.right),ust:Math.round(x.top-k.top),yuk:Math.round(k.height)}});"
             "document.getElementById('o').textContent=JSON.stringify(r)")
    return (f'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="{css.as_uri()}">'
            f'<body><main id="m">{"".join(kartlar)}</main><pre id="o"></pre><script>{betik}</script></body>')


def olc(css, genislik):
    exe = tarayici()
    with tempfile.TemporaryDirectory() as d:
        html = Path(d) / "s.html"
        html.write_text(sayfa(css), encoding="utf-8")
        cikti = subprocess.run([exe, "--headless=new", "--disable-gpu", f"--user-data-dir={d}/p", f"--window-size={genislik},900",
                                "--virtual-time-budget=3000", "--dump-dom", html.as_uri()],
                               capture_output=True, text=True, timeout=60).stdout
    m = re.search(r'<pre id="o">(.*?)</pre>', cikti, re.S)
    assert m, "ölçüm çıktısı yok"
    return json.loads(m.group(1).replace("&quot;", '"'))


@unittest.skipUnless(tarayici(), "Chrome/Edge bulunamadı: yerleşim testi atlandı")
class AnahtarYerlesim(unittest.TestCase):
    def kontrol(self, css, genislik):
        olcum = olc(css, genislik)
        self.assertEqual(len(olcum), 19)
        self.assertEqual(len({o["sag"] for o in olcum}), 1, "düğme sağ kenarları eşit değil: %s" % sorted({o["sag"] for o in olcum}))
        for o in olcum:  # alt satıra düşen düğme kartın ortasında değil altında durur: üst konum kartın yarısını geçmez
            self.assertLess(o["ust"], o["yuk"] / 2 + 1, "düğme alt satıra düştü: %s" % o)

    def test_masaustu_1200(self):
        self.kontrol(ASSETS / "app.css", 1200)

    def test_telefon_375(self):
        self.kontrol(ASSETS / "app.css", 375)


if __name__ == "__main__":
    unittest.main()
