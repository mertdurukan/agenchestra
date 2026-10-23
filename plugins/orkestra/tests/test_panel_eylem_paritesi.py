"""Panel eylem eşitliği (ADR-0081, I-217): sunucunun her POST ucu yeni arayüze (assets/app.js) bağlı ya da gerekçeli istisna.

Kök neden: 'İşi kapat' yalnız klasik /isler sayfasına yazıldı, yeni arayüz (#/is/<id>) düğmeyi taşımadı ve iki arayüzün
eylem eşitliğini denetleyen bir şey yoktu. Yeni POST ucu eklenince bu test, ucun app.js'e bağlanmasını ya da bilinçli
istisna olarak gerekçelenmesini zorlar.

Kriterler:
  K1  panel.py _post_isle içindeki her POST yolu app.js'te gonder/urlAl/fetch çağrısında geçer ya da İSTISNA'da durur.
  K2  İSTISNA satırı gerekçe taşır, gerçek bir POST yoludur ve app.js'te bağlı değildir (bayat istisna kırmızı).
  K3  İhlal vakaları: bağlantı çıkarılırsa, yol yalnız yorumda geçerse, istisna gerekçesiz olursa test kırmızıdır.
"""
import os
import re
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(AD)
PANEL = os.path.join(KOK, "scripts", "panel.py")
APP_JS = os.path.join(KOK, "assets", "app.js")

# yol -> gerekçe. Yalnız bilinçli kararla büyür.
ISTISNA = {
    "/api/isler-sifirla": "yıkıcı eylem; yalnız klasik /isler sayfasında, yeni arayüze alınması kullanıcı kararı",
    "/api/kural-dosya": "kural dosyası düzenleme klasik /onaylar sayfasında; yeni arayüzde yalnız bağlantı var",
    "/api/todo": "POST 405 döner (iş todo listeleri salt okunur); istemci GET kullanır",
}

CAGRI = r"(?:gonder|urlAl|fetch)\(\s*"
TIRNAK = "['\"`]"


def post_yollari(panel_kaynak):
    """_post_isle gövdesindeki `u.path` karşılaştırmalarında geçen yol sabitleri."""
    bas = panel_kaynak.index("def _post_isle")
    son = panel_kaynak.find("\n        def ", bas + 1)
    govde = panel_kaynak[bas:son if son != -1 else None]
    yollar = set()
    for satir in govde.splitlines():
        if "u.path" in satir:
            yollar.update(re.findall(r'"(/[^"]*)"', satir))
    return yollar


def yorumsuz(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)(^|\s)//[^\n]*", r"\1", js)


def bagli_mi(yol, js):
    """Yol, gonder/urlAl/fetch çağrısında doğrudan ya da bu çağrıda kullanılan bir sabit üzerinden geçiyor mu."""
    js = yorumsuz(js)
    y = re.escape(yol)
    if re.search(CAGRI + TIRNAK + y + "['\"`?]", js):
        return True
    for ad in re.findall(r"(?:const|let|var)\s+(\w+)\s*=\s*" + TIRNAK + y + "['\"`?]", js):
        if re.search(CAGRI + re.escape(ad) + r"\b", js):
            return True
    return False


def eksikler(yollar, js, istisna):
    """(bağlı olmayan ve istisnada olmayan yollar, istisna kusurları)."""
    baglanmamis = sorted(y for y in yollar if y not in istisna and not bagli_mi(y, js))
    kusur = []
    for y, neden in istisna.items():
        if not str(neden).strip():
            kusur.append(f"{y}: gerekçe boş")
        if y not in yollar:
            kusur.append(f"{y}: panel.py'de POST yolu değil (bayat istisna)")
        if bagli_mi(y, js):
            kusur.append(f"{y}: app.js'te bağlı, istisnadan çıkarılmalı")
    return baglanmamis, kusur


class EylemParitesi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PANEL, encoding="utf-8") as f:
            cls.yollar = post_yollari(f.read())
        with open(APP_JS, encoding="utf-8") as f:
            cls.js = f.read()

    def test_k1_k2_her_post_yolu_bagli_ya_da_istisna(self):
        baglanmamis, kusur = eksikler(self.yollar, self.js, ISTISNA)
        bagli = sum(1 for y in self.yollar if y not in ISTISNA)
        print(f"{len(self.yollar)} POST yolu: {bagli} app.js'te, {len(ISTISNA)} istisna")
        self.assertEqual(baglanmamis, [], "app.js'e bağlanmamış POST yolu: bağla ya da ISTISNA'ya gerekçeyle ekle")
        self.assertEqual(kusur, [])

    def test_yol_sayisi_makul(self):
        self.assertIn("/api/is-kapat", self.yollar)
        self.assertGreaterEqual(len(self.yollar), 10)

    def test_k3_baglanti_cikarilirsa_kirmizi(self):
        js = self.js.replace("'/api/is-kapat'", "'/api/baska'")
        baglanmamis, _ = eksikler(self.yollar, js, ISTISNA)
        self.assertIn("/api/is-kapat", baglanmamis)

    def test_k3_yalniz_yorumda_gecen_yol_baglanti_sayilmaz(self):
        js = self.js.replace("'/api/is-kapat'", "'/api/baska'") + "\n// gonder('/api/is-kapat', {})\n/* gonder('/api/is-kapat') */"
        baglanmamis, _ = eksikler(self.yollar, js, ISTISNA)
        self.assertIn("/api/is-kapat", baglanmamis)

    def test_k3_gerekcesiz_istisna_kirmizi(self):
        _, kusur = eksikler(self.yollar, self.js, {**ISTISNA, "/api/isler-sifirla": "  "})
        self.assertTrue(any("gerekçe boş" in k for k in kusur))

    def test_k3_bayat_istisna_kirmizi(self):
        _, kusur = eksikler(self.yollar, self.js, {**ISTISNA, "/api/yok-boyle-bir-yol": "x"})
        self.assertTrue(any("bayat" in k for k in kusur))


if __name__ == "__main__":
    unittest.main()
