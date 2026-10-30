"""P-029: düz metin seçtirme hatırlatması (scripts/secim_ekrani_hatirlatma.py) ve hook bağlantısı.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_secim_ekrani_hatirlatma.py`
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
import secim_ekrani_hatirlatma as SH  # noqa: E402

MODUL = os.path.join(KOK, "scripts", "secim_ekrani_hatirlatma.py")
AYAR = os.path.join(KOK, "ayarlar", "secim_ekrani_hatirlatma.json")
OTURUM = "secim12345678-oturum"

POZITIF = ["Bu iki yoldan birini seçmen gerekiyor. Hangisini istersiniz?",
           "İki yoldan birini seç: A ya da B.",
           "Hangisini istediğinizi söyleyin, ona göre ilerleyeyim.",
           "Hangisini yapayım?",
           "Devam edeyim mi yoksa önce testleri mi koşayım?",
           "Push'u da yapmamı ister misiniz?",
           "HANGİSİNİ İSTERSİNİZ",
           'Numaralandırmayı eklememi isterseniz "yap" demeniz yeterli.',
           'Hazır olduğunda "yap" demen yeterli.',
           "Başlamam için onaylıyorum ya da yap yazman yeterli.",
           "Onay verirsen git push çalıştırırım.",
           "Bu üç kararı onaylarsan plan.md'ye işlerim.",
           "İstersen ikisini de yaparım.",
           "Bu iki dosyayı şimdi commit edeyim mi?",
           "Yap dersen yaparım.",
           'Planı onayladıysan "yap" dersen başlarım.',
           "Yap derseniz uygularım.",
           "Kullanıcıya kalan: Değişiklikler commit edilmedi; commit onayınızı bekliyor.",
           "Push kararınızı bekliyorum.",
           "Talimatınız bekleniyor."]
NEGATIF = ["Testler geçti, 12 dosya değişti.",
           "Bu sözcük bir kod örneğidir: `hangisini istersiniz`.",
           "```\nHangisini istersiniz?\n```",
           "P-029 kuralı 'hangisini istersiniz' kalıbını yakalar.",
           "Hangisi daha hızlı? Birincisi, çünkü indeks kullanıyor.",
           "Sen \"yap\" demeden başlamıyorum.",
           "Onay bekleyen iş yok; testler geçti.",
           "Kullanıcı onayladı, iş başladı.",
           "Kullanıcı yap dedi, işi bitirdim.",
           "",
           None]


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_secim_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_SECIM_HATIRLATMA"):
            os.environ.pop(k, None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proje_ayari(self, icerik):
        with open(os.path.join(self.sd, "secim_ekrani_hatirlatma.json"), "w", encoding="utf-8") as f:
            f.write(icerik if isinstance(icerik, str) else json.dumps(icerik))

    def transkript(self, satirlar):
        yol = os.path.join(self.tmp, "tr.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")
        return yol


def kullanici(metin="yap"):
    return {"type": "user", "message": {"role": "user", "content": metin}}


def arac_sonucu():
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}


def arac(ad, girdi=None):
    if girdi is None:
        girdi = {"AskUserQuestion": {"questions": [{"question": "x"}]}}.get(ad, {"actions": [{"label": "Yap"}]} if ad.endswith("wrap_up") else {})
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": ad, "input": girdi}]}}


def metin(m):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": m}]}}


class TestDosyalarVeKural(unittest.TestCase):
    def test_dosyalar_var(self):
        self.assertTrue(os.path.isfile(MODUL))
        self.assertTrue(os.path.isfile(AYAR))

    def test_p029_kural_kaynakta(self):
        with open(os.path.join(KOK, "kurallar", "eklenti_kurallari.json"), encoding="utf-8") as f:
            kayit = {k["id"]: k for k in json.load(f)["kurallar"]}
        self.assertEqual(kayit["P-029"]["katman"], "plugin")
        self.assertIn("kapsam İÇİNDEDİR", kayit["P-029"]["metin"])
        self.assertIn("secim_ekrani_hatirlatma", kayit["P-029"]["metin"])
        self.assertIn("ADR-0037", kayit["P-029"]["metin"])
        self.assertIn("ADR-0043", kayit["P-029"]["metin"])
        self.assertIn("yap demen yeterli", kayit["P-029"]["metin"])

    def test_ayar_anahtarlari(self):
        with open(AYAR, encoding="utf-8") as f:
            a = json.load(f)
        for k in ("mod", "hatirlatma", "secim_araclari", "yanit_kaliplari", "yanit_muaf_kaliplari", "buton_alanlari"):
            self.assertIn(k, a)
        self.assertEqual(a["mod"], "block")
        self.assertEqual(a["buton_alanlari"]["wrap_up"], "actions")
        self.assertIn(a["mod"], SH.MODLAR)
        self.assertIn("AskUserQuestion", a["secim_araclari"])

    def test_modulde_kalip_sabiti_yok(self):
        with open(MODUL, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str):
                for w in ("hangisini", "ister mis", "yoksa", "askuserquestion", "wrap_up"):
                    self.assertNotIn(w, d.value.lower(), f"modülde kalıp sabiti: {d.value[:60]!r}")


class TestKaliplar(_Proje):
    def test_yanit_pozitif(self):
        for m in POZITIF:
            with self.subTest(m=m):
                self.assertTrue(SH.yanit_ihlali(m, self.sd), m)

    def test_yanit_negatif(self):
        for m in NEGATIF:
            with self.subTest(m=m):
                self.assertFalse(SH.yanit_ihlali(m, self.sd), repr(m))

    def test_kapali_mod_ve_ortam_degiskeni(self):
        self.proje_ayari({"mod": "kapali"})
        self.assertFalse(SH.yanit_ihlali(POZITIF[0], self.sd))
        self.proje_ayari({"mod": "block"})
        self.assertTrue(SH.yanit_ihlali(POZITIF[0], self.sd))
        os.environ["ORKESTRA_SECIM_HATIRLATMA"] = "0"
        self.assertFalse(SH.yanit_ihlali(POZITIF[0], self.sd))

    def test_bozuk_proje_ayari_varsayilana_duser(self):
        self.proje_ayari("{bozuk json")
        self.assertEqual(SH.mod(SH.ayar_oku(self.sd)), "block")
        self.assertTrue(SH.yanit_ihlali(POZITIF[0], self.sd))

    def test_bilinmeyen_mod_kapali_sayilir(self):
        self.proje_ayari({"mod": "uydurma"})
        self.assertEqual(SH.mod(SH.ayar_oku(self.sd)), "kapali")

    def test_proje_ezmesi_kalip_ekler(self):
        self.proje_ayari({"yanit_kaliplari": ["ozel kalip"]})
        self.assertTrue(SH.yanit_ihlali("Ozel Kalip geçti", self.sd))
        self.assertFalse(SH.yanit_ihlali(POZITIF[0], self.sd))


class TestTranskriptMuafiyeti(_Proje):
    def test_arac_cagrisi_varsa_sunuldu(self):
        for ad in ("AskUserQuestion", "mcp__ccd_turn__wrap_up"):
            with self.subTest(ad=ad):
                yol = self.transkript([kullanici(), arac(ad), arac_sonucu(), metin("Hangisini istersiniz?")])
                self.assertTrue(SH.secim_ekrani_sunuldu(yol, self.sd))

    def test_onceki_turdaki_cagri_sayilmaz(self):
        yol = self.transkript([kullanici("bir"), arac("AskUserQuestion"), kullanici("iki"), metin("Hangisini istersiniz?")])
        self.assertFalse(SH.secim_ekrani_sunuldu(yol, self.sd))

    def test_tool_result_yeni_tur_sayilmaz(self):
        yol = self.transkript([kullanici(), arac("AskUserQuestion"), arac_sonucu(), arac("Bash")])
        self.assertTrue(SH.secim_ekrani_sunuldu(yol, self.sd))

    def test_bos_dugmeli_cagri_secim_ekrani_degil(self):
        # Düğmesiz wrap_up (yalnız özet) ya da sorusuz AskUserQuestion, düz metin onay isteğini aklamaz.
        for ad, girdi in (("mcp__ccd_turn__wrap_up", {"recap": "bitti"}), ("mcp__ccd_turn__wrap_up", {"actions": []}),
                          ("AskUserQuestion", {"questions": []})):
            with self.subTest(ad=ad, girdi=girdi):
                yol = self.transkript([kullanici(), arac(ad, girdi), metin('Başlamam için "yap" demen yeterli.')])
                self.assertFalse(SH.secim_ekrani_sunuldu(yol, self.sd))

    def test_dolu_dugme_yeter(self):
        yol = self.transkript([kullanici(), arac("mcp__ccd_turn__wrap_up", {"recap": "x", "ask": "Yapayım mı?", "actions": [{"label": "Yap"}]})])
        self.assertTrue(SH.secim_ekrani_sunuldu(yol, self.sd))

    def test_baska_arac_yetmez(self):
        yol = self.transkript([kullanici(), arac("Bash"), metin("x")])
        self.assertFalse(SH.secim_ekrani_sunuldu(yol, self.sd))

    def test_yol_yok_ya_da_bozuk(self):
        self.assertFalse(SH.secim_ekrani_sunuldu(None, self.sd))
        self.assertFalse(SH.secim_ekrani_sunuldu(os.path.join(self.tmp, "yok.jsonl"), self.sd))
        bozuk = os.path.join(self.tmp, "bozuk.jsonl")
        with open(bozuk, "w", encoding="utf-8") as f:
            f.write("{bozuk\n")
        self.assertFalse(SH.secim_ekrani_sunuldu(bozuk, self.sd))


class TestStopKapisi(_Proje):
    def kos(self, yanit, **ek):
        girdi = {"session_id": OTURUM, "cwd": self.tmp, "last_assistant_message": yanit, **ek}
        buf = io.StringIO()
        kod = None
        with contextlib.redirect_stdout(buf):
            try:
                hook._secim_kapisi_yanit(self.sd, OTURUM, girdi)
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

    def ihlaller(self):
        return [g for g in self.gunluk() if g.get("kural") == "secim_ekrani"]

    def test_golge_yalniz_gunluk(self):
        self.proje_ayari({"mod": "golge"})
        kod, cikti = self.kos(POZITIF[0])
        self.assertIsNone(kod)
        self.assertIsNone(cikti)
        kayit = self.ihlaller()
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0]["tur"], "kural_ihlal")
        self.assertEqual(kayit[0]["mod"], "golge")

    def test_varsayilan_block_ve_hatirlatma(self):
        kod, cikti = self.kos(POZITIF[0])
        self.assertEqual(kod, 0)
        self.assertEqual(cikti["decision"], "block")
        self.assertIn("AskUserQuestion", cikti["reason"])
        self.assertIn("wrap_up", cikti["reason"])
        self.assertEqual(self.ihlaller()[0]["mod"], "block")

    def test_stop_hook_active_blok_etmez(self):
        self.proje_ayari({"mod": "block"})
        kod, cikti = self.kos(POZITIF[0], stop_hook_active=True)
        self.assertIsNone(kod)
        self.assertIsNone(cikti)
        self.assertEqual(len(self.ihlaller()), 1)

    def test_yap_demen_yeterli_butonsuz_bloklanir_butonluysa_gecer(self):
        yanit = 'Numaralandırmayı eklemek için "yap" demen yeterli.'
        kod, cikti = self.kos(yanit)
        self.assertEqual(cikti["decision"], "block")
        yol = self.transkript([kullanici(), arac("mcp__ccd_turn__wrap_up"), metin(yanit)])
        kod, cikti = self.kos(yanit, transcript_path=yol)
        self.assertIsNone(cikti)

    def test_secim_ekrani_sunulduysa_sessiz(self):
        self.proje_ayari({"mod": "block"})
        yol = self.transkript([kullanici(), arac("AskUserQuestion"), metin(POZITIF[0])])
        kod, cikti = self.kos(POZITIF[0], transcript_path=yol)
        self.assertIsNone(kod)
        self.assertIsNone(cikti)
        self.assertEqual(self.gunluk(), [])

    def test_temiz_yanit_sessiz(self):
        kod, cikti = self.kos(NEGATIF[0])
        self.assertIsNone(kod)
        self.assertEqual(self.gunluk(), [])

    def test_kapali_sessiz(self):
        os.environ["ORKESTRA_SECIM_HATIRLATMA"] = "0"
        kod, cikti = self.kos(POZITIF[0])
        self.assertIsNone(kod)
        self.assertEqual(self.gunluk(), [])

    def test_modul_hata_atarsa_sessiz(self):
        self.proje_ayari({"mod": "block"})
        with mock.patch.object(SH, "yanit_ihlali", side_effect=RuntimeError("patladi")):
            kod, cikti = self.kos(POZITIF[0])
        self.assertIsNone(kod)
        self.assertIsNone(cikti)


if __name__ == "__main__":
    unittest.main()
