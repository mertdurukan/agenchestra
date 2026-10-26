"""ADR-0085 / P-021: kanıtsız iddia kapısı (scripts/kanitsiz_iddia.py) ve hook bağlantısı.
`python -m pytest -q plugins/orkestra/tests/test_kanitsiz_iddia.py`
Tetik kalıpları testte proje ezmesiyle verilir (sentetik); varsayılan ayarın kalıpları ayrıca sınanır. Döküm ve yanıt
metinleri sentetiktir, gerçek konuşma metni içermez. Hepsi geçici projede koşar.
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
import kanit_olcum as K  # noqa: E402
import kanitsiz_iddia as KI  # noqa: E402

MODUL = os.path.join(KOK, "scripts", "kanitsiz_iddia.py")
AYAR = os.path.join(KOK, "ayarlar", "kanitsiz_iddia.json")
OTURUM = "kanitsiz12345678-oturum"
SORU = "Bu ayar nasıl çalışıyor, neden böyle?"
SENTETIK = {
    "mod": "golge",
    "tetik_kaliplari": [r"\bkullanılıyor\b", r"\btestler? (geçti|yeşil)\b"],
    "muaf_kaliplari": [r"doğrulanmad[ıi]", r"genel bilgi"],
    "alinti_max_karakter": 40,
    "uyari_sablonu": "UYARI: «{alinti}» — doğrulanmadı.",
    "hatirlatma": "Kaynağa bak ya da doğrulanmadı yaz.",
}
IDDIALI = "Bu projede redis kullanılıyor ve her şey yolunda."


def kullanici(metin=SORU):
    return {"type": "user", "timestamp": "2026-10-26T10:00:00Z", "message": {"role": "user", "content": metin}}


def arac_sonucu():
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}


def arac(ad, girdi=None):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": ad, "input": girdi or {}}]}}


def metin(m):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": m}]}}


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_kanitsiz_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_KANIT_KAPISI"):
            os.environ.pop(k, None)
        hook._KULLANICI_MESAJI = ""

    def tearDown(self):
        hook._KULLANICI_MESAJI = ""
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proje_ayari(self, icerik=None):
        veri = dict(SENTETIK)
        veri.update(icerik or {})
        with open(os.path.join(self.sd, "kanitsiz_iddia.json"), "w", encoding="utf-8") as f:
            json.dump(veri, f)

    def transkript(self, satirlar):
        yol = os.path.join(self.tmp, "tr.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")
        return yol


class TestDosyalarVeKural(unittest.TestCase):
    def test_dosyalar_var(self):
        self.assertTrue(os.path.isfile(MODUL))
        self.assertTrue(os.path.isfile(AYAR))

    def test_varsayilan_ayar(self):
        with open(AYAR, encoding="utf-8") as f:
            a = json.load(f)
        for k in ("mod", "uyari_acik", "tetik_kaliplari", "muaf_kaliplari", "alinti_max_karakter", "uyari_sablonu", "hatirlatma"):
            self.assertIn(k, a)
        self.assertEqual(a["mod"], "golge")  # P-028: block'a geçiş ayrı kararla (ADR-0085)
        self.assertIn(a["mod"], KI.MODLAR)
        self.assertIn("{alinti}", a["uyari_sablonu"])
        for k in a["tetik_kaliplari"] + a["muaf_kaliplari"]:
            __import__("re").compile(k)

    def test_modulde_kalip_sabiti_yok(self):
        with open(MODUL, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str):
                for w in ("kullanılıyor", "testler geçti", "doğrulanmadı", "genel bilgi"):
                    self.assertNotIn(w, d.value.lower(), f"modülde kalıp sabiti: {d.value[:60]!r}")


class TestKaliplar(_Proje):
    def test_tetik_ve_alinti_kisaltma(self):
        a = dict(SENTETIK)
        c = KI.ilk_eslesme("Merhaba.\n" + IDDIALI, a)
        self.assertTrue(c.startswith("Bu projede redis"))
        self.assertLessEqual(len(c), 40)

    def test_muaf_kalip_yanitin_her_yerinde_susturur(self):
        self.assertIsNone(KI.ilk_eslesme(IDDIALI + " Bu genel bilgi.", SENTETIK))
        self.assertIsNone(KI.ilk_eslesme("Doğrulanmadı: " + IDDIALI, SENTETIK))

    def test_kod_blogu_cumle_sayilmaz(self):
        self.assertIsNone(KI.ilk_eslesme("```\nredis kullanılıyor\n```\nTamam.", SENTETIK))

    def test_tetiksiz_yanit_sessiz(self):
        self.assertIsNone(KI.ilk_eslesme("Bu bir tanımdır, öneri değildir.", SENTETIK))
        self.assertIsNone(KI.ilk_eslesme("", SENTETIK))
        self.assertIsNone(KI.ilk_eslesme(None, SENTETIK))

    def test_gecersiz_regex_atlanir(self):
        a = dict(SENTETIK, tetik_kaliplari=["[bozuk", r"\bkullanılıyor\b"])
        self.assertIsNotNone(KI.ilk_eslesme(IDDIALI, a))

    def test_mod_ve_ortam_degiskeni(self):
        self.assertEqual(KI.mod({"mod": "block"}), "block")
        self.assertEqual(KI.mod({"mod": "uydurma"}), "kapali")
        self.assertEqual(KI.mod({}), "kapali")
        os.environ["ORKESTRA_KANIT_KAPISI"] = "0"
        try:
            self.assertEqual(KI.mod({"mod": "block"}), "kapali")
        finally:
            os.environ.pop("ORKESTRA_KANIT_KAPISI", None)

    def test_uyari_acik_yalniz_ayar_ya_da_block(self):
        self.assertFalse(KI.uyari_acik({"mod": "golge"}))
        self.assertTrue(KI.uyari_acik({"mod": "golge", "uyari_acik": True}))
        self.assertTrue(KI.uyari_acik({"mod": "block"}))

    def test_bozuk_proje_ayari_varsayilana_duser(self):
        with open(os.path.join(self.sd, "kanitsiz_iddia.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk json")
        self.assertEqual(KI.mod(KI.ayar_oku(self.sd)), "golge")


class TestDegerlendir(_Proje):
    def test_kanitsiz_bilgi_sorusu_yakalanir(self):
        self.proje_ayari()
        yol = self.transkript([kullanici(), metin(IDDIALI)])
        self.assertIsNotNone(KI.degerlendir(yol, IDDIALI, self.sd))

    def test_okuma_araci_kanit_sayilir(self):
        self.proje_ayari()
        for ad in ("Read", "Grep", "Bash"):
            with self.subTest(ad=ad):
                yol = self.transkript([kullanici(), arac(ad, {"command": "git status"}), arac_sonucu(), metin(IDDIALI)])
                self.assertIsNone(KI.degerlendir(yol, IDDIALI, self.sd))

    def test_ilgisiz_arac_kanit_sayilmaz(self):
        self.proje_ayari()
        for ad, girdi in (("Skill", {}), ("TodoWrite", {}), ("mcp__ccd_turn__update_plan", {}),
                          ("Bash", {"command": "orkestra niyet 'x'"})):
            with self.subTest(ad=ad):
                yol = self.transkript([kullanici(), arac(ad, girdi), arac_sonucu(), metin(IDDIALI)])
                self.assertIsNotNone(KI.degerlendir(yol, IDDIALI, self.sd))

    def test_onceki_turdaki_cagri_sayilmaz(self):
        self.proje_ayari()
        yol = self.transkript([kullanici("bir"), arac("Read"), arac_sonucu(), kullanici(), metin(IDDIALI)])
        self.assertIsNotNone(KI.degerlendir(yol, IDDIALI, self.sd))

    def test_is_istegi_kapsam_disi(self):
        self.proje_ayari()
        yol = self.transkript([kullanici("raporu güncelle ve testleri çalıştır"), metin(IDDIALI)])
        self.assertIsNone(KI.degerlendir(yol, IDDIALI, self.sd))

    def test_yanit_verilmezse_dokumdeki_son_metin(self):
        self.proje_ayari()
        yol = self.transkript([kullanici(), metin(IDDIALI)])
        self.assertIsNotNone(KI.degerlendir(yol, None, self.sd))

    def test_yol_yok_ya_da_bozuk(self):
        self.proje_ayari()
        self.assertIsNone(KI.degerlendir(None, IDDIALI, self.sd))
        self.assertIsNone(KI.degerlendir(os.path.join(self.tmp, "yok.jsonl"), IDDIALI, self.sd))
        bozuk = os.path.join(self.tmp, "bozuk.jsonl")
        with open(bozuk, "w", encoding="utf-8") as f:
            f.write("{bozuk\n")
        self.assertIsNone(KI.degerlendir(bozuk, IDDIALI, self.sd))


class TestSonTur(_Proje):
    def test_son_tur_ve_cagrilar(self):
        yol = self.transkript([kullanici("bir"), metin("a"), kullanici("iki"), arac("Read", {"file_path": "x"}), arac_sonucu(), metin("b")])
        t = K.son_tur(yol)
        self.assertEqual(t["istem"], "iki")
        self.assertEqual([c[0] for c in t["cagrilar"]], ["Read"])
        self.assertEqual(t["yanit"], "b")

    def test_tool_result_ve_sistem_satiri_tur_acmaz(self):
        yol = self.transkript([kullanici("bir"), arac("Bash", {"command": "ls"}), arac_sonucu(),
                               {"type": "user", "message": {"role": "user", "content": "<system-reminder>x</system-reminder>"}},
                               metin("c")])
        t = K.son_tur(yol)
        self.assertEqual(t["istem"], "bir")
        self.assertEqual(t["yanit"], "c")

    def test_yan_zincir_atlanir(self):
        yan = dict(kullanici("yan"), isSidechain=True)
        yol = self.transkript([kullanici("ana"), yan, metin("x")])
        self.assertEqual(K.son_tur(yol)["istem"], "ana")

    def test_kuyruk_siniri_ilk_satiri_atar(self):
        satirlar = [kullanici("eski")] + [metin("x" * 200)] * 50 + [kullanici("yeni"), metin("son")]
        yol = self.transkript(satirlar)
        t = K.son_tur(yol, kuyruk_bayt=2000)
        self.assertEqual(t["istem"], "yeni")

    def test_bos_ya_da_yok(self):
        self.assertIsNone(K.son_tur(os.path.join(self.tmp, "yok.jsonl")))
        bos = os.path.join(self.tmp, "bos.jsonl")
        open(bos, "w").close()
        self.assertIsNone(K.son_tur(bos))

    def test_tur_satirlari_bozuk_satiri_atlar(self):
        turlar = list(K.tur_satirlari(["{bozuk", json.dumps(kullanici("a")), json.dumps(metin("b"))]))
        self.assertEqual(len(turlar), 1)
        self.assertEqual(turlar[0]["yanit"], "b")


class TestStopKapisi(_Proje):
    def kos(self, yanit, transkript=None, **ek):
        yol = transkript if transkript is not None else self.transkript([kullanici(), metin(yanit or "")])
        girdi = {"session_id": OTURUM, "cwd": self.tmp, "last_assistant_message": yanit, "transcript_path": yol, **ek}
        buf = io.StringIO()
        kod = None
        with contextlib.redirect_stdout(buf):
            try:
                hook._kanitsiz_iddia_yanit(self.sd, OTURUM, girdi)
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
        return [g for g in self.gunluk() if g.get("kural") == "kanitsiz_iddia"]

    def test_golge_yalniz_gunluk_uyari_kapali(self):
        self.proje_ayari()
        kod, cikti = self.kos(IDDIALI)
        self.assertIsNone(kod)
        self.assertIsNone(cikti)
        kayit = self.ihlaller()
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0]["tur"], "kural_ihlal")
        self.assertEqual(kayit[0]["mod"], "golge")
        self.assertEqual(hook._KULLANICI_MESAJI, "")

    def test_ihlalde_deterministik_uyari_alintiyi_tasir(self):
        self.proje_ayari({"uyari_acik": True})
        self.kos(IDDIALI)
        self.assertEqual(len(self.ihlaller()), 1)
        self.assertEqual(hook._KULLANICI_MESAJI, "UYARI: «Bu projede redis kullanılıyor ve her şey» — doğrulanmadı.")

    def test_uyari_mevcut_kullanici_mesajini_korur(self):
        self.proje_ayari({"uyari_acik": True})
        hook._KULLANICI_MESAJI = "Orkestra belgeleri:"
        self.kos(IDDIALI)
        satirlar = hook._KULLANICI_MESAJI.split("\n")
        self.assertEqual(satirlar[0], "Orkestra belgeleri:")
        self.assertTrue(satirlar[1].startswith("UYARI:"))

    def test_block_kipinde_block_ve_uyari(self):
        self.proje_ayari({"mod": "block"})
        kod, cikti = self.kos(IDDIALI)
        self.assertEqual(kod, 0)
        self.assertEqual(cikti["decision"], "block")
        self.assertIn("doğrulanmadı", cikti["reason"])
        self.assertIn("UYARI:", cikti["systemMessage"])
        self.assertEqual(self.ihlaller()[0]["mod"], "block")

    def test_stop_hook_active_ikinci_block_yok(self):
        self.proje_ayari({"mod": "block"})
        kod, cikti = self.kos(IDDIALI, stop_hook_active=True)
        self.assertIsNone(kod)
        self.assertIsNone(cikti)
        self.assertEqual(len(self.ihlaller()), 1)

    def test_kanit_araci_varsa_sessiz(self):
        self.proje_ayari({"mod": "block", "uyari_acik": True})
        yol = self.transkript([kullanici(), arac("Read", {"file_path": "x"}), arac_sonucu(), metin(IDDIALI)])
        kod, cikti = self.kos(IDDIALI, transkript=yol)
        self.assertIsNone(kod)
        self.assertEqual(self.gunluk(), [])

    def test_ilgisiz_arac_kanit_sayilmaz(self):
        self.proje_ayari({"mod": "block"})
        yol = self.transkript([kullanici(), arac("Bash", {"command": "orkestra is todo I-1 --bitti 1"}), arac_sonucu(), metin(IDDIALI)])
        kod, cikti = self.kos(IDDIALI, transkript=yol)
        self.assertEqual(kod, 0)
        self.assertEqual(cikti["decision"], "block")

    def test_isaretli_yanit_sessiz(self):
        self.proje_ayari({"mod": "block"})
        kod, cikti = self.kos(IDDIALI + " Bu doğrulanmadı.")
        self.assertIsNone(kod)
        self.assertEqual(self.gunluk(), [])

    def test_ortam_degiskeni_kapatir(self):
        self.proje_ayari({"mod": "block"})
        os.environ["ORKESTRA_KANIT_KAPISI"] = "0"
        kod, cikti = self.kos(IDDIALI)
        self.assertIsNone(kod)
        self.assertEqual(self.gunluk(), [])

    def test_kapali_mod_sessiz(self):
        self.proje_ayari({"mod": "kapali"})
        kod, cikti = self.kos(IDDIALI)
        self.assertIsNone(kod)
        self.assertEqual(self.gunluk(), [])

    def test_modul_hata_atarsa_sessiz(self):
        self.proje_ayari({"mod": "block"})
        with mock.patch.object(KI, "degerlendir", side_effect=RuntimeError("patladi")):
            kod, cikti = self.kos(IDDIALI)
        self.assertIsNone(kod)
        self.assertIsNone(cikti)


if __name__ == "__main__":
    unittest.main()
