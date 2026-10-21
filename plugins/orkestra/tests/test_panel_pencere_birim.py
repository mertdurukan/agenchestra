"""I-137 P3: panel v2'de pencere (Bugün / Son 3 gün / Son 7 gün / Bu ay) ve birim (USD / Token) seçimi her sayfada tutarlı uygulanır.

İki kapı:
- Statik: app.js'te biçimleyici (B.usd, B.token) yalnız B nesnesinin içinde çağrılır; sabit '$' yoktur.
- Çalışma: sahte tarayıcıda (panel_duman.js) 7 görünüm x 5 pencere (Tümü dahil) x 2 birim çizilir. Her pencerenin her ailesi ayrı sayıya sahiptir:
  seçili pencerenin sayısı seçili birimde görünür, başka pencerenin sayısı ve tüm-zaman sayacı hiçbir yerde görünmez.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
APP = os.path.join(KOK, "assets", "app.js")
DUMAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_duman.js")
SECILEBILIR = ["bugun", "son_3_gun", "son_7_gun", "bu_ay", "tum_zaman"]   # Tümü dahil
TUM = SECILEBILIR
GUN = {"bugun": 1, "son_3_gun": 3, "son_7_gun": 7, "bu_ay": 20, "tum_zaman": 40}
ISO = "2026-10-18T10:00:00+03:00"

# aile -> değer: a = 100*(aile+1) + 11*(pencere sırası+1); usd = a,25 ; token = a bin
# 0 ozet.maliyet.pencere   1 ozet.kartlar (Gelen)   2 isler.json iş   3 iş kovası kart   4 teknik iş kartı
# 5 Koşular satırı / Maliyet israf   6 en pahalı   7 basamak ve kart başı   8 model ve süreç
ROTA_AILE = {"gelen": [0, 1], "isler": [2], "is": [2, 3, 4], "kosular": [5], "maliyet": [0, 5, 6, 7, 8], "kart": [], "kurallar": []}
ROTA_HASH = {"gelen": "#/gelen", "isler": "#/isler", "is": "#/is/I-1", "kosular": "#/kosular", "kart": "#/kart/G-1", "maliyet": "#/maliyet", "kurallar": "#/kurallar"}
KOVA_SAYI = {"ozet_kart": 987, "is": 876, "teknik_kart": 765, "kova": 654, "bugun": 543, "ay": 432, "birim": 321, "medyan": 210}


def _a(f, i):
    return 100 * (f + 1) + 11 * (i + 1)


def usd_s(f, i):
    return "$%d,25" % _a(f, i)


def tok_s(f, i):
    return "%d K" % _a(f, i)


def _pen(f):
    return {w: {"usd": _a(f, i) + 0.25, "token": _a(f, i) * 1000} for i, w in enumerate(TUM)}


def _sifir():
    return {w: {"usd": 0.0, "token": 0} for w in TUM}


def fixture():
    ozet_pencere = {}
    for i, w in enumerate(TUM):
        ozet_pencere[w] = {"usd": _a(0, i) + 0.25, "token": _a(0, i) * 1000, "gun": GUN[w],
                           "onceki": None if w == "tum_zaman" else {"usd": (_a(0, i) + 0.25) / 2, "token": _a(0, i) * 500},
                           "surec": {"surec-" + w: _a(8, i) + 0.25}, "model": {"model-" + w: _a(8, i) + 0.25},
                           "surec_token": {"surec-" + w: _a(8, i) * 1000}, "model_token": {"model-" + w: _a(8, i) * 1000}}
    gunluk = [{"donem": "2026-09-%02d" % d if d <= 30 else "2026-10-01", "usd": 0.5, "token": 500, "model": {"sonnet": 0.5}, "model_token": {"sonnet": 500}}
              for d in range(1, 31)]
    saatlik = [{"donem": "%02d" % h, "usd": 0.25, "token": 250, "model": {"sonnet": 0.25}, "model_token": {"sonnet": 250}} for h in range(24)]
    olculer = {
        "ana_ajan_payi": {w: {"deger": 0.41 + 0.01 * i, "hedef": 0.3, "durum": "kotu", "tur": "ust", "ornek": 5} for i, w in enumerate(TUM)},
        "isci_cagrisi_kart": {w: {"deger": 2.5, "hedef": 3.0, "durum": "iyi", "tur": "ust", "ornek": 5} for w in TUM},
        "onayli_kart_usd": {w: {"deger": 5.5 + i, "hedef": 4.0, "durum": "kotu", "tur": "ust", "ornek": 5} for i, w in enumerate(TUM)},
        "ret_orani": {w: {"deger": 0.1, "hedef": 0.2, "durum": "iyi", "tur": "ust", "ornek": 5} for w in TUM},
        "teknik_not_kapsama": {w: {"deger": 0.9, "hedef": 0.8, "durum": "iyi", "tur": "alt", "ornek": 5} for w in TUM},
    }
    ozet_akis = lambda i: {"kart": 3, "toplam_medyan": 61 + i, "toplam_ort": 61 + i, "kuyruk_medyan": 5, "kuyruk_uzun": 0, "uzun_esik_dk": 30, "darbogaz": "is"}
    pencere = {}
    for i, w in enumerate(TUM):
        pencere[w] = {"kart_sayisi": 3,
                      "birim": {"kart_basi": _a(7, i) + 0.25, "kart_medyan": _a(7, i) + 0.25, "teslim_kart": 4,
                                "kart_basi_token": _a(7, i) * 1000, "kart_medyan_token": _a(7, i) * 1000},
                      "en_pahali": [["G-9", _a(6, i) + 0.25]], "en_pahali_token": [["G-9", _a(6, i) * 1000]],
                      "basamak": [{"basamak": "T2", "kart": 3, "ilk_gecis_orani": 0.5, "ret_orani": 0.1, "kart_basi_usd": _a(7, i) + 0.25, "kart_basi_token": _a(7, i) * 1000}],
                      "akis_ozet": ozet_akis(i)}
    israf = {w: {"onlenebilir_usd": _a(5, i) + 0.25, "onlenebilir_token": _a(5, i) * 1000} for i, w in enumerate(TUM)}
    sent = lambda n: n + 0.65
    kart_a = {"id": "G-1", "baslik": "Koşu kartı", "basamak": "T2", "durum": "teslim", "olusturma": ISO, "toplam_dk": 33, "kuyruk_dk": 3, "is_dk": 20,
              "denetim_toplam_dk": 10, "pencere": _pen(5), "penceresi": list(TUM)}
    kart_b = {"id": "G-2", "baslik": "ESKI-KART-B", "basamak": "T1", "durum": "teslim", "olusturma": ISO, "toplam_dk": 40, "kuyruk_dk": 4, "is_dk": 26,
              "denetim_toplam_dk": 10, "pencere": _sifir(), "penceresi": ["bu_ay", "tum_zaman"]}
    return {
        "/alanlar.json": [{"id": "a1", "ad": "proje", "orkestra": True}],
        "/onaylar.json": {"kayitlar": [], "sayac": {"uygulanacak": 0}},
        "/simdi.json": {"oturumlar": [], "sayac": {"claude": 1}},
        "/kurallar.json": {"etkin": [{"id": "K-1", "katman": "plugin", "metin": "Bir kural cümlesi burada yazılı olsun ve yeterince uzun.", "guncelleme": ISO}], "oneriler": [], "gecmis": []},
        "/ozet.json": {
            "acik": True, "orkestra": True, "sayac": {},
            "kartlar": [{"id": "G-1", "baslik": "Takılı kart", "durum": "isleniyor", "basamak": "T2", "isci": 2, "usd": sent(KOVA_SAYI["ozet_kart"]),
                         "token": KOVA_SAYI["ozet_kart"] * 1000, "guncelleme": ISO, "pencere": _pen(1)}],
            "maliyet": {"bugun": sent(KOVA_SAYI["bugun"]), "bugun_token": KOVA_SAYI["bugun"] * 1000, "toplam": 1.0, "toplam_token": 1,
                        "surec": {"SENT-S": sent(321)}, "model": {"SENT-M": sent(321)}, "surec_token": {"SENT-S": 321000}, "model_token": {"SENT-M": 321000},
                        "pencere": ozet_pencere},
        },
        "/analitik.json": {
            "trend": {"gunluk": gunluk, "saatlik": saatlik,
                      "ay_sonu": {"ay": "2026-10", "simdiye": sent(KOVA_SAYI["ay"]), "gecen_gun": 20, "ay_gun": 31, "veri_gun": 20, "gunluk_ort": 21.6,
                                  "tahmin_ort": 4321.5, "tahmin_yeterli": True,
                                  "token": {"simdiye": KOVA_SAYI["ay"] * 1000, "tahmin_ort": 4321000, "tahmin_7g": None, "onceki_ay": None}}},
            "akis": {"kartlar": [kart_a, kart_b], "ozet": {"kart": 99, "toplam_medyan": 500, "toplam_ort": 500, "kuyruk_medyan": 5, "kuyruk_uzun": 0, "uzun_esik_dk": 30, "darbogaz": "is"}},
            "birim": {"kart_maliyetleri": [["G-1", sent(KOVA_SAYI["birim"])]], "kart_medyan": sent(KOVA_SAYI["medyan"]), "kart_basi": sent(KOVA_SAYI["medyan"]), "teslim_kart": 5},
            "basamak": {"satirlar": [{"basamak": "SENT-B", "kart": 1, "ilk_gecis_orani": 0.5, "ret_orani": 0.1, "kart_basi_usd": sent(210)}]},
            "hedef_panosu": {"olculer": olculer, "israf": israf},
            "pencere": pencere,
        },
        "/isler.json": {"isler": [{
            "id": "I-1", "ad": "İş bir", "durum": "acik", "usd": sent(KOVA_SAYI["is"]), "token": KOVA_SAYI["is"] * 1000, "pencere": _pen(2), "son": ISO,
            "ilerleme": {"toplam": 4, "biten": 2}, "klasor": "x/y",
            "kovalar": {"simdi": [{"tur": "kart", "kart": "G-1", "basamak": "T2", "metin": "kart metni", "usd": sent(KOVA_SAYI["kova"]),
                                   "token": KOVA_SAYI["kova"] * 1000, "pencere": _pen(3)}]}}],
            "kartsiz": {"acik": []}},
        "/teknik.json?is=I-1": {"kartlar": [{"id": "G-1", "baslik": "Kart", "sinif": "kod", "basamak": "T2", "durum": "teslim", "denetim": "onay", "sure": 60,
                                             "usd": sent(KOVA_SAYI["teknik_kart"]), "token": KOVA_SAYI["teknik_kart"] * 1000, "pencere": _pen(4)}]},
        "/api/todo?is=I-1": {"acik_maddeler": ["a"], "biten_maddeler": ["b"]},
        "/teknik.json?kart=G-1": {
            "ne": {"baslik": "Kart", "basamak": "T2", "sinif": "kod", "kabul_kriterleri": [], "ciktilar": []}, "neden": {"is": "I-1"},
            "maliyet_sure": {"toplam_usd": 88.75, "toplam_token": 88000, "sureler": {"kuyruk_sn": 60, "is_sn": 120, "denetim_sn": 30},
                             "maliyet": [{"ajan": "orkestra:isci-t2", "model": "claude-sonnet-5-5", "usd": 88.75, "token": 88000}]},
            "dogrulama": {"denetimler": [], "test_kosulari": [], "onkontrol_kosulari": []}, "degisen": {"dosyalar": []}, "ogrenilen": {}, "nasil": {}},
    }


def kaynak_b_disi() -> str:
    s = open(APP, encoding="utf-8").read()
    bas = s.index("  const B = {")
    son = s.index("\n  };\n", bas) + len("\n  };\n")
    return s[:bas] + s[son:]


class KacakKapisiStatik(unittest.TestCase):
    def test_bicimleyici_yalniz_b_icinde_cagrilir(self):
        kalan = kaynak_b_disi()
        bulunan = sorted(set(re.findall(r"\bB\.(?:usd|token|deger)\(", kalan)))
        self.assertEqual(bulunan, [], "ham biçimleyici çağrısı birim/pencere seçimini atlar: B.para / B.paraP kullan")

    def test_sabit_dolar_yok(self):
        kalan = kaynak_b_disi()
        # ${…} şablon ifadesi ve düzenli ifade sonu ($/ ve $)) dışındaki her '$' para simgesi sayılır
        self.assertEqual(re.findall(r".{12}\$(?![{/)]).{6}", kalan), [], "sabit '$' token modunda sızar")


def _senaryolar():
    s = []
    for r, h in ROTA_HASH.items():
        for w in SECILEBILIR:
            for o in ("usd", "token"):
                s.append({"anahtar": [r, w, o], "depo": {"orkestra.v2.pencere": w, "orkestra.olcu": o}, "hash": h})
    return s


def _kos(senaryolar):
    with tempfile.TemporaryDirectory() as t:
        yollar = {a: os.path.join(t, a + ".json") for a in ("fx", "sn", "cikti")}
        json.dump(fixture(), open(yollar["fx"], "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(senaryolar, open(yollar["sn"], "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.run(["node", DUMAN, APP, yollar["fx"], yollar["sn"], yollar["cikti"]], check=True, timeout=180)
        return json.load(open(yollar["cikti"], encoding="utf-8"))


def _metin(c):
    return c["ray"] + c["bas"] + c["ana"]


def _bicim_dugmesi_at(html: str) -> str:
    return re.sub(r'<button[^>]*data-eylem="olcu"[^>]*>.*?</button>', "", html, flags=re.S)


@unittest.skipUnless(shutil.which("node"), "node yok")
class KacakKapisiCalisma(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sn = _senaryolar()
        cikti = _kos(sn)
        cls.hatalar = cikti["hatalar"]
        cls.sonuc = {tuple(s["anahtar"]): c for s, c in zip(sn, cikti["sonuc"])}

    def test_calisma_hatasi_yok(self):
        self.assertEqual(self.hatalar, [])
        self.assertEqual(len(self.sonuc), len(ROTA_HASH) * len(SECILEBILIR) * 2)

    def test_secili_pencere_ve_birim_her_sayfada(self):
        for (r, w, o), c in self.sonuc.items():
            i = TUM.index(w)
            html = _metin(c)
            with self.subTest(rota=r, pencere=w, birim=o):
                for f in ROTA_AILE[r]:
                    benim, yanlis = (usd_s(f, i), tok_s(f, i)) if o == "usd" else (tok_s(f, i), usd_s(f, i)[1:])
                    self.assertIn(benim, html, "aile %d: seçili pencerenin değeri yok" % f)
                    self.assertNotIn(yanlis, html, "aile %d: öteki birimin değeri görünüyor" % f)
                    for j, w2 in enumerate(TUM):
                        if j != i:
                            self.assertNotIn(usd_s(f, j)[1:], html, "aile %d: %s penceresi sızıyor" % (f, w2))
                            self.assertNotIn(tok_s(f, j), html, "aile %d: %s penceresi sızıyor" % (f, w2))
                for f in set(range(9)) - set(ROTA_AILE[r]):
                    for j in range(5):
                        self.assertNotIn(usd_s(f, j)[1:], html, "aile %d bu sayfada olmamalı" % f)
                        self.assertNotIn(tok_s(f, j), html, "aile %d bu sayfada olmamalı" % f)

    def test_tum_zaman_sayaclari_gorunmez(self):
        for (r, w, o), c in self.sonuc.items():
            html = _metin(c)
            with self.subTest(rota=r, pencere=w, birim=o):
                for ad, n in KOVA_SAYI.items():
                    self.assertNotIn("%d,65" % n, html, ad + " (tüm zaman USD) sızıyor")
                    self.assertNotIn("%d K" % n, html, ad + " (tüm zaman token) sızıyor")
                for ad in ("SENT-S", "SENT-M", "SENT-B"):
                    self.assertNotIn(ad, html)

    def test_token_modunda_dolar_ve_usd_yok(self):
        izinli = re.compile(r"Onaylı kart başına USD|[\d.,]+ USD")
        for (r, w, o), c in self.sonuc.items():
            if o != "token":
                continue
            html = izinli.sub("", _bicim_dugmesi_at(_metin(c)))
            with self.subTest(rota=r, pencere=w):
                self.assertNotIn("$", html)
                self.assertNotIn("USD", html)

    def test_usd_modunda_token_basligi_yok(self):
        for (r, w, o), c in self.sonuc.items():
            if o == "usd" and r in ("isler", "is", "kosular", "maliyet", "kart"):
                with self.subTest(rota=r, pencere=w):
                    self.assertNotRegex(_bicim_dugmesi_at(c["ana"]), r"\bToken\b")

    def test_ust_cubuk_kontrolleri(self):
        for (r, w, o), c in self.sonuc.items():
            bas = c["bas"]
            with self.subTest(rota=r, pencere=w, birim=o):
                if r == "kurallar":
                    self.assertNotIn('data-eylem="pencere"', bas)
                    self.assertNotIn('data-eylem="olcu"', bas)
                    continue
                self.assertIn('data-eylem="olcu" data-v="%s" aria-pressed="true"' % o, bas)
                self.assertIn('data-eylem="olcu" data-v="%s" aria-pressed="false"' % ("token" if o == "usd" else "usd"), bas)
                if r == "kart":
                    self.assertIn("tüm ömrü", bas)
                    self.assertRegex(bas, r'data-eylem="pencere"[^>]*disabled')
                else:
                    self.assertIn('data-eylem="pencere" data-v="%s" aria-pressed="true"' % w, bas)
                    self.assertEqual(bas.count('data-eylem="pencere"'), 5)
                    self.assertEqual(len(re.findall(r'data-eylem="pencere"[^>]*aria-pressed="true"', bas)), 1)

    def test_kart_izi_birimi_izler(self):
        for (r, w, o), c in self.sonuc.items():
            if r == "kart":
                with self.subTest(pencere=w, birim=o):
                    html = _metin(c)
                    self.assertIn("88,75" if o == "usd" else "88 K", html)
                    self.assertNotIn("88 K" if o == "usd" else "88,75", html)

    def test_hedef_olculeri_secili_pencereyi_izler(self):
        for (r, w, o), c in self.sonuc.items():
            if r not in ("gelen", "maliyet"):
                continue
            i = TUM.index(w)
            html = _metin(c)
            with self.subTest(rota=r, pencere=w, birim=o):
                self.assertIn("%%%d" % (41 + i), html)
                self.assertIn(("$%d,50" % (5 + i)) if o == "usd" else ("%d,50 USD" % (5 + i)), html, "onaylı kart başına USD hep USD kalır")
                for j in range(5):
                    if j != i:
                        self.assertNotIn("%%%d" % (41 + j), html)
                        self.assertNotIn("%d,50" % (5 + j), html)

    def test_kosular_penceredeki_kartlari_listeler(self):
        for (r, w, o), c in self.sonuc.items():
            if r == "kosular":
                with self.subTest(pencere=w, birim=o):
                    self.assertIn("Koşu kartı", c["ana"])
                    self.assertEqual("ESKI-KART-B" in c["ana"], w in ("bu_ay", "tum_zaman"))
                    i = TUM.index(w)
                    self.assertIn("1 sa %d dk" % (1 + i), c["ana"], "akış karoları pencereden gelmeli")
                    self.assertNotIn("8 sa 20 dk", c["ana"])


@unittest.skipUnless(shutil.which("node"), "node yok")
class DurumKalicilik(unittest.TestCase):
    def kos(self, adimlar_listesi):
        sn = []
        for depo, hash_, adimlar in adimlar_listesi:
            sn.append({"depo": depo, "hash": hash_, "adimlar": adimlar})
        c = _kos(sn)
        self.assertEqual(c["hatalar"], [])
        return c["sonuc"]

    def test_tik_tus_derin_baglanti(self):
        bos = {"orkestra.v2.pencere": None, "orkestra.olcu": None}
        r = self.kos([
            (bos, "#/maliyet", []),
            (bos, "#/maliyet", [["tikla", "pencere", {"v": "bugun"}]]),
            ({}, "#/maliyet", [["tikla", "olcu", {"v": "token"}]]),
            ({}, "#/maliyet", [["tus", "p"]]),
            ({}, "#/maliyet", [["tus", "u"]]),
            ({"orkestra.v2.pencere": "bugun"}, "#/maliyet?p=son_7_gun", []),
            ({}, "#/gelen", []),
            ({"orkestra.v2.pencere": "bozuk"}, "#/gelen", []),
        ])
        # varsayılan: Son 3 gün, USD
        self.assertIn(usd_s(0, 1), r[0]["ana"])
        # tıklama: kalıcı ve yeniden çizim
        self.assertEqual(r[1]["depo"]["orkestra.v2.pencere"], "bugun")
        self.assertIn(usd_s(0, 0), r[1]["ana"])
        # birim klasik sayfalarla ortak anahtarda
        self.assertEqual(r[2]["depo"]["orkestra.olcu"], "token")
        self.assertIn(tok_s(0, 0), r[2]["ana"])
        # p: pencereyi sırayla değiştirir, u: birimi çevirir
        self.assertEqual(r[3]["depo"]["orkestra.v2.pencere"], "son_3_gun")
        self.assertEqual(r[4]["depo"]["orkestra.olcu"], "usd")
        # ?p= derin bağlantı seçimi uygular, saklar, adresten çıkarır
        self.assertEqual(r[5]["depo"]["orkestra.v2.pencere"], "son_7_gun")
        self.assertNotIn("p=", r[5]["hash"])
        self.assertIn(usd_s(0, 2), r[5]["ana"])
        # seçim sayfalar arasında kalıcı
        self.assertIn(usd_s(0, 2), r[6]["ana"])
        # bozuk saklı değer varsayılana düşer
        self.assertIn(usd_s(0, 1), r[7]["ana"])


if __name__ == "__main__":
    unittest.main()
