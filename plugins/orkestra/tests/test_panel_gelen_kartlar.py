"""I-145 P4: Gelen kutusu kartları üç gruba ayırır (teslim bekleyen / sahipsiz / takılan); arşivli sahibe 'Sohbeti aç' çıkmaz."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import test_panel_pencere_birim as TPB

ISO = TPB.ISO


def _kart(kimlik, baslik, durum, **ek):
    return {"id": kimlik, "baslik": baslik, "durum": durum, "basamak": "T2", "isci": 1, "usd": 1.0, "token": 1000,
            "guncelleme": ISO, "pencere": TPB._pen(1), "oturum": "oturum-a", "son_oturum": "oturum-a",
            "sahip_arsivli": False, "is": "I-3", **ek}


def _calistir(kartlar):
    fx = TPB.fixture()
    fx["/ozet.json"]["kartlar"] = kartlar
    senaryo = [{"anahtar": ["gelen"], "depo": {}, "hash": "#/gelen"}]
    with tempfile.TemporaryDirectory() as t:
        yollar = {a: os.path.join(t, a + ".json") for a in ("fx", "sn", "cikti")}
        json.dump(fx, open(yollar["fx"], "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(senaryo, open(yollar["sn"], "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.run(["node", TPB.DUMAN, TPB.APP, yollar["fx"], yollar["sn"], yollar["cikti"]], check=True, timeout=180)
        cikti = json.load(open(yollar["cikti"], encoding="utf-8"))
    assert cikti["hatalar"] == [], cikti["hatalar"]
    return TPB._metin(cikti["sonuc"][0])


def _grup(html, baslik):
    """Başlıktan sonraki bölümün HTML'i (bir sonraki gelen-grup başlığına kadar)."""
    m = re.search(r"<section class=\"gelen-grup\"><h2>" + re.escape(baslik) + r".*?(?=<section class=\"gelen-grup\">|$)", html, re.S)
    return m.group(0) if m else ""


@unittest.skipUnless(shutil.which("node"), "node yok")
class GelenKartGruplari(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _calistir([
            _kart("G-1", "TAKILI-KART", "isleniyor"),
            _kart("G-2", "ONAYLI-KART", "onaylandi"),
            _kart("G-3", "SAHIPSIZ-KART", "isleniyor", sahip_arsivli=True, oturum="arsivli-oturum", son_oturum="arsivli-oturum"),
            _kart("G-4", "ONAYLI-SAHIPSIZ", "onaylandi", sahip_arsivli=True, oturum="arsivli-oturum", son_oturum="arsivli-oturum"),
            _kart("G-5", "TESLIM-KART", "teslim"),
        ])

    def test_uc_grup_ve_kart_yerlesimi(self):
        takili, teslim, sahipsiz = _grup(self.html, "Takılan kartlar"), _grup(self.html, "Teslim bekleyen kartlar"), _grup(self.html, "Sahipsiz kartlar")
        self.assertIn("TAKILI-KART", takili)
        self.assertNotIn("ONAYLI-KART", takili)
        self.assertIn("ONAYLI-KART", teslim)
        self.assertIn("ONAYLI-SAHIPSIZ", teslim)          # onaylı kart arşivli sahipli olsa da teslim bekliyor (eylem teslim)
        self.assertIn("SAHIPSIZ-KART", sahipsiz)
        self.assertNotIn("SAHIPSIZ-KART", takili)
        self.assertNotIn("TESLIM-KART", self.html)

    def test_arsivli_sahibe_sohbeti_ac_yok_diger_kartta_var(self):
        sahipsiz = _grup(self.html, "Sahipsiz kartlar")
        self.assertNotIn("Sohbeti aç", sahipsiz)
        self.assertNotIn("arsivli-oturum", sahipsiz)
        self.assertIn("orkestra is devam I-3", sahipsiz)
        self.assertIn("Sohbeti aç", _grup(self.html, "Takılan kartlar"))
        self.assertIn('data-oturum="oturum-a"', _grup(self.html, "Takılan kartlar"))

    def test_son_oturum_oluşturandan_önce_gelir(self):
        html = _calistir([_kart("G-1", "SAHIP-DEGISTI", "isleniyor", oturum="eski-oturum", son_oturum="yeni-oturum")])
        self.assertIn('data-oturum="yeni-oturum"', html)
        self.assertNotIn("eski-oturum", html)


if __name__ == "__main__":
    unittest.main()
