"""G-120: soru sınıflayıcı (scripts/soru_sinif.py) ve hook.user_prompt_submit bilgi sorusu notu.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_soru_sinif.py`
Kalıp/eşikler testte sabitlenmez; ayardan okunur. Hepsi geçici projede koşar.
"""
import ast
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
try:  # kod yokken toplama hatası değil, test başarısızlığı olsun
    import soru_sinif  # noqa: E402
except ImportError:
    soru_sinif = None
import hook  # noqa: E402
import niyet  # noqa: E402

MODUL = os.path.join(KOK, "scripts", "soru_sinif.py")
AYAR = os.path.join(KOK, "ayarlar", "soru_sinif.json")
OTURUM = "soru1234567890-oturum"

POZITIF = ["fallback ne demek?", "PE-612 nedir", "bu kural gerekir mi?", "neden iki denetçi var?",
           "niye yavaş?", "yapay zeka nedir?", "eklenti nedir?", "bu doğru mu", "langfuse token sayıyor mu?"]
NEGATIF = ["şunu düzelt", "testleri yap ve commit at", "bunu uygular mısın?", "başlayalım mı?",
           "raporu güncelle, sonra ne demek olduğunu yaz", ""]


class _Ayarli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_soru_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.assertIsNotNone(soru_sinif, "scripts/soru_sinif.py yok")
        self.ayar = soru_sinif.ayar_oku(self.sd)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proje_ayari(self, icerik):
        with open(os.path.join(self.sd, "soru_sinif.json"), "w", encoding="utf-8") as f:
            f.write(icerik if isinstance(icerik, str) else json.dumps(icerik))


class TestK1Dosyalar(unittest.TestCase):
    def test_dosyalar_var(self):
        self.assertTrue(os.path.isfile(MODUL))
        self.assertTrue(os.path.isfile(AYAR))

    def test_p021_kural_kaynakta(self):
        """P-021: yanıttan önce doğrulama kuralı eklenti kaynağında ve KURALLAR.md'de, P-001 ile birlikte durur."""
        with open(os.path.join(KOK, "kurallar", "eklenti_kurallari.json"), encoding="utf-8") as f:
            kayit = {k["id"]: k for k in json.load(f)["kurallar"]}
        self.assertIn("P-001", kayit)
        self.assertIn("P-021", kayit)
        self.assertEqual(kayit["P-021"]["katman"], "plugin")
        self.assertIn("kod tabanına göre doğrulan", kayit["P-021"]["metin"])
        self.assertIn("P-001", kayit["P-021"]["metin"])
        with open(os.path.join(KOK, "KURALLAR.md"), encoding="utf-8") as f:
            self.assertIn("P-021", f.read())

    def test_ayar_anahtarlari(self):
        with open(AYAR, encoding="utf-8") as f:
            a = json.load(f)
        for k in ("not", "kisa_max_karakter", "uzun_max_karakter", "soru_kaliplari", "soru_eki_regex", "eylem_kaliplari"):
            self.assertIn(k, a)
        # P-021: not, yanıttan önce hedefli doğrulamayı ister; P-001 sınırı (5 cümle, geniş tarama yok) korunur
        self.assertIn("P-021", a["not"])
        self.assertIn("doğrula", a["not"])
        self.assertIn("en çok 5 cümle", a["not"])
        self.assertNotIn("kaynak taraması yok", a["not"].replace("geniş kaynak taraması yok", ""))
        self.assertLess(a["kisa_max_karakter"], a["uzun_max_karakter"])
        self.assertTrue(a["soru_kaliplari"] and a["eylem_kaliplari"])
        self.assertNotIn("\n", a["not"])

    def test_modulde_kalip_ve_esik_sabiti_yok(self):
        with open(MODUL, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        yasak_kelime = ("nedir", "demek", "gerekir", "niye", "uygula", "düzelt", "commit")
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant):
                if isinstance(d.value, str):
                    dusuk = d.value.lower()
                    for w in yasak_kelime:
                        self.assertNotIn(w, dusuk, f"modülde kalıp sabiti: {d.value[:60]!r}")
                elif isinstance(d.value, (int, float)) and not isinstance(d.value, bool):
                    self.assertNotIn(d.value, (100, 120, 150, 200, 250, 300, 400, 500), "modülde eşik sabiti")


class TestK2Pozitif(_Ayarli):
    def test_pozitif_ornekler(self):
        for m in POZITIF:
            with self.subTest(m=m):
                self.assertTrue(soru_sinif.bilgi_sorusu_mu(m, self.ayar), m)

    def test_buyuk_harf_normallestirme(self):
        self.assertTrue(soru_sinif.bilgi_sorusu_mu("FALLBACK NE DEMEK?", self.ayar))
        self.assertTrue(soru_sinif.bilgi_sorusu_mu("İKİ DENETÇİ NEDEN VAR?", self.ayar))
        self.assertTrue(soru_sinif.bilgi_sorusu_mu("BU DOĞRU MU", self.ayar))

    def test_kisa_soru_isareti_tek_basina(self):
        # karar (4): '?' ile biten kısa metin kalıp olmasa da soru
        self.assertTrue(soru_sinif.bilgi_sorusu_mu("kuantum gitar?", self.ayar))

    def test_not_metni_soruysa_ayar_notu(self):
        self.assertEqual(soru_sinif.not_metni("fallback ne demek?", self.sd), self.ayar["not"])


class TestK3Negatif(_Ayarli):
    def test_negatif_ornekler(self):
        for m in NEGATIF:
            with self.subTest(m=m):
                self.assertFalse(soru_sinif.bilgi_sorusu_mu(m, self.ayar), repr(m))

    def test_uzun_soru_isaretli_false(self):
        m = "a" * (self.ayar["uzun_max_karakter"]) + "?"
        self.assertEqual(len(m), self.ayar["uzun_max_karakter"] + 1)
        self.assertFalse(soru_sinif.bilgi_sorusu_mu(m, self.ayar))
        m2 = "fallback ne demek " + "x " * (self.ayar["uzun_max_karakter"] // 2 + 1) + "?"
        self.assertFalse(soru_sinif.bilgi_sorusu_mu(m2, self.ayar))

    def test_sinirda_uzunluk_kabul(self):
        # tam uzun_max_karakter uzunlukta, soru kalıplı, eylemsiz metin hâlâ True
        taban = "fallback ne demek "
        m = taban + "x" * (self.ayar["uzun_max_karakter"] - len(taban))
        self.assertEqual(len(m), self.ayar["uzun_max_karakter"])
        self.assertTrue(soru_sinif.bilgi_sorusu_mu(m, self.ayar))

    def test_bosluk_ve_sadece_isaret(self):
        self.assertFalse(soru_sinif.bilgi_sorusu_mu("   ", self.ayar))
        self.assertFalse(soru_sinif.bilgi_sorusu_mu("\n\t", self.ayar))

    def test_eylem_kazanir(self):
        self.assertFalse(soru_sinif.bilgi_sorusu_mu("bunu düzeltebilir misin?", self.ayar))
        self.assertFalse(soru_sinif.bilgi_sorusu_mu("neden başlatmıyorsun, push et", self.ayar))
        self.assertFalse(soru_sinif.bilgi_sorusu_mu("DÜZELT", self.ayar))

    def test_not_metni_degilse_bos(self):
        self.assertEqual(soru_sinif.not_metni("şunu düzelt", self.sd), "")
        self.assertEqual(soru_sinif.not_metni("", self.sd), "")

    def test_eylem_kelime_siniri(self):
        for m in ("yapay zeka nedir?", "yazılım nedir", "eklenti nedir"):
            with self.subTest(m=m):
                self.assertTrue(soru_sinif.bilgi_sorusu_mu(m, self.ayar))


class TestK4Ezme(_Ayarli):
    def test_varsayilan_proje_yokken(self):
        with open(AYAR, encoding="utf-8") as f:
            self.assertEqual(self.ayar["uzun_max_karakter"], json.load(f)["uzun_max_karakter"])

    def test_esik_ezmesi_karari_degistirir(self):
        m = "fallback ne demek?"
        self.assertTrue(soru_sinif.bilgi_sorusu_mu(m, self.ayar))
        self.proje_ayari({"uzun_max_karakter": 5})
        a = soru_sinif.ayar_oku(self.sd)
        self.assertEqual(a["uzun_max_karakter"], 5)
        self.assertFalse(soru_sinif.bilgi_sorusu_mu(m, a))
        self.assertEqual(soru_sinif.not_metni(m, self.sd), "")
        # ezilmeyen anahtarlar varsayılandan gelir
        self.assertEqual(a["not"], self.ayar["not"])

    def test_kalip_ezmesi_karari_degistirir(self):
        m = "zzqx hakkında bilgi"
        self.assertFalse(soru_sinif.bilgi_sorusu_mu(m, self.ayar))
        self.proje_ayari({"soru_kaliplari": [r"\bzzqx\b"]})
        a = soru_sinif.ayar_oku(self.sd)
        self.assertTrue(soru_sinif.bilgi_sorusu_mu(m, a))
        self.assertTrue(soru_sinif.not_metni(m, self.sd))
        # eski kalıplar artık sayılmaz (soru eki de devre dışı bırakılınca)
        self.assertFalse(soru_sinif.bilgi_sorusu_mu("fallback ne demek", dict(a, soru_eki_regex=r"(?!x)x")))
        self.assertEqual(a["soru_kaliplari"], [r"\bzzqx\b"])

    def test_not_ezmesi(self):
        self.proje_ayari({"not": "ozel not"})
        self.assertEqual(soru_sinif.not_metni("fallback ne demek?", self.sd), "ozel not")

    def test_bozuk_json_varsayilana_duser(self):
        self.proje_ayari("{bozuk json,,")
        self.assertEqual(soru_sinif.ayar_oku(self.sd), self.ayar)
        self.assertTrue(soru_sinif.bilgi_sorusu_mu("fallback ne demek?", soru_sinif.ayar_oku(self.sd)))

    def test_json_dizi_varsayilana_duser(self):
        self.proje_ayari("[1, 2]")
        self.assertEqual(soru_sinif.ayar_oku(self.sd), self.ayar)

    def test_bos_dosya_varsayilana_duser(self):
        self.proje_ayari("")
        self.assertEqual(soru_sinif.ayar_oku(self.sd), self.ayar)

    def test_olmayan_durum_dizini(self):
        a = soru_sinif.ayar_oku(os.path.join(self.tmp, "yok", "dizin"))
        self.assertEqual(a, self.ayar)


class TestK5Hook(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_soruhook_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        niyet_yolu = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(niyet_yolu)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()
        self.assertIsNotNone(soru_sinif, "scripts/soru_sinif.py yok")
        self.not_ = soru_sinif.ayar_oku(self.sd)["not"]

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def istek(self, metin):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr, "prompt": metin}
        buf = io.StringIO()
        kod = None
        with contextlib.redirect_stdout(buf):
            try:
                hook.user_prompt_submit(g)
            except SystemExit as e:
                kod = e.code
        self.assertIn(kod, (0, None))
        c = buf.getvalue().strip()
        if not c:
            return ""
        return json.loads(c)["hookSpecificOutput"]["additionalContext"]

    def test_bilgi_sorusunda_not_ilk_satir(self):
        ctx = self.istek("fallback ne demek?")
        self.assertEqual(ctx.split("\n")[0], self.not_)

    def test_is_isteginde_not_yok(self):
        ctx = self.istek("şunu düzelt")
        self.assertNotIn(self.not_, ctx)
        self.assertNotIn("BİLGİ SORUSU", ctx)

    def test_sistem_iletisinde_not_yok(self):
        ctx = self.istek("<task-notification>ne demek?</task-notification>")
        self.assertNotIn("BİLGİ SORUSU", ctx)

    def test_not_tek_satir(self):
        ctx = self.istek("neden iki denetçi var?")
        self.assertEqual(ctx.count("BİLGİ SORUSU"), 1)
        self.assertEqual(ctx.split("\n")[0].count("\n"), 0)

    def test_proje_ezmesi_hooka_yansir(self):
        with open(os.path.join(self.sd, "soru_sinif.json"), "w", encoding="utf-8") as f:
            json.dump({"not": "OZEL KISA NOT"}, f)
        ctx = self.istek("fallback ne demek?")
        self.assertEqual(ctx.split("\n")[0], "OZEL KISA NOT")

    def test_soru_sinif_hata_atarsa_hook_cikti_verir(self):
        with mock.patch.object(soru_sinif, "not_metni", side_effect=RuntimeError("patladi")):
            ctx = self.istek("fallback ne demek?")
        self.assertNotIn("BİLGİ SORUSU", ctx)
        # hook çıktı vermeye devam eder: gunluk kaydı ve JSON çıktısı üretildi
        self.assertTrue(os.path.isfile(os.path.join(self.sd, "gunluk.jsonl")))

    def test_hata_halinde_diger_parcalar_korunur(self):
        with mock.patch.object(hook, "_yonlendirme_ipucu", return_value="IPUCU-X"), \
                mock.patch.object(soru_sinif, "not_metni", side_effect=ValueError("x")):
            ctx = self.istek("fallback ne demek?")
        self.assertIn("IPUCU-X", ctx)

    def test_not_diger_parcalardan_once(self):
        with mock.patch.object(hook, "_yonlendirme_ipucu", return_value="IPUCU-X"):
            ctx = self.istek("fallback ne demek?")
        satirlar = ctx.split("\n")
        self.assertEqual(satirlar[0], self.not_)
        self.assertIn("IPUCU-X", satirlar)


class TurSiniflama(unittest.TestCase):
    """tur(): model çağrısız üç sınıf; kararsızlıkta yönlendirme tetiklenmez (soru/devam), yalnız 'is' tetikler."""

    def test_uc_sinif(self):
        self.assertEqual(soru_sinif.tur("bu ne demek?"), "soru")
        self.assertEqual(soru_sinif.tur("önerinle devam et"), "devam")
        self.assertEqual(soru_sinif.tur("fatura raporunu düzelt"), "is")

    def test_bos_metin_is_degil(self):
        self.assertNotEqual(soru_sinif.tur(""), "soru")


class BagliTur(unittest.TestCase):
    """I-061 P1: bağlı oturumda 'açıkça devam' yalnız güçlü kalıp ya da çok kısa mesajdır; zayıf kalıp belirsizdir."""

    def test_acik_devam_ve_soru(self):
        self.assertEqual(soru_sinif.bagli_tur("tamam, devam et"), "devam")
        self.assertEqual(soru_sinif.bagli_tur("commit et"), "devam")
        self.assertEqual(soru_sinif.bagli_tur("bu ne demek?"), "soru")

    def test_zayif_kalip_gecis_vermez(self):
        self.assertEqual(soru_sinif.bagli_tur("Bunu bir kural olarak ekle. Kesinlikle yapılacak bir kural bu."), "belirsiz")
        self.assertEqual(soru_sinif.bagli_tur("bunlara ayrı bir kural yazalım, hepsi alt alta olsun"), "belirsiz")

    def test_uzun_konu_belirsiz(self):
        self.assertEqual(soru_sinif.bagli_tur("o zaman main dışında bulunan tüm dalları silelim"), "belirsiz")


class YanitIhlali(unittest.TestCase):
    def test_kalip_yakalanir_temiz_yanit_gecer(self):
        self.assertTrue(soru_sinif.yanit_ihlali("Bitti. Başka kartı da yapmamı ister misin?"))
        self.assertFalse(soru_sinif.yanit_ihlali("Bitti. 3 dosya değişti."))


if __name__ == "__main__":
    unittest.main()
