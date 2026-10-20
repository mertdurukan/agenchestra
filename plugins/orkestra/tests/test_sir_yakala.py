"""ADR-0011: sohbetteki açık atama kimlik klasörüne yazılır; bağlama ve hata iletisine değer girmez."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import kimlik as K  # noqa: E402
import sir_yakala as S  # noqa: E402

SIR = "d3ger-GIZLI-4242"


class Yakala(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.eski = {k: os.environ.get(k) for k in ("ORKESTRA_KIMLIK_DIZINI", "ORKESTRA_KIMLIK_PROJE", "ORKESTRA_SIR_YAKALA")}
        os.environ["ORKESTRA_KIMLIK_DIZINI"] = os.path.join(self.t, "cred")
        os.environ["ORKESTRA_KIMLIK_PROJE"] = "Proje"
        os.environ.pop("ORKESTRA_SIR_YAKALA", None)

    def tearDown(self):
        for k, v in self.eski.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def test_atama_servise_yazilir(self):
        s = S.kaydet(f"bak\nLANGFUSE_SECRET_KEY={SIR}\nbitti")
        self.assertEqual(s, ["kimlik kaydedildi: langfuse.LANGFUSE_SECRET_KEY"])
        self.assertEqual(K.al("langfuse", "LANGFUSE_SECRET_KEY"), SIR)
        self.assertNotIn(SIR, "\n".join(s))

    def test_acik_servis_ve_tirnak(self):
        S.kaydet(f"mail: SMTP_PASSWORD=\"{SIR}\"")
        self.assertEqual(K.al("mail", "SMTP_PASSWORD"), SIR)

    def test_guncelleme_bildirilir(self):
        S.kaydet(f"DB_PASSWORD=eski")
        self.assertEqual(S.kaydet(f"DB_PASSWORD={SIR}"), ["kimlik güncellendi: db.DB_PASSWORD"])

    def test_tanimayan_bicim_yazmaz(self):
        for m in (f"şifre {SIR}", f"DB_HOST={SIR}", f"x=y", f"api key: {SIR}"):
            self.assertEqual(S.kaydet(m), [], m)
        self.assertFalse(os.path.exists(K.kok()))

    def test_kapatma(self):
        os.environ["ORKESTRA_SIR_YAKALA"] = "0"
        self.assertEqual(S.kaydet(f"DB_PASSWORD={SIR}"), [])
        self.assertFalse(os.path.exists(K.kok()))

    def test_hook_baglamda_deger_yok(self):
        proje = os.path.join(self.t, "proje")
        os.makedirs(os.path.join(proje, ".claude", "orkestra"))
        girdi = json.dumps({"cwd": proje, "session_id": "s1", "prompt": f"POSTHOG_API_KEY={SIR}"})
        p = subprocess.run([sys.executable, os.path.join(KOK, "scripts", "hook.py"), "UserPromptSubmit"], input=girdi,
                           capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"))
        self.assertNotIn(SIR, p.stdout + p.stderr)
        self.assertIn("kimlik kaydedildi: posthog.POSTHOG_API_KEY", p.stdout)
        self.assertEqual(K.al("posthog", "POSTHOG_API_KEY"), SIR)


class SerbestMetin(unittest.TestCase):
    """ADR-0020: bağlantı dizesi, token ve parola satırı serbest metinden kimlik klasörüne alınır."""

    URI = "mongodb+srv://kullanici:SAHTE-4242@sunucu.example.com/?tls=true"

    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.eski = {k: os.environ.get(k) for k in ("ORKESTRA_KIMLIK_DIZINI", "ORKESTRA_KIMLIK_PROJE", "ORKESTRA_SIR_YAKALA")}
        os.environ["ORKESTRA_KIMLIK_DIZINI"] = os.path.join(self.t, "cred")
        os.environ["ORKESTRA_KIMLIK_PROJE"] = "Proje"
        os.environ.pop("ORKESTRA_SIR_YAKALA", None)

    def tearDown(self):
        for k, v in self.eski.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def test_uri_ve_alt_satir_etiketi(self):
        s = S.kaydet(f"{self.URI}\n \nCosmos yusuf")
        self.assertEqual(K.al("cosmos_yusuf", "COSMOS_YUSUF_CONNECTION_STRING"), self.URI)
        self.assertIn("cosmos_yusuf.COSMOS_YUSUF_CONNECTION_STRING", "\n".join(s))
        self.assertIn("kaydedildi", s[0])

    def test_ust_satir_ve_ayni_satir_etiketi(self):
        S.kaydet(f"Cosmos Test\n{self.URI}")
        self.assertEqual(K.al("cosmos_test", "COSMOS_TEST_CONNECTION_STRING"), self.URI)
        S.kaydet(f"Ana Veri: {self.URI}")
        self.assertEqual(K.al("ana_veri", "ANA_VERI_CONNECTION_STRING"), self.URI)

    def test_turkce_etiket(self):
        S.kaydet(f"{self.URI}\nÜretim Çıktı")
        self.assertEqual(K.al("uretim_cikti", "URETIM_CIKTI_CONNECTION_STRING"), self.URI)

    def test_etiketsiz_uri_semadan_tahmin(self):
        s = S.kaydet(self.URI)
        self.assertEqual(K.al("mongodb", "MONGODB_CONNECTION_STRING"), self.URI)
        self.assertIn("mongodb.MONGODB_CONNECTION_STRING", "\n".join(s))

    def test_uzun_cumle_etiket_sayilmaz(self):
        S.kaydet(f"{self.URI}\nbunu lütfen bir kontrol edip bana söyler misin")
        self.assertEqual(K.al("mongodb", "MONGODB_CONNECTION_STRING"), self.URI)

    def test_parolasiz_uri_yazilmaz(self):
        for m in ("https://example.com/yol", "mongodb://sunucu:27017/db", "postgres://kullanici@sunucu/db"):
            self.assertEqual(S.kaydet(m), [], m)
        self.assertFalse(os.path.exists(K.kok()))

    def test_yer_tutucu_parola_yazilmaz(self):
        for m in ("mongodb://kullanici:<parola>@sunucu/db", "postgres://u:***@h/db", "redis://u:${REDIS_PW}@h/0"):
            self.assertEqual(S.kaydet(m), [], m)
        self.assertFalse(os.path.exists(K.kok()))

    def test_tokenlar(self):
        for metin, servis, anahtar in (
                ("sk-or-v1-" + "a1b2c3d4e5" * 4, "openrouter", "OPENROUTER_TOKEN"),
                ("ghp_" + "A1b2C3d4E5" * 3 + "xy", "github", "GITHUB_TOKEN"),
                ("Authorization: Bearer " + "abc.DEF-123_" * 4, "bearer", "BEARER_TOKEN")):
            with self.subTest(servis=servis):
                s = S.kaydet(metin)
                self.assertEqual(len(s), 2, s)  # kayıt satırı + değeri tekrar etme uyarısı
                self.assertIn(f"{servis}.{anahtar}", s[0])
                self.assertIn(K.al(servis, anahtar)[:6], metin)

    def test_etiketli_token(self):
        S.kaydet("sk-or-v1-" + "a1b2c3d4e5" * 4 + "\nOpenrouter yedek")
        self.assertTrue(K.al("openrouter_yedek", "OPENROUTER_YEDEK_TOKEN").startswith("sk-or-"))

    def test_parola_satiri(self):
        s = S.kaydet(f"Langfuse\nParola: {SIR}")
        self.assertEqual(K.al("langfuse", "LANGFUSE_PASSWORD"), SIR)
        self.assertNotIn(SIR, "\n".join(s))

    def test_deger_hicbir_satirda_yok(self):
        satirlar = S.kaydet(f"{self.URI}\nCosmos yusuf") + S.kaydet(f"{self.URI}\nCosmos yusuf")
        satirlar += S.kaydet(self.URI.replace("4242", "FARKLI-9999") + "\nCosmos yusuf")
        for sat in satirlar:
            self.assertNotIn("SAHTE", sat)
            self.assertNotIn("FARKLI", sat)
            self.assertNotIn("kullanici:", sat)

    def test_ayni_deger_degisiklik_yok(self):
        S.kaydet(f"{self.URI}\nCosmos yusuf")
        s = S.kaydet(f"{self.URI}\nCosmos yusuf")
        self.assertIn("aynı", s[0])
        self.assertEqual(K.al("cosmos_yusuf", "COSMOS_YUSUF_CONNECTION_STRING"), self.URI)

    def test_farkli_deger_ezmez_yeni_ad_onerir(self):
        S.kaydet(f"{self.URI}\nCosmos yusuf")
        yeni = self.URI.replace("4242", "FARKLI-9999")
        s = S.kaydet(f"{yeni}\nCosmos yusuf")
        self.assertIn("farklı", s[0])
        self.assertIn("cosmos_yusuf_2", "\n".join(s))
        self.assertEqual(K.al("cosmos_yusuf", "COSMOS_YUSUF_CONNECTION_STRING"), self.URI)
        self.assertFalse(os.path.exists(os.path.join(K.kok(), "Proje", "cosmos_yusuf_2.env")))

    def test_uyari_satiri_ajana_degeri_tekrarlatmaz(self):
        s = S.kaydet(f"{self.URI}\nCosmos yusuf")
        self.assertIn("yenilemek", "\n".join(s))
        self.assertIn("tekrar etme", "\n".join(s))

    def test_acik_atama_davranisi_ayni(self):
        S.kaydet("DB_PASSWORD=eski")
        self.assertEqual(S.kaydet(f"DB_PASSWORD={SIR}"), ["kimlik güncellendi: db.DB_PASSWORD"])

    def test_atama_icindeki_token_ikinci_kez_yazilmaz(self):
        s = S.kaydet("OPENROUTER_API_KEY=sk-or-v1-" + "a1b2c3d4e5" * 4)
        self.assertEqual(s, ["kimlik kaydedildi: openrouter.OPENROUTER_API_KEY"])

    def test_kapatma(self):
        os.environ["ORKESTRA_SIR_YAKALA"] = "0"
        self.assertEqual(S.kaydet(f"{self.URI}\nCosmos yusuf"), [])
        self.assertFalse(os.path.exists(K.kok()))

    def test_hook_baglamda_deger_yok(self):
        proje = os.path.join(self.t, "proje")
        os.makedirs(os.path.join(proje, ".claude", "orkestra"))
        girdi = json.dumps({"cwd": proje, "session_id": "s1", "prompt": f"{self.URI}\nCosmos yusuf"})
        p = subprocess.run([sys.executable, os.path.join(KOK, "scripts", "hook.py"), "UserPromptSubmit"], input=girdi,
                           capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"))
        self.assertNotIn("SAHTE", p.stdout + p.stderr)
        self.assertIn("cosmos_yusuf.COSMOS_YUSUF_CONNECTION_STRING", p.stdout)
        self.assertEqual(K.al("cosmos_yusuf", "COSMOS_YUSUF_CONNECTION_STRING"), self.URI)

if __name__ == "__main__":
    unittest.main()
