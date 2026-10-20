"""P-023: kimlik klasörüne önce bak hatırlatması (scripts/kimlik_hatirlatma.py) ve hook bağlantıları.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_kimlik_hatirlatma.py`
Kalıplar testte sabitlenmez; ayardan okunur. Hepsi geçici projede koşar.
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
import hook  # noqa: E402
import kimlik_hatirlatma as KH  # noqa: E402
import niyet  # noqa: E402

MODUL = os.path.join(KOK, "scripts", "kimlik_hatirlatma.py")
AYAR = os.path.join(KOK, "ayarlar", "kimlik_hatirlatma.json")
OTURUM = "kimlik12345678-oturum"

POZITIF = ["Cosmos erişimi bekleniyor, kullanıcı eklemeli.",
           "Production bağlantısını kullanıcı eklesin.",
           "Langfuse anahtarı yok.",
           "Airflow için kimlik bilgisi eksik."]
NEGATIF = ["Testler geçti, 12 dosya değişti.",
           "Kimlik klasörüne baktım: orkestra kimlik liste çıktısında cosmos var.",
           "Kimlik klasöründe karşılığı yok (liste bakıldı); kullanıcıya soruyorum.",
           ""]
MESAJ_POZITIF = ["Cosmos conversation sayısını çıkar", "Langfuse izlerine bak", "bağlantı dizesi gerekiyor"]
MESAJ_NEGATIF = ["testleri koş", "README'yi güncelle", ""]


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_kimlik_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_KIMLIK_HATIRLATMA"):
            os.environ.pop(k, None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proje_ayari(self, icerik):
        with open(os.path.join(self.sd, "kimlik_hatirlatma.json"), "w", encoding="utf-8") as f:
            f.write(icerik if isinstance(icerik, str) else json.dumps(icerik))


class TestDosyalarVeKural(unittest.TestCase):
    def test_dosyalar_var(self):
        self.assertTrue(os.path.isfile(MODUL))
        self.assertTrue(os.path.isfile(AYAR))

    def test_p023_kural_kaynakta(self):
        with open(os.path.join(KOK, "kurallar", "eklenti_kurallari.json"), encoding="utf-8") as f:
            kayit = {k["id"]: k for k in json.load(f)["kurallar"]}
        self.assertIn("P-023", kayit)
        self.assertEqual(kayit["P-023"]["katman"], "plugin")
        for parca in ("orkestra kimlik liste", "orkestra kimlik calistir", "cosmos_yusuf"):
            self.assertIn(parca, kayit["P-023"]["metin"])
        with open(os.path.join(KOK, "KURALLAR.md"), encoding="utf-8") as f:
            self.assertIn("orkestra kimlik liste", f.read())

    def test_ayar_anahtarlari(self):
        with open(AYAR, encoding="utf-8") as f:
            a = json.load(f)
        for k in ("mod", "ipucu", "hatirlatma", "servis_kaliplari", "yanit_kaliplari", "yanit_muaf_kaliplari"):
            self.assertIn(k, a)
        self.assertIn(a["mod"], KH.MODLAR)
        self.assertIn("orkestra kimlik liste", a["hatirlatma"])
        self.assertNotIn("\n", a["ipucu"])

    def test_modulde_kalip_sabiti_yok(self):
        with open(MODUL, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str):
                for w in ("cosmos", "langfuse", "airflow", "bekleniyor", "eklemeli"):
                    self.assertNotIn(w, d.value.lower(), f"modülde kalıp sabiti: {d.value[:60]!r}")


class TestKaliplar(_Proje):
    def test_yanit_pozitif(self):
        for m in POZITIF:
            with self.subTest(m=m):
                self.assertTrue(KH.yanit_ihlali(m, self.sd), m)

    def test_yanit_negatif(self):
        for m in NEGATIF:
            with self.subTest(m=m):
                self.assertFalse(KH.yanit_ihlali(m, self.sd), repr(m))

    def test_buyuk_harf_ve_none(self):
        self.assertTrue(KH.yanit_ihlali("COSMOS ERİŞİMİ BEKLENİYOR", self.sd))
        self.assertFalse(KH.yanit_ihlali(None, self.sd))

    def test_mesaj_ipucu(self):
        for m in MESAJ_POZITIF:
            with self.subTest(m=m):
                self.assertEqual(KH.mesaj_ipucu(m, self.sd), KH.ayar_oku(self.sd)["ipucu"])
        for m in MESAJ_NEGATIF:
            with self.subTest(m=m):
                self.assertEqual(KH.mesaj_ipucu(m, self.sd), "")

    def test_kapali_mod_ve_ortam_degiskeni(self):
        self.proje_ayari({"mod": "kapali"})
        self.assertFalse(KH.yanit_ihlali(POZITIF[0], self.sd))
        self.assertEqual(KH.mesaj_ipucu(MESAJ_POZITIF[0], self.sd), "")
        self.proje_ayari({"mod": "block"})
        self.assertTrue(KH.yanit_ihlali(POZITIF[0], self.sd))
        os.environ["ORKESTRA_KIMLIK_HATIRLATMA"] = "0"
        self.assertFalse(KH.yanit_ihlali(POZITIF[0], self.sd))
        self.assertEqual(KH.mesaj_ipucu(MESAJ_POZITIF[0], self.sd), "")

    def test_bozuk_proje_ayari_varsayilana_duser(self):
        self.proje_ayari("{bozuk json")
        self.assertTrue(KH.yanit_ihlali(POZITIF[0], self.sd))

    def test_proje_ezmesi_kalip_ekler(self):
        self.proje_ayari({"yanit_kaliplari": ["ozel kalip"]})
        self.assertTrue(KH.yanit_ihlali("Ozel Kalip geçti", self.sd))
        self.assertFalse(KH.yanit_ihlali(POZITIF[0], self.sd))


class TestStopKapisi(_Proje):
    def kos(self, yanit, **ek):
        girdi = {"session_id": OTURUM, "cwd": self.tmp, "last_assistant_message": yanit, **ek}
        buf = io.StringIO()
        kod = None
        with contextlib.redirect_stdout(buf):
            try:
                hook._kimlik_kapisi_yanit(self.sd, OTURUM, girdi)
            except SystemExit as e:
                kod = e.code
        c = buf.getvalue().strip()
        return kod, (json.loads(c) if c else None)

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.isfile(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def test_block_ve_hatirlatma(self):
        kod, cikti = self.kos(POZITIF[0])
        self.assertEqual(kod, 0)
        self.assertEqual(cikti["decision"], "block")
        self.assertIn("orkestra kimlik liste", cikti["reason"])
        kayit = [g for g in self.gunluk() if g.get("kural") == "kimlik_once_bak"]
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0]["mod"], "block")

    def test_stop_hook_active_blok_etmez(self):
        kod, cikti = self.kos(POZITIF[0], stop_hook_active=True)
        self.assertIsNone(kod)
        self.assertIsNone(cikti)
        self.assertEqual(len([g for g in self.gunluk() if g.get("kural") == "kimlik_once_bak"]), 1)

    def test_golge_kipinde_yalniz_gunluk(self):
        self.proje_ayari({"mod": "golge"})
        kod, cikti = self.kos(POZITIF[0])
        self.assertIsNone(kod)
        self.assertIsNone(cikti)
        self.assertEqual(self.gunluk()[0]["mod"], "golge")

    def test_temiz_yanit_sessiz(self):
        kod, cikti = self.kos(NEGATIF[0])
        self.assertIsNone(kod)
        self.assertIsNone(cikti)
        self.assertEqual(self.gunluk(), [])

    def test_kapali_sessiz(self):
        os.environ["ORKESTRA_KIMLIK_HATIRLATMA"] = "0"
        kod, cikti = self.kos(POZITIF[0])
        self.assertIsNone(kod)
        self.assertEqual(self.gunluk(), [])

    def test_modul_hata_atarsa_sessiz(self):
        with mock.patch.object(KH, "yanit_ihlali", side_effect=RuntimeError("patladi")):
            kod, cikti = self.kos(POZITIF[0])
        self.assertIsNone(kod)
        self.assertIsNone(cikti)


class TestPromptIpucu(_Proje):
    def setUp(self):
        super().setUp()
        self.tr = os.path.join(self.tmp, "tr.jsonl")
        open(self.tr, "w").close()
        niyet_yolu = os.path.join(self.tmp, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(niyet_yolu)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        super().tearDown()

    def istek(self, metin):
        g = {"session_id": OTURUM, "cwd": self.tmp, "transcript_path": self.tr, "prompt": metin}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.user_prompt_submit(g)
            except SystemExit:
                pass
        c = buf.getvalue().strip()
        return json.loads(c)["hookSpecificOutput"]["additionalContext"] if c else ""

    def test_servis_anilinca_ipucu(self):
        self.assertIn(KH.ayar_oku(self.sd)["ipucu"], self.istek("Cosmos'tan konuşmaları çek"))

    def test_servis_yoksa_ipucu_yok(self):
        self.assertNotIn(KH.ayar_oku(self.sd)["ipucu"], self.istek("testleri koş"))

    def test_sistem_iletisinde_ipucu_yok(self):
        self.assertNotIn(KH.ayar_oku(self.sd)["ipucu"], self.istek("<task-notification>cosmos</task-notification>"))

    def test_modul_hata_atarsa_hook_cikti_verir(self):
        with mock.patch.object(KH, "mesaj_ipucu", side_effect=RuntimeError("patladi")):
            ctx = self.istek("Cosmos'tan konuşmaları çek")
        self.assertNotIn(KH.ayar_oku(self.sd)["ipucu"], ctx)


if __name__ == "__main__":
    unittest.main()
