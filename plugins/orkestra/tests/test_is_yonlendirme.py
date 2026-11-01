"""is_yonlendirme: yeni görev satırı, kapanış/bayat tespiti (G-062).

Tüm veri sentetiktir; dosya/ağ yok. Yalnız modül kaynağı statik olarak okunur.
`python -m unittest discover -s plugins/orkestra/tests -p test_is_yonlendirme.py`
"""
import ast
import importlib.util
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODUL_YOLU = os.path.join(KOK, "scripts", "is_yonlendirme.py")

iy = None


def setUpModule():
    global iy
    assert os.path.isfile(MODUL_YOLU), "scripts/is_yonlendirme.py yok"
    spec = importlib.util.spec_from_file_location("is_yonlendirme", MODUL_YOLU)
    iy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(iy)


def is_(id_, baslik, klasor="", todolar=None):
    return {"id": id_, "baslik": baslik, "klasor_adi": klasor,
            "acik_todolar": list(todolar or [])}


class ArayuzTest(unittest.TestCase):
    def test_fonksiyonlar_var(self):
        for ad in ("yonlendir", "kapanis_adaylari"):
            self.assertTrue(callable(getattr(iy, ad, None)), ad)


class YonlendirTest(unittest.TestCase):
    ISLER = [is_("I-1", "Fatura raporlama"), is_("I-2", "Kampanya takvimi")]

    def _kontrol(self, s):
        self.assertIsInstance(s, str)
        self.assertNotIn(chr(10), s)
        self.assertLessEqual(len(s), iy.SATIR_SINIR)
        self.assertIn("orkestra is devam", s)
        self.assertIn("orkestra is ac", s)

    def test_baglisiz_acik_isler_ve_kural(self):
        s = iy.yonlendir(self.ISLER, None)
        self._kontrol(s)
        self.assertIn("bağlı iş yok", s)
        self.assertIn("I-1 Fatura raporlama", s)
        self.assertIn("I-2 Kampanya takvimi", s)

    def test_bagli_is_adi_satirda(self):
        s = iy.yonlendir(self.ISLER, "I-2")
        self._kontrol(s)
        self.assertIn("bağlı iş I-2 Kampanya takvimi", s)

    def test_bagli_oturumda_farkli_konu_ayri_sohbette_acilir(self):
        # K-004: bağlı işten farklı konu sormadan ayrı oturumda, ayrı işte yürür; bu oturum bağlı işte kalır.
        for zorunlu in (False, True):
            s = iy.yonlendir(self.ISLER, "I-2", zorunlu=zorunlu)
            self.assertIn("start_session", s)
            self.assertIn("detach_session", s)
            self.assertIn("FARKLI", s)
            self.assertIn("sorma", s.lower())
            self.assertIn("orkestra is ac", s)

    def test_baglisiz_oturumda_yeni_oturum_onerisi_yok(self):
        self.assertNotIn("start_session", iy.yonlendir(self.ISLER, None))

    def test_acik_is_yoksa_yine_yeni_is_kurali(self):
        for girdi in ([], None, "x"):
            s = iy.yonlendir(girdi, None)
            self._kontrol(s)
            self.assertNotIn("Açık işler:", s)

    def test_bozuk_girdi_atlanir(self):
        s = iy.yonlendir([None, 5, {"baslik": "idsiz"}, is_("I-9", "Tek")], None)
        self.assertIn("I-9 Tek", s)
        self.assertNotIn("idsiz", s)

    def test_cok_is_ve_uzun_baslik_sinirli(self):
        isler = [is_("I-%d" % n, "Uzun başlık" + chr(10) + "ikinci satır " * 20) for n in range(20)]
        s = iy.yonlendir(isler, "I-3")
        self._kontrol(s)
        self.assertNotIn("I-10 ", s)


class KapanisTest(unittest.TestCase):
    SIMDI = datetime(2026, 10, 14, 12, 0, 0)

    def _o(self, id_, toplam, biten, acik, son):
        return {"id": id_, "toplam": toplam, "biten": biten, "acik_kart": acik,
                "son_dokunus": son}

    def _iso(self, gun, saat=0):
        return (self.SIMDI - timedelta(days=gun, hours=saat)).isoformat()

    def test_tum_biten_kapat(self):
        r = iy.kapanis_adaylari([self._o("A", 5, 5, 0, self._iso(1))], self.SIMDI)
        self.assertEqual(r["kapat"], ["A"])
        self.assertEqual(r["bayat"], [])

    def test_donus_bicimi(self):
        r = iy.kapanis_adaylari([], self.SIMDI)
        self.assertEqual(r, {"kapat": [], "bayat": []})

    def test_toplam_sifir_kapat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 0, 0, 0, self._iso(1))], self.SIMDI)
        self.assertNotIn("A", r["kapat"])

    def test_acik_kart_varsa_kapat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 3, 3, 1, self._iso(1))], self.SIMDI)
        self.assertNotIn("A", r["kapat"])

    def test_biten_eksikse_kapat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 3, 2, 0, self._iso(1))], self.SIMDI)
        self.assertNotIn("A", r["kapat"])

    def test_14_gun_bayat(self):
        r = iy.kapanis_adaylari([self._o("A", 4, 2, 0, self._iso(14))], self.SIMDI)
        self.assertEqual(r["bayat"], ["A"])
        self.assertEqual(r["kapat"], [])

    def test_14_gunden_eski_bayat(self):
        r = iy.kapanis_adaylari([self._o("A", 4, 2, 1, self._iso(60))], self.SIMDI)
        self.assertEqual(r["bayat"], ["A"])

    def test_13_gun_bayat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 4, 2, 1, self._iso(13, 23))], self.SIMDI)
        self.assertEqual(r["bayat"], [])

    def test_kapat_adayi_bayat_sayilmaz(self):
        r = iy.kapanis_adaylari([self._o("A", 2, 2, 0, self._iso(40))], self.SIMDI)
        self.assertEqual(r["kapat"], ["A"])
        self.assertEqual(r["bayat"], [])

    def test_son_dokunus_none_bayat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 4, 2, 1, None)], self.SIMDI)
        self.assertEqual(r["bayat"], [])

    def test_saat_dilimli_tarih(self):
        simdi = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone(timedelta(hours=3)))
        eski = (simdi - timedelta(days=20)).isoformat()
        taze = (simdi - timedelta(days=2)).isoformat()
        r = iy.kapanis_adaylari([self._o("E", 4, 2, 1, eski),
                                 self._o("T", 4, 2, 1, taze)], simdi)
        self.assertEqual(r["bayat"], ["E"])

    def test_birden_cok_is_karisik(self):
        ozetler = [self._o("K1", 2, 2, 0, self._iso(1)),
                   self._o("B1", 5, 1, 2, self._iso(30)),
                   self._o("N1", 5, 1, 2, self._iso(1)),
                   self._o("K2", 1, 1, 0, self._iso(20))]
        r = iy.kapanis_adaylari(ozetler, self.SIMDI)
        self.assertEqual(sorted(r["kapat"]), ["K1", "K2"])
        self.assertEqual(r["bayat"], ["B1"])

    def test_bozuk_girdi_istisna_firlatmaz(self):
        iyi = self._o("OK", 2, 2, 0, self._iso(1))
        bozuklar = [
            None, 42, "metin", [], {},
            {"id": "X"},
            {"id": "X", "toplam": "çok", "biten": None, "acik_kart": "?"},
            {"id": "X", "toplam": 3, "biten": 3, "acik_kart": 0, "son_dokunus": "dun gibi"},
            {"id": "X", "toplam": 3, "biten": 1, "acik_kart": 1, "son_dokunus": 12345},
            {"toplam": 3, "biten": 3, "acik_kart": 0},
        ]
        r = iy.kapanis_adaylari(bozuklar + [iyi], self.SIMDI)
        self.assertIn("OK", r["kapat"])
        self.assertIsInstance(r["bayat"], list)

    def test_ozetler_bozuk_tipler(self):
        for girdi in (None, [], "x", 5):
            r = iy.kapanis_adaylari(girdi, self.SIMDI)
            self.assertEqual(r["kapat"], [])
            self.assertEqual(r["bayat"], [])


class StatikTest(unittest.TestCase):
    YASAK_ISIMLER = {"subprocess", "socket", "urllib", "http", "requests", "os",
                     "pathlib", "shutil", "tempfile", "ftplib", "smtplib", "ctypes"}

    def setUp(self):
        with open(MODUL_YOLU, encoding="utf-8") as f:
            self.kaynak = f.read()
        self.agac = ast.parse(self.kaynak)

    def _kok_moduller(self):
        out = set()
        for n in ast.walk(self.agac):
            if isinstance(n, ast.Import):
                out |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                out.add(n.module.split(".")[0])
        return out

    def test_yalniz_standart_kutuphane(self):
        std = set(sys.stdlib_module_names) | {"__future__"}
        self.assertLessEqual(self._kok_moduller(), std)

    def test_dosya_ag_subprocess_yok(self):
        self.assertFalse(self._kok_moduller() & self.YASAK_ISIMLER)

    def test_open_ve_exec_cagrisi_yok(self):
        for n in ast.walk(self.agac):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                self.assertNotIn(n.func.id, {"open", "exec", "eval", "__import__"})
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                self.assertNotIn(n.func.attr, {"read_text", "write_text", "system", "popen"})


I013 = {"id": "I-013", "baslik": "İş yönlendirmesinde tür ve alan ayrımı (yeni iş görünmüyor)",
        "klasor": "015-20261016-is-yonlendirme-tur-alan"}
I015 = {"id": "I-015", "baslik": "Orkestra LLM'den Python'a alma: ana ajan turları, kanıt kapısı, kural→ön kontrol, koşullu denetçi",
        "klasor": "017-20261016-llm-python-gecis"}
I018 = {"id": "I-018", "baslik": "Orkestra Cursor uyumu: tek kaynak + adaptör planı",
        "klasor": "019-20261016-cursor-uyumu"}
ACIK = [I013, I015, I018]
AYAR_YOLU = os.path.join(KOK, "ayarlar", "is_esleme.json")
AYAR = {"yuksek": 0.6, "dusuk": 0.2, "durak_sozcukler": [], "soru_etiketi": "soru"}


class EslestirTest(unittest.TestCase):
    def test_k1_islevler_var(self):
        self.assertTrue(callable(getattr(iy, "eslestir", None)))
        self.assertTrue(callable(getattr(iy, "karar", None)))

    def test_k1_siralama_ve_aralik(self):
        r = iy.eslestir("Orkestra iş yönlendirme tür alan ayrımı", ACIK)
        self.assertEqual({x["id"] for x in r}, {"I-013", "I-015", "I-018"})
        puanlar = [x["puan"] for x in r]
        self.assertEqual(puanlar, sorted(puanlar, reverse=True))
        for x in r:
            self.assertIsInstance(x["puan"], (int, float))
            self.assertGreaterEqual(x["puan"], 0)
            self.assertLessEqual(x["puan"], 1)
        self.assertEqual(r[0]["id"], "I-013")
        self.assertGreater(r[0]["puan"], r[-1]["puan"])

    def test_k1_bos_girdiler(self):
        self.assertEqual(iy.eslestir("", ACIK), [])
        self.assertEqual(iy.eslestir("   ", ACIK), [])
        self.assertEqual(iy.eslestir(None, ACIK), [])
        self.assertEqual(iy.eslestir("tür alan ayrımı", []), [])
        self.assertEqual(iy.eslestir("tür alan ayrımı", None), [])

    def test_k1_klasor_ve_metin_kullanilir(self):
        isler = [{"id": "X-1", "baslik": "Genel iş", "metin": "kampanya fiyat raporu hazırlığı"},
                 {"id": "X-2", "baslik": "Genel iş", "klasor": "depo-taşıma"}]
        self.assertEqual(iy.eslestir("kampanya fiyat raporu", isler)[0]["id"], "X-1")
        self.assertEqual(iy.eslestir("depo taşıma", isler)[0]["id"], "X-2")

    def test_k1_ilgisiz_dusuk_puan(self):
        for x in iy.eslestir("AcmeRetail kampanya fiyat raporu", ACIK):
            self.assertLess(x["puan"], 0.2)

    def test_k1_tam_ortusme_yuksek(self):
        r = iy.eslestir(I013["baslik"], ACIK)
        self.assertEqual(r[0]["id"], "I-013")
        self.assertGreaterEqual(r[0]["puan"], 0.6)

    def test_k2_buyuk_kucuk_harf_noktalama_duyarsiz(self):
        a = iy.eslestir("TÜR, ALAN: ayrımı!", [I013])[0]["puan"]
        b = iy.eslestir("tür alan ayrımı", [I013])[0]["puan"]
        self.assertAlmostEqual(a, b)
        self.assertGreater(a, 0)

    def test_k2_turkce_buyuk_I_ve_i(self):
        a = iy.eslestir("İŞ YÖNLENDİRMESİNDE TÜR ALAN AYRIMI", [I013])[0]["puan"]
        b = iy.eslestir("iş yönlendirmesinde tür alan ayrımı", [I013])[0]["puan"]
        self.assertAlmostEqual(a, b)
        self.assertGreater(a, 0.5)

    def test_k2_kisa_sozcukler_atilir(self):
        r = iy.eslestir("ab cd ef", [{"id": "A", "baslik": "ab cd ef xyz"}])
        self.assertTrue(r == [] or all(x["puan"] == 0 for x in r))

    def test_k2_ayardaki_durak_sozcuk_etki_eder(self):
        isler = [{"id": "A", "baslik": "zebra kampanya"}]
        p1 = iy.eslestir("zebra", isler, dict(AYAR, durak_sozcukler=["zebra"]))
        p2 = iy.eslestir("zebra", isler, AYAR)
        self.assertTrue(p1 == [] or p1[0]["puan"] == 0)
        self.assertGreater(p2[0]["puan"], 0)

    def test_k2_ayar_dosyasi_alanlari(self):
        import json
        self.assertTrue(os.path.isfile(AYAR_YOLU), "ayarlar/is_esleme.json yok")
        with open(AYAR_YOLU, encoding="utf-8") as f:
            a = json.load(f)
        for alan in ("yuksek", "dusuk", "durak_sozcukler", "soru_etiketi"):
            self.assertIn(alan, a)
        self.assertTrue(0 < a["dusuk"] < a["yuksek"] <= 1)
        self.assertIsInstance(a["durak_sozcukler"], list)
        self.assertTrue(a["durak_sozcukler"])
        self.assertTrue(str(a["soru_etiketi"]).strip())

    def test_k2_bozuk_ayarla_varsayilan_calisir(self):
        for ayar in (None, {}, "bozuk", 5, {"yuksek": "x"}):
            r = iy.eslestir(I013["baslik"], ACIK, ayar)
            self.assertEqual(r[0]["id"], "I-013")
            self.assertEqual(iy.karar(r, ayar)[0], "bagla")

    def test_k3_bagla(self):
        k = iy.karar([{"id": "I-1", "puan": 0.9}, {"id": "I-2", "puan": 0.1}])
        self.assertEqual(k, ("bagla", "I-1"))

    def test_k3_ac(self):
        self.assertEqual(iy.karar([{"id": "I-1", "puan": 0.0}]), ("ac", None))
        self.assertEqual(iy.karar([]), ("ac", None))

    def test_k3_sec_en_cok_iki(self):
        k = iy.karar([{"id": "A", "puan": 0.4}, {"id": "B", "puan": 0.35},
                      {"id": "C", "puan": 0.3}], AYAR)
        self.assertEqual(k, ("sec", ["A", "B"]))

    def test_k3_sec_tek_is(self):
        self.assertEqual(iy.karar([{"id": "A", "puan": 0.4}], AYAR), ("sec", ["A"]))

    def test_k3_esikler_ayardan_ve_sinir_degerleri(self):
        ayar = dict(AYAR, yuksek=0.5, dusuk=0.25)
        self.assertEqual(iy.karar([{"id": "A", "puan": 0.5}], ayar), ("bagla", "A"))
        self.assertEqual(iy.karar([{"id": "A", "puan": 0.25}], ayar), ("sec", ["A"]))
        self.assertEqual(iy.karar([{"id": "A", "puan": 0.2499}], ayar), ("ac", None))
        ayar2 = dict(ayar, yuksek=0.8, dusuk=0.7)
        self.assertEqual(iy.karar([{"id": "A", "puan": 0.5}], ayar2), ("ac", None))

    def test_k4_ilgili_istek_baglar_ya_da_secer(self):
        k = iy.karar(iy.eslestir("Orkestra iş yönlendirme tür alan ayrımı", ACIK))
        self.assertIn(k[0], ("bagla", "sec"))
        if k[0] == "bagla":
            self.assertEqual(k[1], "I-013")
        else:
            self.assertIn("I-013", k[1])

    def test_k4_ilgisiz_istek_acar(self):
        self.assertEqual(iy.karar(iy.eslestir("AcmeRetail kampanya fiyat raporu", [I013])), ("ac", None))
        self.assertEqual(iy.karar(iy.eslestir("AcmeRetail kampanya fiyat raporu", ACIK)), ("ac", None))

    def test_k4_ayrim_olculebilir(self):
        ilgili = iy.eslestir("Orkestra iş yönlendirme tür alan ayrımı", [I013])[0]["puan"]
        ilgisiz = iy.eslestir("AcmeRetail kampanya fiyat raporu", [I013])[0]["puan"]
        self.assertGreater(ilgili - ilgisiz, 0.3)

    def test_k4_diger_isler_dogru_eslesir(self):
        self.assertEqual(iy.eslestir("Cursor uyumu adaptör planı", ACIK)[0]["id"], "I-018")
        self.assertEqual(iy.eslestir("LLM'den Python'a alma kanıt kapısı", ACIK)[0]["id"], "I-015")

    def test_k5_girdi_degismez(self):
        import copy
        kopya = copy.deepcopy(ACIK)
        iy.eslestir("tür alan ayrımı", ACIK)
        self.assertEqual(ACIK, kopya)

    def test_k5_bozuk_is_ogeleri_atlanir(self):
        r = iy.eslestir("tür alan ayrımı", [None, "x", {"baslik": "kimliksiz tür alan"}, I013])
        self.assertEqual(r[0]["id"], "I-013")


class IsleIlgiliTest(unittest.TestCase):
    """I-061 P1: bağlı işle ilgili mi (gönderme ya da örtüşme); plan/todo sözcüğü tek başına sayılmaz."""
    IS = {"id": "I-061", "baslik": "Konu değişiminde yeni oturum önerisi: mekanik kontrol",
          "klasor": "043-20261018-konu-degisimi-mekanik-kontrol", "metin": ""}

    def test_kimlik_ve_klasor_gondermesi(self):
        self.assertTrue(iy.isle_ilgili_mi("I-061 için devam edelim", self.IS))
        self.assertTrue(iy.isle_ilgili_mi("043- klasöründeki plana bak", self.IS))
        self.assertFalse(iy.isle_ilgili_mi("I-0610 değil", self.IS))

    def test_plan_todo_sozcugu_tek_basina_yetmez(self):
        self.assertFalse(iy.isle_ilgili_mi("plan ve todo gibi her işte jira dosyası oluşsun", self.IS))

    def test_baslik_ortusmesi(self):
        self.assertTrue(iy.isle_ilgili_mi("yeni oturum önerisi için mekanik kontrol kuralı", self.IS))

    def test_bozuk_girdi(self):
        self.assertFalse(iy.isle_ilgili_mi(None, self.IS))
        self.assertFalse(iy.isle_ilgili_mi("x", None))


class ZorunluYonergeTest(unittest.TestCase):
    """I-061 P2: belirsiz mesajda satır zorunlu yönergedir, güncel konuyu taşır ve sınırı aşmaz."""
    ISLER = [{"id": "I-061", "baslik": "Konu değişiminde yeni oturum"}, {"id": "I-003", "baslik": "Ölçüm"}]

    def test_zorunlu_metin_ve_guncel_konu(self):
        s = iy.yonlendir(self.ISLER, "I-061", zorunlu=True, guncel_konu="dal temizliği")
        self.assertTrue(s.startswith("Yeni görev ("), s)
        self.assertIn("ZORUNLU", s)
        self.assertIn("start_session", s)
        self.assertIn("SORMA", s)
        self.assertIn("dal temizliği", s)
        self.assertLessEqual(len(s), iy.SATIR_SINIR)

    def test_varsayilan_hatirlatma_degismedi(self):
        self.assertNotIn("ZORUNLU", iy.yonlendir(self.ISLER, "I-061"))
        self.assertNotIn("ZORUNLU", iy.yonlendir(self.ISLER, None, zorunlu=True))


class BaslikKapsama(unittest.TestCase):
    """I-138 P3: yeterince uzun başlıkta başlık kapsaması da sayılır."""

    MESAJ = "fatura raporlama ekranında kolon sırası bozuk geliyor düzeltelim lütfen şimdi"
    BASLIK = "fatura raporlama ekranında kolon sırası bozuk"

    def test_ayar_varsayilani_5(self):
        self.assertEqual(iy._ayar({})["baslik_kapsama_min_sozcuk"], 5)
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ayarlar", "is_esleme.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["baslik_kapsama_min_sozcuk"], 5)

    def test_basligi_ureten_mesaj_baglanir(self):
        p = iy.eslestir(self.MESAJ, [{"id": "I-1", "baslik": self.BASLIK}], {"durak_sozcukler": []})
        self.assertGreaterEqual(p[0]["puan"], 0.6)

    def test_tek_sozcuklu_baslik_uzun_mesaja_baglanmaz(self):
        p = iy.eslestir(self.MESAJ + " panel", [{"id": "I-2", "baslik": "panel"}], {"durak_sozcukler": []})
        self.assertLess(p[0]["puan"], 0.6)


class DevirOnu(unittest.TestCase):
    """I-151 G8: 'Task (from the session…):' öneki sözcük örtüşmesine girmez; yan oturum yanlış işe bağlanmaz."""

    ON = "Task (from the session that started this one): "
    ISLER = [
        {"id": "I-072", "baslik": ON + "Eski tarama aracı hata ayıklama günlüğü"},
        {"id": "I-151", "baslik": "Panel klasik görünüm kısayollar kaldır"},
    ]

    def test_devir_onu_at(self):
        self.assertEqual(iy.devir_onu_at(self.ON + "Panel düzeni"), "Panel düzeni")
        self.assertEqual(iy.devir_onu_at("Background (from the session x): Task (from the session y): a b"), "a b")
        self.assertEqual(iy.devir_onu_at("öneksiz metin"), "öneksiz metin")
        self.assertEqual(iy.devir_onu_at(None), "")

    def test_onek_ortak_sozcuk_baglamaz(self):
        # önek yalnız istekte ve işin başlığında ortak: önek atılınca örtüşme kalmaz
        p = {x["id"]: x["puan"] for x in iy.eslestir(self.ON + "Panel klasik görünüm kısayollar kaldır", self.ISLER)}
        self.assertGreater(p["I-151"], p["I-072"])
        self.assertEqual(p["I-072"], 0)

    def test_yalniz_onek_olan_istek_hicbir_ise_baglanmaz(self):
        self.assertEqual(iy.eslestir(self.ON, self.ISLER), [])
        self.assertEqual(iy.karar(iy.eslestir(self.ON + "Yeni bambaşka konu", self.ISLER)), ("ac", None))


if __name__ == "__main__":
    unittest.main()
