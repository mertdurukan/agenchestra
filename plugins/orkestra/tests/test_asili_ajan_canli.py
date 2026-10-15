"""Asılı ajan kaydı yalnız canlı oturumlardan: kapanış temizliği + canlılık süzgeci (G-082).

Geçici projede ve sahte niyet.jsonl ile çalışır; gerçek ~/.claude'a yazılmaz.
"""
import contextlib
import datetime
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
import niyet  # noqa: E402
import ozet  # noqa: E402


def dk_once(dk):
    return (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=dk)).isoformat(timespec="seconds")


class CanliSuzgec(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_canli_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.genel = os.path.join(self.proje, "genel")
        os.makedirs(self.genel)
        self.niyet_yolu = os.path.join(self.genel, "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", self.niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", self.genel),
                   mock.patch.dict(os.environ, {}, clear=False)]
        for p in self._p:
            p.start()
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.environ.pop("ORKESTRA_RUYA", None)
        os.environ.pop("ORKESTRA_PERSPEKTIF", None)

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def yol(self, aid):
        return os.path.join(self.sd, "oturumlar", f"acik_ajan_{aid}.json")

    def kayit(self, aid, dk, oturum="o-1", **ek):
        d = {"zaman": dk_once(dk), "oturum": oturum, "agent_id": aid, "ajan": "orkestra:isci-t2", "gorev": "G-001", "surec": "is"}
        d.update(ek)
        with open(self.yol(aid), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def niyet_yaz(self, oturum, tur, dk):
        with open(self.niyet_yolu, "a", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": dk_once(dk), "oturum": oturum, "proje": self.proje, "tur": tur}) + "\n")

    def calistir(self, fn, girdi):
        g = {"session_id": "o-1", "cwd": self.proje, "transcript_path": os.path.join(self.proje, "yok.jsonl")}
        g.update(girdi)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            fn(g)
        return buf.getvalue()

    # --- Kriter 1
    def test_session_end_kendi_kayitlarini_siler_digerlerine_dokunmaz(self):
        self.kayit("a", 5, oturum="o-1")
        self.kayit("b", 50, oturum="o-1")
        self.kayit("c", 5, oturum="o-2")
        self.kayit("d", 50, oturum="o-2")
        self.calistir(hook.session_end, {"session_id": "o-1"})
        self.assertFalse(os.path.exists(self.yol("a")))
        self.assertFalse(os.path.exists(self.yol("b")))
        self.assertTrue(os.path.exists(self.yol("c")))
        self.assertTrue(os.path.exists(self.yol("d")))

    def test_session_end_kayit_yoksa_hata_vermez(self):
        self.calistir(hook.session_end, {"session_id": "o-1"})

    def test_session_end_bozuk_kayit_digerlerini_engellemez(self):
        with open(self.yol("bozuk"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.kayit("a", 5, oturum="o-1")
        self.calistir(hook.session_end, {"session_id": "o-1"})
        self.assertFalse(os.path.exists(self.yol("a")))

    # --- Kriter 2
    def test_kapanmis_oturum_dondurulmez_ve_silinir(self):
        self.kayit("olu", 45, oturum="o-1")
        self.kayit("canli", 45, oturum="o-2")
        self.niyet_yaz("o-1", "kapandi", 40)
        self.niyet_yaz("o-2", "niyet", 1)
        a = ozet.asili_ajanlar(self.sd)
        self.assertEqual([x["agent_id"] for x in a], ["canli"])
        self.assertFalse(os.path.exists(self.yol("olu")))
        self.assertTrue(os.path.exists(self.yol("canli")))

    def test_kapandi_sonra_yeniden_acilan_oturum_canli(self):
        # kapandi olayından SONRA yeni olay varsa oturum yeniden açılmıştır (resume)
        self.kayit("a", 45, oturum="o-1")
        self.niyet_yaz("o-1", "kapandi", 30)
        self.niyet_yaz("o-1", "niyet", 2)
        self.assertEqual([x["agent_id"] for x in ozet.asili_ajanlar(self.sd)], ["a"])

    # --- Kriter 3
    def test_sessiz_saat_sabiti(self):
        self.assertEqual(ozet.ASILI_OTURUM_SESSIZ_SAAT, 2)

    def test_uzun_suredir_sessiz_oturum_dondurulmez_ve_silinir(self):
        self.kayit("a", 300, oturum="o-1")
        self.niyet_yaz("o-1", "niyet", 3 * 60)
        self.assertEqual(ozet.asili_ajanlar(self.sd), [])
        self.assertFalse(os.path.exists(self.yol("a")))

    def test_yeni_olayli_oturumun_otuz_dakika_asan_kaydi_uyari_doner(self):
        self.kayit("a", 90, oturum="o-1")
        self.niyet_yaz("o-1", "niyet", 5)
        a = ozet.asili_ajanlar(self.sd)
        self.assertEqual([x["agent_id"] for x in a], ["a"])
        self.assertTrue(os.path.exists(self.yol("a")))

    def test_sessizlik_siniri_iki_saatin_altinda_korunur(self):
        self.kayit("a", 200, oturum="o-1")
        self.niyet_yaz("o-1", "niyet", 110)  # 1 sa 50 dk: eşik altı
        self.assertEqual([x["agent_id"] for x in ozet.asili_ajanlar(self.sd)], ["a"])

    def test_son_olay_esas_alinir_eski_olay_degil(self):
        self.kayit("a", 600, oturum="o-1")
        self.niyet_yaz("o-1", "niyet", 500)
        self.niyet_yaz("o-1", "sonuc", 10)
        self.assertEqual([x["agent_id"] for x in ozet.asili_ajanlar(self.sd)], ["a"])

    # --- Kriter 5 (geriye uyum): niyet kaydı olmayan oturum süzülmez
    def test_niyet_kaydi_olmayan_oturum_eski_kuralla_calisir(self):
        self.kayit("a", 40, oturum="o-yok")
        self.kayit("b", 25 * 60, oturum="o-yok")
        self.assertEqual([x["agent_id"] for x in ozet.asili_ajanlar(self.sd)], ["a"])
        self.assertFalse(os.path.exists(self.yol("b")))

    def test_otuz_dakika_esigi_canli_oturumda_korunur(self):
        self.kayit("eski", 31, oturum="o-1")
        self.kayit("yeni", 5, oturum="o-1")
        self.niyet_yaz("o-1", "niyet", 1)
        self.assertEqual([x["agent_id"] for x in ozet.asili_ajanlar(self.sd)], ["eski"])

    # --- Kriter 4
    def test_baglam_yalniz_kendi_oturumunun_ajanlarini_gosterir(self):
        self.kayit("benim", 45, oturum="o-1", ajan="orkestra:benim-ajan")
        self.kayit("baskasi", 45, oturum="o-2", ajan="orkestra:baskasi-ajan")
        self.niyet_yaz("o-1", "niyet", 1)
        self.niyet_yaz("o-2", "niyet", 1)
        for fn, ek in ((hook.session_start, {"source": "startup"}), (hook.user_prompt_submit, {"prompt": "merhaba"})):
            ctx = json.loads(self.calistir(fn, ek))["hookSpecificOutput"]["additionalContext"]
            self.assertIn("orkestra:benim-ajan", ctx)
            self.assertNotIn("orkestra:baskasi-ajan", ctx)

    def test_baglam_yalniz_baska_oturumun_kaydi_varsa_uyari_yok(self):
        self.kayit("baskasi", 45, oturum="o-2")
        self.niyet_yaz("o-2", "niyet", 1)
        out = self.calistir(hook.session_start, {"source": "startup"})
        self.assertNotIn("bitmeyen ajan", out)
        out = self.calistir(hook.user_prompt_submit, {"prompt": "merhaba"})
        self.assertNotIn("bitmeyen ajan", out)


if __name__ == "__main__":
    unittest.main()
