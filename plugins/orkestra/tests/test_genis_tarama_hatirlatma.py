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

    def test_ayar_reddet(self):
        with open(AYAR, encoding="utf-8") as f:
            a = json.load(f)
        for k in ("mod", "hatirlatma", "komut_kaliplari", "zaman_siniri_kaliplari", "genis_kok_kaliplari",
                  "arka_plana_dusen_kaliplari", "reddet_kaliplari", "muafiyet_kaliplari", "reddet_metni", "onek"):
            self.assertIn(k, a)
        self.assertEqual(a["mod"], "reddet")  # ADR-0120, kullanıcı kararı D1 (31.10.2026): dar sınıf (find) baştan reddedilir
        self.assertIn(a["mod"], GT.MODLAR)

    def test_modulde_kalip_sabiti_yok(self):
        with open(MODUL, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        belge = {id(n.value) for n in ast.walk(agac) if isinstance(n, ast.Expr)}  # docstring ifadeleri
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str) and id(d) not in belge:
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
        self.assertEqual(kayit[0]["mod"], "reddet")  # grep -r reddet_kaliplari'nda değil: yalnız uyarı
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


# ADR-0120 derlemi: gerçek oturum kayıtlarından (1375 Bash `find`/`grep -r` komutu, 31.10.2026) seçilmiş reddedilmesi gerekenler
# ve gerçek meşru komutlar; ikisi de elle sınıflandı.
REDDEDILMELI = ["find /c/Mert/McD -name karar_kapisi.py",
                "find / -name panel.py -path '*orkestra*' 2>/dev/null | grep -v node_modules | head",
                "find / -name 'pe41-deck*' 2>/dev/null | head",
                "find / -ipath '*orkestra*' -name 'panel*' -not -path '*/node_modules/*' 2>/dev/null | head",
                "find /c/Mert/McD -iname '*rakip*' -o -iname '*karsilastir*' 2>/dev/null",
                "find /c/Users/PC /c/Mert -iname '*rakip_karsilastirmasi*' 2>/dev/null | head",
                "find /c/Users/PC/Desktop /c/Users/PC/Downloads /c/Mert -newer x",
                "find /c/Users/PC/.claude/plugins -name 'perspektif-ajani.md' 2>/dev/null",
                "find 'C:/Mert' 'C:/Users/PC/Desktop' -iname '*acik_ve_profesyonel*' 2>/dev/null",
                "cd /c/Mert/McD && find /c/Mert/McD -name '*.py'",
                "ls /c/Users/PC/Desktop; find /c/Mert -name x",
                "find ~ -name '*.log'",
                "find /c/Users -name x"]
GECMELI = ["timeout 20 find /c/Mert/McD -name karar_kapisi.py",
           "find /c/Mert/McD -maxdepth 1 -name x",
           "find /c/Mert/McD -name node_modules -prune -o -name x -print",
           "find . -name '*.py'",
           "find Claude_Orkestrasyon/isler -name 'plan.md'",
           "find /c/Mert/McD/RNV/063-x -name '*.md'",
           "find /c/Users/PC/.claude/projects/C--Mert-McD/memory -name '*.md'",
           "find $s -type f | wc -l",
           "echo \"$(grep -rlic 'a\\|b' $s | wc -l) dosya / $(find $s -type f | wc -l)\"",
           "git ls-files | grep -i taslak; find / -maxdepth 0",
           "timeout 30 find / -name x",
           "ls /c/Users/PC/Desktop",
           "grep foo /c/Mert/McD/dosya.txt",
           "git log --oneline -3 -- Claude_Orkestrasyon/",
           "cat /c/Users/PC/.claude/projects/C--Mert-McD/memory/MEMORY.md",
           "py -3.13 -m pytest -q tests/test_x.py",
           "python3 -c \"print('find / -name x')\" | head"]


class TestReddetKipi(_Proje):
    """ADR-0120: geniş kökte zaman sınırsız `find` komut koşmadan reddedilir; meşru komut geçer."""

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

    def test_derlem_reddedilir(self):
        self.assertGreaterEqual(len(REDDEDILMELI) + len(GECMELI), 30)
        for m in REDDEDILMELI:
            with self.subTest(m=m):
                self.assertTrue(GT.reddet_metni(m, self.sd), m)

    def test_derlem_gecer_yanlis_pozitif_sifir(self):
        for m in GECMELI:
            with self.subTest(m=m):
                self.assertEqual(GT.reddet_metni(m, self.sd), "", m)

    def test_ret_metni_hazir_duzeltilmis_komutu_verir(self):
        metin = GT.reddet_metni("find /c/Mert/McD -name x", self.sd)
        self.assertIn("timeout 20 find /c/Mert/McD -name x", metin)
        self.assertIn("Glob", metin)

    def test_hook_find_komutunu_kosmadan_reddeder(self):
        ho = self.pre("find /c/Mert/McD -name karar_kapisi.py").get("hookSpecificOutput", {})
        self.assertEqual(ho.get("permissionDecision"), "deny")
        self.assertIn("timeout 20 find", ho.get("permissionDecisionReason", ""))
        kayit = [g for g in self.gunluk() if g.get("kural") == "genis_tarama"]
        self.assertEqual([g["tur"] for g in kayit], ["kapi_ret"])
        self.assertEqual(kayit[0]["mod"], "reddet")

    def test_hook_mesru_find_gecer(self):
        for m in GECMELI[:4]:
            with self.subTest(m=m):
                self.assertNotEqual(self.pre(m).get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_grep_r_yalniz_uyarir(self):
        self.assertEqual(GT.reddet_metni("grep -r foo C:/Users/PC", self.sd), "")
        self.assertTrue(GT.ihlal_mi("grep -r foo C:/Users/PC", self.sd))

    def test_golge_kipinde_reddetmez(self):
        self.proje_ayari({"mod": "golge"})
        self.assertEqual(GT.reddet_metni("find /c/Mert/McD -name x", self.sd), "")
        self.assertNotEqual(self.pre("find /c/Mert/McD -name x").get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_ortam_degiskeni_kapatir(self):
        os.environ["ORKESTRA_GENIS_TARAMA"] = "0"
        self.assertEqual(GT.reddet_metni("find /c/Mert/McD -name x", self.sd), "")


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
