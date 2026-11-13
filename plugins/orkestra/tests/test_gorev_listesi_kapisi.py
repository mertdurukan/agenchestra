"""Görev listesi açık adım kapısı: durum kurma (S3), karar (S1/S2), ayar ve günlük (S4), uçtan uca Stop."""
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
sys.path.insert(0, os.path.join(KOK, "skills", "close", "scripts"))
import gorev_listesi as GL  # noqa: E402
import gorev_listesi_kapisi as GK  # noqa: E402
import hook  # noqa: E402
import sohbet_cikar  # noqa: E402

PLAN = "mcp__ccd_turn__update_plan"
OTURUM = "gorevlistesi1234-oturum"


def kullanici(metin):
    return {"type": "user", "message": {"role": "user", "content": metin}}


def arac(ad, girdi, yan=False):
    return {"type": "assistant", "isSidechain": yan,
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": ad, "input": girdi}]}}


def metin(m):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": m}]}}


UC_ADIM = {"items": [{"content": "Oku", "status": "in_progress"}, {"content": "Yaz", "status": "pending"},
                     {"content": "Test", "status": "pending"}]}


class Ortak(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.mkdtemp(prefix="ork_gl_")
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_GOREV_LISTESI_KAPISI", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.dizin, ignore_errors=True)

    def transkript(self, *satirlar):
        yol = os.path.join(self.dizin, "t.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        return yol


class DurumKurma(Ortak):  # S3
    def test_items_advance_done_start(self):
        m = GL.uygula([], PLAN, UC_ADIM)
        m = GL.uygula(m, PLAN, {"advance": True})
        self.assertEqual([x["durum"] for x in m], ["completed", "in_progress", "pending"])
        m = GL.uygula(m, PLAN, {"done": [2], "start": 3})
        self.assertEqual([x["durum"] for x in m], ["completed", "completed", "in_progress"])

    def test_advance_sonraki_pending_adimi_baslatir(self):
        m = GL.uygula([], PLAN, {"items": [{"content": "a", "status": "pending"}, {"content": "b", "status": "in_progress"},
                                           {"content": "c", "status": "pending"}]})
        m = GL.uygula(m, PLAN, {"advance": True})
        self.assertEqual([x["durum"] for x in m], ["pending", "completed", "in_progress"])

    def test_todowrite_listeyi_degistirir(self):
        m = GL.uygula([], "TodoWrite", {"todos": [{"content": "x", "status": "completed"}, {"content": "y", "status": "pending"}]})
        self.assertEqual([x["durum"] for x in m], ["completed", "pending"])

    def test_bozuk_girdi_listeyi_bozmaz(self):
        m = GL.uygula([], PLAN, UC_ADIM)
        self.assertEqual(GL.uygula(m, PLAN, "bozuk"), m)
        self.assertEqual(GL.uygula(m, PLAN, {"done": [9, "x"]}), m)

    def test_transkriptten_kurar_alt_ajani_yok_sayar(self):
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), arac(PLAN, {"done": [1, 2, 3]}, yan=True),
                            arac(PLAN, {"advance": True}))
        m, ad = GL.durum_kur(t)
        self.assertEqual([x["durum"] for x in m], ["completed", "in_progress", "pending"])
        self.assertEqual(ad, PLAN)

    def test_close_plan_ortak_modulu_kullanir(self):
        p = sohbet_cikar.Plan()
        p.uygula(UC_ADIM)
        p.uygula({"advance": True})
        self.assertEqual([x["durum"] for x in p.maddeler], ["completed", "in_progress", "pending"])


class Karar(Ortak):
    def test_s1_acik_adim_ve_bekleme_yok_tetikler(self):
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), metin("Bitti, testler geçti."))
        b = GK.degerlendir(t, "Bitti, testler geçti.", 0, {})
        self.assertEqual([n for n, _, _ in b["acik"]], [1, 2, 3])
        self.assertIn('"done": [1, 2, 3]', GK.hatirlatma_metni(b, {}))

    def test_s2_soru_bekleyen_tur_tetiklemez(self):
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), metin("Hangi yolu seçelim?"))
        self.assertIsNone(GK.degerlendir(t, "Hangi yolu seçelim?", 0, {}))

    def test_s2_arka_plan_gorevi_tetiklemez(self):
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), metin("Testler arka planda."))
        self.assertIsNone(GK.degerlendir(t, "Testler arka planda.", 0, {"background_tasks": [{"id": "b1"}]}))

    def test_s2_yalniz_son_adim_in_progress_tetiklemez(self):
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), arac(PLAN, {"done": [1, 2], "start": 3}), metin("Bitti."))
        self.assertIsNone(GK.degerlendir(t, "Bitti.", 0, {}))

    def test_liste_yoksa_tetiklemez(self):
        t = self.transkript(kullanici("selam"), metin("Merhaba."))
        self.assertIsNone(GK.degerlendir(t, "Merhaba.", 0, {}))

    def test_todowrite_hatirlatmasi(self):
        t = self.transkript(kullanici("yap"), arac("TodoWrite", {"todos": [{"content": "a", "status": "pending"},
                                                                           {"content": "b", "status": "completed"}]}), metin("Bitti."))
        self.assertIn("TodoWrite", GK.hatirlatma_metni(GK.degerlendir(t, "Bitti.", 0, {}), {}))


class AyarVeStop(Ortak):  # S4 + uçtan uca
    def setUp(self):
        super().setUp()
        self.proje = os.path.join(self.dizin, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje

    def test_s4_ortam_degiskeni_ve_ayar_kapatir(self):
        self.assertEqual(GK.mod({}), "block")
        self.assertEqual(GK.mod({"mod": "kapali"}), "kapali")
        os.environ["ORKESTRA_GOREV_LISTESI_KAPISI"] = "0"
        self.assertEqual(GK.mod({"mod": "block"}), "kapali")

    def test_s4_proje_ayari_ezer(self):
        with open(os.path.join(self.sd, GK.DOSYA), "w", encoding="utf-8") as f:
            json.dump({"mod": "golge"}, f)
        self.assertEqual(GK.mod(GK.ayar_oku(self.sd)), "golge")

    def stop(self, t, son, **ek):
        buf = io.StringIO()
        inp = {"cwd": self.proje, "session_id": OTURUM, "transcript_path": t, "last_assistant_message": son, **ek}
        with contextlib.redirect_stdout(buf):
            try:
                hook._gorev_listesi_yanit(self.sd, OTURUM, inp, 0)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        return json.loads(ham.splitlines()[-1]) if ham else {}

    def gunluk(self):
        try:
            with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
                return [json.loads(s) for s in f if '"gorev_listesi"' in s]
        except OSError:
            return []

    def test_s1_block_ve_gunluk(self):
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), metin("Bitti."))
        c = self.stop(t, "Bitti.")
        self.assertEqual(c.get("decision"), "block")
        self.assertIn("açık adım", c.get("reason", ""))
        g = self.gunluk()
        self.assertEqual((g[-1]["tur"], g[-1]["acik"]), ("kapi_ihlal", 3))

    def test_s2_stop_hook_active_gecer(self):
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), metin("Bitti."))
        self.assertEqual(self.stop(t, "Bitti.", stop_hook_active=True), {})
        self.assertEqual(self.gunluk(), [])

    def test_s4_golge_yalniz_gunluge_yazar(self):
        with open(os.path.join(self.sd, GK.DOSYA), "w", encoding="utf-8") as f:
            json.dump({"mod": "golge"}, f)
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), metin("Bitti."))
        self.assertEqual(self.stop(t, "Bitti."), {})
        self.assertEqual(self.gunluk()[-1]["tur"], "kapi_golge")

    def test_stop_icinden_cagrilir(self):
        t = self.transkript(kullanici("yap"), arac(PLAN, UC_ADIM), metin("Bitti."))
        with mock.patch.object(hook, "_gorev_listesi_yanit") as m:
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    hook.stop({"cwd": self.proje, "session_id": OTURUM, "transcript_path": t, "last_assistant_message": "Bitti."})
                except SystemExit:
                    pass
        self.assertTrue(m.called)


if __name__ == "__main__":
    unittest.main()
