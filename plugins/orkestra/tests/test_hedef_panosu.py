"""G-138: verim hedef panosu (5 ölçü, iki pencere) ve önlenebilir israf (K11)."""
import datetime
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import analitik as A  # noqa: E402
import kpi as K  # noqa: E402

OLCULER = ("ana_ajan_payi", "isci_cagrisi_kart", "onayli_kart_usd", "ret_orani", "teknik_not_kapsama")
PENCERELER = ("son_3_gun", "tum_zaman")
HEDEF = {"surum": 1, "teknik_kapi_baslangic": "2026-10-16", "pencere_gun": 3, "uyari_carpani": 1.25, "teknik_uyari_alt": 0.8,
         "olculer": {"ana_ajan_payi": {"tur": "ust", "hedef": 0.40}, "isci_cagrisi_kart": {"tur": "ust", "hedef": 2},
                     "onayli_kart_usd": {"tur": "ust", "hedef": 1.5}, "ret_orani": {"tur": "band", "alt": 0.10, "ust": 0.20},
                     "teknik_not_kapsama": {"tur": "alt", "hedef": 1.0}}}
ESIK = {"surum": 7, "ret_sinifi": {"kapsam-eksik": "onlenebilir", "kriter-belirsiz": "plan-kusuru", "talimat-ihlali": "koruyucu"},
        "israf_siniflari": ["onlenebilir"]}
SIMDI = datetime.datetime(2026, 10, 16, 12, 0, tzinfo=datetime.timezone.utc).astimezone()


def z(gun_once=0, saat=0):
    return (SIMDI - datetime.timedelta(days=gun_once, hours=saat)).isoformat(timespec="seconds")


def kart(id_, olus=None, durum="teslim", isciler=1, teknik=None, denetimler=None, turlar=None):
    k = {"id": id_, "durum": durum, "olusturma": olus or z(0, 1), "isciler": ["a%d" % i for i in range(isciler)],
         "denetimler": denetimler or [], "is_turlari": turlar or [], "gecmis": []}
    if teknik is not None:
        k["teknik"] = teknik
    return k


def pano(kartlar, kayitlar=(), esik=None):
    return A.hedef_panosu(list(kartlar), list(kayitlar), simdi=SIMDI, hedef=HEDEF, esik=esik or ESIK)


class K1Yapi(unittest.TestCase):
    def test_bes_olcu_iki_pencere_dort_alan(self):
        k = kart("G-1", denetimler=[{"karar": "onay", "sira": 2}])
        r = [{"zaman": z(0, 2), "gorev": "G-1", "maliyet_usd": 1.0, "agent_id": "a0"}, {"zaman": z(0, 2), "gorev": "-", "maliyet_usd": 0.5}]
        p = pano([k], r)
        self.assertEqual(set(p["olculer"]), set(OLCULER))
        for o in OLCULER:
            for w in PENCERELER:
                e = p["olculer"][o][w]
                for alan in ("deger", "hedef", "durum", "ornek"):
                    self.assertIn(alan, e, (o, w, alan))
                self.assertIn(e["durum"], ("iyi", "uyari", "kotu", "veri-yok"))
        self.assertAlmostEqual(p["olculer"]["ana_ajan_payi"]["tum_zaman"]["deger"], 0.5 / 1.5, places=3)
        self.assertEqual(p["olculer"]["isci_cagrisi_kart"]["tum_zaman"]["deger"], 1.0)
        self.assertEqual(p["olculer"]["onayli_kart_usd"]["tum_zaman"]["deger"], 1.0)

    def test_pencereler_ayrisir(self):
        eski = kart("G-1", olus=z(10), isciler=6)
        yeni = kart("G-2", olus=z(0, 1), isciler=1)
        p = pano([eski, yeni])
        self.assertEqual(p["olculer"]["isci_cagrisi_kart"]["son_3_gun"]["deger"], 1.0)
        self.assertEqual(p["olculer"]["isci_cagrisi_kart"]["tum_zaman"]["deger"], 3.5)
        self.assertEqual(p["olculer"]["isci_cagrisi_kart"]["son_3_gun"]["ornek"], 1)

    def test_alan_analitigi_cikti_anahtari(self):
        with tempfile.TemporaryDirectory() as d:
            sd = os.path.join(d, ".claude", "orkestra")
            os.makedirs(os.path.join(sd, "gorevler"))
            with open(os.path.join(sd, "gorevler", "G-001.json"), "w", encoding="utf-8") as f:
                json.dump(kart("G-001"), f)
            alan = {"id": "x", "ad": "x", "yol": d, "orkestra": True}
            with mock.patch.object(A, "_alan_listesi", return_value=[alan]), \
                    mock.patch.object(A.L, "sohbetler", return_value=[]):
                o = A.alan_analitigi("x")
        self.assertIn("hedef_panosu", o)
        self.assertEqual(set(o["hedef_panosu"]["olculer"]), set(OLCULER))
        self.assertEqual(set(o["hedef_panosu"]["olculer"]["ret_orani"]), set(PENCERELER))


class K2Sinirlar(unittest.TestCase):
    def test_bos_veri_veri_yok(self):
        p = pano([], [])
        for o in OLCULER:
            for w in PENCERELER:
                e = p["olculer"][o][w]
                self.assertEqual(e["durum"], "veri-yok", (o, w))
                self.assertIsNone(e["deger"])

    def test_payda_sifir_bolme_hatasi_yok(self):
        # kart var ama denetim, onaylı kart ve defter yok
        p = pano([kart("G-1", durum="planlandi")], [])
        self.assertEqual(p["olculer"]["ret_orani"]["tum_zaman"]["durum"], "veri-yok")
        self.assertEqual(p["olculer"]["onayli_kart_usd"]["tum_zaman"]["durum"], "veri-yok")
        self.assertEqual(p["olculer"]["ana_ajan_payi"]["tum_zaman"]["durum"], "veri-yok")
        self.assertEqual(p["olculer"]["teknik_not_kapsama"]["tum_zaman"]["durum"], "veri-yok")

    def test_sinir_degerleri(self):
        vaka = [
            ("ana_ajan_payi", 0.40, "iyi"), ("ana_ajan_payi", 0.41, "uyari"), ("ana_ajan_payi", 0.50, "uyari"),
            ("ana_ajan_payi", 0.51, "kotu"), ("ana_ajan_payi", 0.0, "iyi"),
            ("isci_cagrisi_kart", 2, "iyi"), ("isci_cagrisi_kart", 2.1, "uyari"), ("isci_cagrisi_kart", 2.5, "uyari"),
            ("isci_cagrisi_kart", 2.6, "kotu"),
            ("onayli_kart_usd", 1.5, "iyi"), ("onayli_kart_usd", 1.51, "uyari"), ("onayli_kart_usd", 1.875, "uyari"),
            ("onayli_kart_usd", 1.9, "kotu"),
            ("ret_orani", 0.10, "iyi"), ("ret_orani", 0.20, "iyi"), ("ret_orani", 0.15, "iyi"),
            ("ret_orani", 0.0999, "uyari"), ("ret_orani", 0.2001, "kotu"), ("ret_orani", 0.0, "uyari"),
            ("teknik_not_kapsama", 1.0, "iyi"), ("teknik_not_kapsama", 0.99, "uyari"), ("teknik_not_kapsama", 0.8, "uyari"),
            ("teknik_not_kapsama", 0.79, "kotu"), ("teknik_not_kapsama", 0.0, "kotu"),
        ]
        for ad, deger, beklenen in vaka:
            with self.subTest(olcu=ad, deger=deger):
                durum, _ = A.olcu_durumu(deger, HEDEF["olculer"][ad])
                self.assertEqual(durum, beklenen)

    def test_band_yorumlari(self):
        sp = HEDEF["olculer"]["ret_orani"]
        self.assertEqual(A.olcu_durumu(0.05, sp), ("uyari", "gevsek-riski"))
        self.assertEqual(A.olcu_durumu(0.30, sp), ("kotu", "plan-kusuru"))
        self.assertEqual(A.olcu_durumu(0.10, sp), ("iyi", None))
        self.assertEqual(A.olcu_durumu(None, sp), ("veri-yok", None))

    def test_ret_orani_panoda_yorum(self):
        den = [{"karar": "ret", "sira": 3}] + [{"karar": "onay", "sira": 10 + i} for i in range(19)]
        e = pano([kart("G-1", denetimler=den)])["olculer"]["ret_orani"]["tum_zaman"]
        self.assertEqual(e["deger"], 0.05)
        self.assertEqual((e["durum"], e["yorum"]), ("uyari", "gevsek-riski"))


class K3TeknikKapsama(unittest.TestCase):
    def test_yalniz_kapi_sonrasi_paydada(self):
        kartlar = [
            kart("G-1", olus="2026-10-15T23:59:00+03:00", teknik=""),                 # kapıdan önce: paydada değil
            kart("G-2", olus="2026-10-16T00:00:00+03:00", teknik="not var"),          # tam sınır: paydada, dolu
            kart("G-3", olus="2026-10-16T09:00:00+03:00", teknik={"degisen": ["a"]}),  # dolu
            kart("G-4", olus="2026-10-16T10:00:00+03:00"),                              # boş (alan yok)
            kart("G-5", olus="2026-10-16T10:30:00+03:00", teknik="   "),               # boşluk = boş
            kart("G-6", olus="2026-10-16T11:00:00+03:00", teknik="x", durum="planlandi"),  # onaylı/teslim değil
        ]
        e = pano(kartlar)["olculer"]["teknik_not_kapsama"]["tum_zaman"]
        self.assertEqual(e["payda"], 4)
        self.assertEqual(e["pay"], 2)
        self.assertEqual(e["deger"], 0.5)
        self.assertEqual(e["durum"], "kotu")
        self.assertEqual(e["ornek"], 4)

    def test_kapi_oncesi_hepsi_veri_yok(self):
        e = pano([kart("G-1", olus="2026-10-10T10:00:00+03:00", teknik="")])["olculer"]["teknik_not_kapsama"]["tum_zaman"]
        self.assertEqual(e["durum"], "veri-yok")

    def test_tam_kapsama_iyi(self):
        e = pano([kart("G-1", olus="2026-10-16T10:00:00+03:00", teknik="n")])["olculer"]["teknik_not_kapsama"]["tum_zaman"]
        self.assertEqual((e["deger"], e["durum"]), (1.0, "iyi"))

    def test_ayar_dosyasinda_varsayilan_tarih(self):
        self.assertEqual(A._ayar("hedef.json")["teknik_kapi_baslangic"], "2026-10-16")


class K4Israf(unittest.TestCase):
    def kartlar(self):
        turlar = [{"sira": 3, "agent_id": "A1"}, {"sira": 7, "agent_id": "A2"}, {"sira": 12, "agent_id": "A3"}]
        den = [
            {"karar": "ret", "sira": 4, "neden": "kapsam-eksik"},      # tur A1
            {"karar": "ret", "sira": 8, "neden": "kriter-belirsiz"},   # tur A2
            {"karar": "ret", "sira": 9, "neden": "talimat-ihlali"},    # tur A2 (aynı tur, farklı sınıf)
            {"karar": "ret", "sira": 13, "neden": None},               # sınıflanmamış, tur A3
            {"karar": "ret", "sira": 14, "neden": "uydurma-kod"},      # bilinmeyen -> sınıflanmamış
        ]
        k = kart("G-1", denetimler=den, turlar=turlar)
        k["token_toplam"] = 999999
        k["maliyet_usd"] = 777.0
        return [k]

    def defter(self):
        return [{"zaman": z(0, 3), "gorev": "G-1", "agent_id": "A1", "maliyet_usd": 0.5},
                {"zaman": z(0, 3), "gorev": "G-1", "agent_id": "A1", "maliyet_usd": 0.25},
                {"zaman": z(0, 2), "gorev": "G-1", "agent_id": "A2", "maliyet_usd": 2.0},
                {"zaman": z(0, 1), "gorev": "G-1", "agent_id": "A3", "maliyet_usd": 4.0}]

    def test_tur_maliyeti_defterden_ve_siniflar(self):
        israf = pano(self.kartlar(), self.defter())["israf"]["tum_zaman"]
        s = israf["siniflar"]
        self.assertEqual(israf["esik_surumu"], 7)
        self.assertEqual(s["onlenebilir"], {"ret": 1, "usd": 0.75, "tur_bulunamadi": 0})
        self.assertEqual(s["plan-kusuru"]["usd"], 2.0)
        self.assertEqual(s["koruyucu"]["usd"], 2.0)
        self.assertEqual(s["siniflanmamis"]["ret"], 2)
        self.assertEqual(s["siniflanmamis"]["usd"], 8.0)
        # kartın kendi token/maliyet alanları (999999 / 777) kullanılmaz
        self.assertEqual(israf["onlenebilir_usd"], 0.75)

    def test_siniflanmamis_israfa_eklenmez(self):
        israf = pano(self.kartlar(), self.defter())["israf"]["tum_zaman"]
        self.assertIn("siniflanmamis", israf["siniflar"])
        self.assertNotIn(israf["onlenebilir_usd"], (8.75, 10.75, 8.0))
        self.assertEqual(israf["onlenebilir_usd"], 0.75)

    def test_onceki_en_yakin_tur_secilir(self):
        turlar = [{"sira": 1, "agent_id": "A1"}, {"sira": 5, "agent_id": "A2"}]
        k = kart("G-1", denetimler=[{"karar": "ret", "sira": 6, "neden": "kapsam-eksik"}], turlar=turlar)
        r = [{"zaman": z(0, 1), "gorev": "G-1", "agent_id": "A1", "maliyet_usd": 1.0},
             {"zaman": z(0, 1), "gorev": "G-1", "agent_id": "A2", "maliyet_usd": 3.0}]
        self.assertEqual(pano([k], r)["israf"]["tum_zaman"]["onlenebilir_usd"], 3.0)

    def test_tur_yoksa_maliyet_sayilmaz_ama_sayilir(self):
        k = kart("G-1", denetimler=[{"karar": "ret", "sira": 6, "neden": "kapsam-eksik"}], turlar=[])
        e = pano([k], [])["israf"]["tum_zaman"]["siniflar"]["onlenebilir"]
        self.assertEqual((e["ret"], e["usd"], e["tur_bulunamadi"]), (1, 0.0, 1))

    def test_esleme_dosyadan_okunur_ve_surumlu(self):
        esik = A._ayar("kpi_esikleri.json")
        self.assertIsInstance(esik.get("surum"), int)
        esl = esik["ret_sinifi"]
        for kod in ("kapsam-eksik", "bicim", "sayi-tutarsiz", "kanit-yok", "yetenek-yetersiz"):
            self.assertEqual(esl[kod], "onlenebilir", kod)
        self.assertEqual(esl["kriter-belirsiz"], "plan-kusuru")
        self.assertEqual(esl["talimat-ihlali"], "koruyucu")
        self.assertNotIn("siniflanmamis", esl)
        # eşleme değişince sonuç değişir: kod içinde sabit değil
        k = self.kartlar()
        d = self.defter()
        esik2 = dict(ESIK, ret_sinifi={"kapsam-eksik": "koruyucu"}, surum=8)
        israf = A.hedef_panosu(k, d, simdi=SIMDI, hedef=HEDEF, esik=esik2)["israf"]["tum_zaman"]
        self.assertEqual(israf["esik_surumu"], 8)
        self.assertEqual(israf["onlenebilir_usd"], 0.0)

    def test_varsayilan_panoda_surum_var(self):
        p = A.hedef_panosu([], [], simdi=SIMDI)
        self.assertEqual(p["israf"]["tum_zaman"]["esik_surumu"], A._ayar("kpi_esikleri.json")["surum"])


class K6GeriyeUyum(unittest.TestCase):
    def test_kpi_olcum_alanlari_durur(self):
        with tempfile.TemporaryDirectory() as sd:
            os.makedirs(os.path.join(sd, "gorevler"))
            with open(os.path.join(sd, "gorevler", "G-001.json"), "w", encoding="utf-8") as f:
                json.dump(kart("G-001"), f)
            o = K.olcum(sd)
        self.assertIn("basari_basina_token", o["genel"])
        self.assertIn("onay_bekleme_sn", o["genel"])
        self.assertIn("basari_basina_token", K.TANIMLAR)
        self.assertIn("onay_bekleme_sn", K.TANIMLAR)

    def test_analitik_json_eski_anahtarlar_durur(self):
        with tempfile.TemporaryDirectory() as d:
            sd = os.path.join(d, ".claude", "orkestra")
            os.makedirs(os.path.join(sd, "gorevler"))
            with mock.patch.object(A.L, "sohbetler", return_value=[]):
                o = A.olustur(sd, d)
        for a in ("basamak", "birim", "akis", "saglik", "ders", "trend", "hedef_panosu"):
            self.assertIn(a, o)

    def test_verim_js_kaldirilan_kpi_gostermez(self):
        for dosya in ("verim.js", "maliyet.html", "maliyet.js"):
            with open(os.path.join(KOK, "assets", dosya), encoding="utf-8") as f:
                s = f.read()
            self.assertNotIn("basari_basina_token", s, dosya)
            self.assertNotIn("onay_bekleme_sn", s, dosya)


class K5PanoJs(unittest.TestCase):
    """Canlı doğrulama ayrıca yapılır; burada yalnız kaynak sözleşmesi: pano konumu ve kutu içeriği."""

    def setUp(self):
        with open(os.path.join(KOK, "assets", "verim.js"), encoding="utf-8") as f:
            self.js = f.read()
        with open(os.path.join(KOK, "assets", "maliyet.html"), encoding="utf-8") as f:
            self.html = f.read()

    def test_pano_bolumu_sayfanin_en_ustunde(self):
        i_pano = self.html.index('id="panoIcerik"')
        for sonraki in ('id="kpiIcerik"', 'id="icerik"', 'id="basamakIcerik"'):
            self.assertLess(i_pano, self.html.index(sonraki), sonraki)
        # kapsam şeridi ve uyarıdan başka hiçbir bölüm önce gelmez
        once = self.html[:i_pano]
        self.assertEqual(len(re.findall(r"<section", once)), 1)  # yalnız pano bölümünün kendi açılışı

    def test_js_bes_olcu_ve_alanlari(self):
        for o in OLCULER:
            self.assertIn(o, self.js)
        for parca in ("hedef_panosu", "panoCiz", "durumMetni", "son_3_gun", "tum_zaman", "pay", "payda"):
            self.assertIn(parca, self.js)
        self.assertIn("gevsek-riski", self.js)
        self.assertIn("plan-kusuru", self.js)
        self.assertIn("'pano'", self.js)


if __name__ == "__main__":
    unittest.main()
