"""P-012 madde 4 (I-194): geniş tarama gölge uyarısı (scripts/genis_tarama_hatirlatma.py), hook bağlantısı ve
zaman aşımıyla arka plana düşen komutun açık görev listesine girmesi (hook._acik_arka_plan).
`py -3.13 -m pytest -q plugins/orkestra/tests/test_genis_tarama_hatirlatma.py`
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
import genis_tarama_hatirlatma as GT  # noqa: E402

MODUL = os.path.join(KOK, "scripts", "genis_tarama_hatirlatma.py")
AYAR = os.path.join(KOK, "ayarlar", "genis_tarama_hatirlatma.json")
OTURUM = "genis12345678-oturum"

POZITIF = ["grep -r foo C:/Users/PC",
           "grep -rn 'x' C:\\Users\\PC\\Desktop",
           "grep -R foo /c/Users/PC",
           "grep --recursive foo ~",
           "find C:/Users/PC -name '*.py'",
           "find / -name x",
           "cd /tmp && grep -rl abc C:/Users",
           "grep -r foo C:/Mert/McD"]
NEGATIF = ["timeout 20 grep -r foo C:/Users/PC",
           "timeout 30 find C:/Users/PC -name x",
           "grep -r foo C:/Mert/McD/RNV/063-x",
           "grep foo C:/Users/PC/dosya.txt",
           "ls C:/Users/PC",
           "echo grep -r",
           "",
           None]
ZAMAN_ASIMI = ("Command did not complete within its 120s timeout and was moved to the background (ID: abc). "
               "Output is being written to: x.output. You will be notified when it completes.")


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_genis_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("ORKESTRA_GENIS_TARAMA", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp
        os.environ["ORKESTRA_SIRA_KAPISI"] = "0"
        os.environ["ORKESTRA_ONAY_KAPISI"] = "0"

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proje_ayari(self, icerik):
        with open(os.path.join(self.sd, GT.PROJE_DOSYA), "w", encoding="utf-8") as f:
            f.write(icerik if isinstance(icerik, str) else json.dumps(icerik))

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.isfile(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def ihlaller(self):
        return [g for g in self.gunluk() if g.get("kural") == "genis_tarama"]


class TestDosyalarVeAyar(unittest.TestCase):
    def test_dosyalar_var(self):
        self.assertTrue(os.path.isfile(MODUL))
        self.assertTrue(os.path.isfile(AYAR))

    def test_ayar_golge(self):
        with open(AYAR, encoding="utf-8") as f:
            a = json.load(f)
        for k in ("mod", "hatirlatma", "komut_kaliplari", "zaman_siniri_kaliplari", "genis_kok_kaliplari",
                  "arka_plana_dusen_kaliplari"):
            self.assertIn(k, a)
        self.assertEqual(a["mod"], "golge")  # P-028: ihlal moduna ölçümsüz geçilmez
        self.assertIn(a["mod"], GT.MODLAR)

    def test_modulde_kalip_sabiti_yok(self):
        with open(MODUL, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str):
                for w in ("grep", "timeout", "users", "moved to the background"):
                    self.assertNotIn(w, d.value.lower(), f"modülde kalıp sabiti: {d.value[:60]!r}")


class TestKaliplar(_Proje):
    def test_pozitif(self):
        for m in POZITIF:
            with self.subTest(m=m):
                self.assertTrue(GT.ihlal_mi(m, self.sd), m)

    def test_negatif(self):
        for m in NEGATIF:
            with self.subTest(m=m):
                self.assertFalse(GT.ihlal_mi(m, self.sd), m)

    def test_kapali_mod_ve_ortam_degiskeni(self):
        self.proje_ayari({"mod": "kapali"})
        self.assertFalse(GT.ihlal_mi(POZITIF[0], self.sd))
        self.proje_ayari({"mod": "golge"})
        os.environ["ORKESTRA_GENIS_TARAMA"] = "0"
        self.assertFalse(GT.ihlal_mi(POZITIF[0], self.sd))

    def test_bozuk_proje_ayari_varsayilana_duser(self):
        self.proje_ayari("{bozuk")
        self.assertTrue(GT.ihlal_mi(POZITIF[0], self.sd))

    def test_arka_plana_dustu(self):
        self.assertTrue(GT.arka_plana_dustu_mu(ZAMAN_ASIMI, self.sd))
        self.assertFalse(GT.arka_plana_dustu_mu("ok", self.sd))
        self.assertFalse(GT.arka_plana_dustu_mu(None, self.sd))


class TestHookBaglantisi(_Proje):
    def pre(self, komut):
        g = {"tool_name": "Bash", "cwd": self.tmp, "session_id": OTURUM, "tool_input": {"command": komut}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(g)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        return json.loads(ham.splitlines()[-1]) if ham else {}

    def test_ihlal_gunluge_yazilir_ve_engellenmez(self):
        cikti = self.pre("grep -r . C:/Users/PC")
        kayit = self.ihlaller()
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0]["tur"], "kural_ihlal")
        self.assertEqual(kayit[0]["mod"], "golge")
        ho = cikti.get("hookSpecificOutput", {})
        self.assertNotEqual(ho.get("permissionDecision"), "deny")
        self.assertIn("timeout", ho.get("additionalContext", ""))

    def test_timeout_lu_komut_kayit_uretmez(self):
        self.pre("timeout 20 grep -r . C:/Users/PC")
        self.assertEqual(self.ihlaller(), [])

    def test_kapali_modda_kayit_yok(self):
        self.proje_ayari({"mod": "kapali"})
        self.pre("grep -r . C:/Users/PC")
        self.assertEqual(self.ihlaller(), [])

    def test_modul_hata_atarsa_komut_gecer(self):
        with mock.patch.object(GT, "ihlal_mi", side_effect=RuntimeError("x")):
            cikti = self.pre("grep -r . C:/Users/PC")
        self.assertNotEqual(cikti.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")


class TestZamanAsimiAcikGorev(_Proje):
    def transkript(self, satirlar):
        yol = os.path.join(self.tmp, "t.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in satirlar) + "\n")
        return yol

    def sonuc(self, kim, metin):
        return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": kim, "content": metin}]}}

    def bildirim(self, kim, durum):
        return {"type": "user", "message": {"content": f"<task-notification><tool-use-id>{kim}</tool-use-id><status>{durum}</status></task-notification>"}}

    def kos(self, satirlar):
        yol = self.transkript(satirlar)
        return hook._acik_arka_plan(yol, 0, os.path.getsize(yol), [])

    def test_zaman_asimi_acik_listeye_girer(self):
        self.assertEqual(self.kos([self.sonuc("b1", ZAMAN_ASIMI)]), ["b1"])

    def test_blok_listesi_icerigi(self):
        self.assertEqual(self.kos([self.sonuc("b1", [{"type": "text", "text": ZAMAN_ASIMI}])]), ["b1"])

    def test_stopped_bildirimi_kapatir(self):
        self.assertEqual(self.kos([self.sonuc("b1", ZAMAN_ASIMI), self.bildirim("b1", "stopped")]), [])

    def test_completed_bildirimi_kapatir(self):
        self.assertEqual(self.kos([self.sonuc("b1", ZAMAN_ASIMI), self.bildirim("b1", "completed")]), [])

    def test_normal_sonuc_girmez_ve_tekrar_cogaltmaz(self):
        self.assertEqual(self.kos([self.sonuc("b1", "ok"), self.sonuc("b2", ZAMAN_ASIMI), self.sonuc("b2", ZAMAN_ASIMI)]), ["b2"])


if __name__ == "__main__":
    unittest.main()
