"""Gelen kutusu sağ paneli: insan kararı bekleyen işler (onay, etki sorusu, seni bekleyen sohbet) sohbete göre tek kartta."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import test_panel_pencere_birim as TPB

ISO = TPB.ISO


def _onay(kimlik, baslik, oturum, **ek):
    return {"id": kimlik, "tur": "karar", "baslik": baslik, "metin": "", "durum": "bekliyor", "secenekler": [],
            "oturum": oturum, "olusturma": ISO, "alan": {"id": "a1", "ad": "proje"}, **ek}


def _sohbet(oturum, ad, bekleyen="sen", **ek):
    return {"oturum": oturum, "sohbet": ad, "kisa": ad, "bekleyen": bekleyen, "bekleme": "Hangisini seçelim?" if bekleyen == "sen" else None,
            "proje": "proje", "son_zaman": ISO, "arsiv": False, "link": "claude://claude.ai/epitaxy/" + oturum, **ek}


def _calistir(kayitlar, oturumlar):
    fx = TPB.fixture()
    fx["/onaylar.json"] = {"kayitlar": kayitlar, "sayac": {"uygulanacak": 0}}
    fx["/simdi.json"] = {"oturumlar": oturumlar, "sayac": {"claude": 1}}
    senaryo = [{"anahtar": ["gelen"], "depo": {}, "hash": "#/gelen"}]
    with tempfile.TemporaryDirectory() as t:
        yollar = {a: os.path.join(t, a + ".json") for a in ("fx", "sn", "cikti")}
        json.dump(fx, open(yollar["fx"], "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(senaryo, open(yollar["sn"], "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.run(["node", TPB.DUMAN, TPB.APP, yollar["fx"], yollar["sn"], yollar["cikti"]], check=True, timeout=180)
        cikti = json.load(open(yollar["cikti"], encoding="utf-8"))
    assert cikti["hatalar"] == [], cikti["hatalar"]
    return TPB._metin(cikti["sonuc"][0])


def _panel(html):
    m = re.search(r'<aside class="insan-panel".*?</aside>', html, re.S)
    return m.group(0) if m else ""


@unittest.skipUnless(shutil.which("node"), "node yok")
class InsanKarariPaneli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _calistir(
            [_onay("O-1", "KARAR-A1", "s-a"), _onay("O-2", "KARAR-A2", "s-a"), _onay("O-3", "KARAR-A3", "s-a"),
             _onay("O-4", "KARAR-B1", "s-b"), _onay("O-5", "KARAR-YETIM", None)],
            [_sohbet("s-a", "SOHBET-A"), _sohbet("s-b", "SOHBET-B", bekleyen="claude"), _sohbet("s-c", "SOHBET-C")])
        cls.panel = _panel(cls.html)

    def test_ayni_sohbetin_kararlari_tek_kartta(self):
        kartlar = re.findall(r'<article class="oge insan-kart.*?</article>', self.panel, re.S)
        a = [k for k in kartlar if "SOHBET-A" in k]
        self.assertEqual(len(a), 1)
        for ad in ("KARAR-A1", "KARAR-A2", "KARAR-A3"):
            self.assertIn(ad, a[0])
        self.assertNotIn("KARAR-B1", a[0])

    def test_kartlar_sohbete_gider(self):
        self.assertIn('data-oturum="s-a"', self.panel)
        self.assertIn('data-eylem="sohbet-ac" data-oturum="s-a"', self.panel)
        self.assertIn("Son sohbete git", self.panel)

    def test_bekleyen_sohbet_karar_olmasa_da_sagda(self):
        self.assertIn("SOHBET-C", self.panel)
        self.assertIn("Hangisini seçelim?", self.panel)

    def test_sohbetsiz_karar_ayri_kart_ve_sohbete_git_yok(self):
        yetim = [k for k in re.findall(r'<article class="oge insan-kart.*?</article>', self.panel, re.S) if "KARAR-YETIM" in k]
        self.assertEqual(len(yetim), 1)
        self.assertNotIn("data-oturum", yetim[0])

    def test_sol_taraf_sohbet_ve_onay_icermez(self):
        sol = self.html.replace(self.panel, "")
        for s in ("KARAR-A1", "SOHBET-C", "Seni bekleyen sohbetler"):
            self.assertNotIn(s, sol)

    def test_claude_bekleyen_sohbet_bekleme_metni_yok(self):
        b = [k for k in re.findall(r'<article class="oge insan-kart.*?</article>', self.panel, re.S) if "SOHBET-B" in k][0]
        self.assertNotIn("ik-bekleme", b)


@unittest.skipUnless(shutil.which("node"), "node yok")
class BosPanel(unittest.TestCase):
    def test_bos_panel_mesaji(self):
        html = _calistir([], [])
        self.assertIn("Senden karar beklenmiyor", _panel(html))


if __name__ == "__main__":
    unittest.main()
