"""I-433 (Jira ORKESTRA-9, ORKESTRA-12): teslim kapısı uzak depo adı ayarı, `is kapat --yerel-birlesme`, ajanın kapı
atlatma komutları (gölge/ihlal) ve PR/kullanıcı kararı bekleyen işte kapanış hatırlatması.
Geçici projede koşar; CLI ve hook süreç içinde (ic_kos) çağrılır, ağ yok."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(TC.KOK, "scripts"))
import kapi_mod as KM  # noqa: E402
import teslim as T  # noqa: E402

ESKI = "2000-01-01T00:00:00+00:00"


def git(kok, *args):
    return subprocess.run(["git", "-C", kok, *args], check=True, capture_output=True, text=True).stdout.strip()


def git_hazirla(kok):
    git(kok, "init", "-q")
    git(kok, "config", "user.email", "t@t")
    git(kok, "config", "user.name", "t")
    git(kok, "config", "commit.gpgsign", "false")


class UzakDepoAdi(unittest.TestCase):
    """(a) teslim kapısı ayardaki uzak depo adına bakar."""

    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_i433_uzak_")
        self.addCleanup(shutil.rmtree, self.kok, True)
        git_hazirla(self.kok)
        os.makedirs(os.path.join(self.kok, ".claude", "orkestra"))
        self.klasor = os.path.join(self.kok, "is1")
        os.makedirs(self.klasor)
        with open(os.path.join(self.klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("x")
        git(self.kok, "add", "-A")
        git(self.kok, "commit", "-qm", "ilk")
        os.makedirs(os.path.join(self.kok, "modul"))
        with open(os.path.join(self.kok, "modul", "a.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        self.kayit = {"id": "I-1", "klasor": self.klasor, "olusturma": ESKI}
        env = mock.patch.dict(os.environ, {"ORKESTRA_TESLIM_KAPISI": "1"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def ayar_yaz(self, d):
        with open(os.path.join(self.kok, ".claude", "orkestra", "teslim.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def eksik(self):
        with mock.patch.object(KM, "mod", return_value="ihlal"), mock.patch.object(T, "pr_oku", return_value=None):
            return T.teslim_eksigi(self.kok, self.kayit)

    def test_upstream_ayarliysa_o_depoya_bakar(self):
        git(self.kok, "remote", "add", "upstream", "https://example.invalid/x/y.git")
        self.assertEqual(T.uzak_adi(self.klasor), "origin")
        self.assertEqual(self.eksik(), [], "varsayılan origin yok: kapı susar")
        self.ayar_yaz({"uzak_depo": "upstream"})
        self.assertEqual(T.uzak_adi(self.klasor), "upstream")
        e = self.eksik()
        self.assertTrue(e and "PR" in e[0], e)

    def test_ayardaki_uzak_depoda_yoksa_kapi_susar(self):
        git(self.kok, "remote", "add", "origin", "https://example.invalid/x/y.git")
        self.ayar_yaz({"uzak_depo": "upstream"})
        self.assertEqual(self.eksik(), [])

    def test_eklenti_varsayilani_origin(self):
        with open(os.path.join(TC.KOK, "ayarlar", "teslim.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("uzak_depo"), "origin")


class YerelBirlesme(unittest.TestCase):
    """(b) --yerel-birlesme ana dalda olmayan commit'i reddeder, ana daldakini kabul eder; ajan oturumunda reddedilir."""
    setUp_ = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def setUp(self):
        self.setUp_()
        git_hazirla(self.proje)
        git(self.proje, "checkout", "-q", "-b", "main")
        git(self.proje, "remote", "add", "origin", "https://example.invalid/x/y.git")
        self.klasor = os.path.join(self.proje, "is1")
        r = self.kos("is", "ac", "Yerel birleşme işi", "--klasor", self.klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        git(self.proje, "add", "-A")
        git(self.proje, "commit", "-qm", "ilk")
        os.makedirs(os.path.join(self.proje, "modul"))
        with open(os.path.join(self.proje, "modul", "a.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        git(self.proje, "add", "modul/a.py")
        git(self.proje, "commit", "-qm", "kod")
        self.ana_sha = git(self.proje, "rev-parse", "HEAD")
        git(self.proje, "checkout", "-q", "-b", "yan")
        with open(os.path.join(self.proje, "modul", "b.py"), "w", encoding="utf-8") as f:
            f.write("y = 2\n")
        git(self.proje, "add", "modul/b.py")
        git(self.proje, "commit", "-qm", "yan")
        self.yan_sha = git(self.proje, "rev-parse", "HEAD")
        git(self.proje, "checkout", "-q", "main")

    def kos(self, *args, ajan=False, **ortam):
        a = [TC.CLI] + list(args) + (["--ajan-id", "ana", "--ajan-tipi", "ana"] if ajan else [])
        return TC.kos(a, self.proje, ortam={"ORKESTRA_TESLIM_KAPISI": "1", **ortam})

    def is_json(self):
        with open(os.path.join(self.klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_ana_dalda_olmayan_commit_reddedilir(self):
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.yan_sha)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ana dalda", r.stderr)
        self.assertEqual(self.is_json().get("durum"), "acik")
        self.assertNotIn("yerel_birlesme", self.is_json().get("teslim") or {})

    def test_ana_daldaki_commit_kabul_edilir_ve_kaydedilir(self):
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.ana_sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.is_json()
        self.assertEqual(k.get("durum"), "kapandi")
        self.assertEqual(k["teslim"]["yerel_birlesme"]["commit"], self.ana_sha)
        self.assertEqual(k["teslim"]["yerel_birlesme"]["dal"], "main")
        self.assertNotIn("bekliyor", k)

    def test_ozet_kapisi_yine_calisir(self):
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.ana_sha, ORKESTRA_OZET_KAPISI="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("görev bitiş raporu", r.stderr)
        self.assertEqual(self.is_json().get("durum"), "acik")

    def test_ajan_oturumunda_reddedilir(self):
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.ana_sha, ajan=True)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("kendi terminalinde", r.stderr)
        self.assertEqual(self.is_json().get("durum"), "acik")

    def test_pr_beklenen_kapanis_reddi_isi_bekliyor_isaretler(self):
        with mock.patch.object(T, "pr_oku", return_value=None), mock.patch.object(T.shutil, "which", return_value="gh"):
            r = self.kos("is", "kapat", "I-001")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("teslim eksik", r.stderr)
        self.assertIn("PR", self.is_json().get("bekliyor", ""))

    def test_ana_dal_ayardan_okunur(self):
        with open(os.path.join(self.sd, "teslim.json"), "w", encoding="utf-8") as f:
            json.dump({"ana_dal": "yan"}, f)
        self.assertEqual(T.ana_dal(self.proje, self.klasor), "yan")
        kanit, _ = T.yerel_birlesme_dogrula(self.proje, self.yan_sha, self.klasor)
        self.assertEqual(kanit["dal"], "yan")


class KapiAtlatma(unittest.TestCase):
    """(c) ajan oturumunda --ozetsiz ve ORKESTRA_*_KAPISI=0: ihlalde ret, gölgede geçer + kapi_golge."""
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    hook = TC.Cekirdek.hook
    karar = TC.Cekirdek.karar

    KOMUTLAR = [("Bash", 'orkestra is kapat I-001 --ozetsiz "iş yapılmadı"'),
                ("Bash", "ORKESTRA_TESLIM_KAPISI=0 orkestra is kapat I-001"),
                ("Bash", "export ORKESTRA_TESLIM_KAPISI=0 && orkestra is kapat I-001"),
                ("Bash", "cd x; ORKESTRA_OZET_KAPISI=off python orkestra.py is kapat I-001"),
                ("PowerShell", '$env:ORKESTRA_TESLIM_KAPISI = "0"; orkestra is kapat I-001'),
                ("Bash", 'set "ORKESTRA_ADR_KAPISI=false"')]

    def pre(self, arac, komut):
        return self.hook("PreToolUse", {"tool_name": arac, "tool_input": {"command": komut}})

    def golge_kayitlari(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [o for o in (json.loads(s) for s in f if s.strip()) if o.get("tur") == "kapi_golge" and o.get("kapi") == "kapi_atlatma"]

    def test_golge_modda_gecer_ve_kapi_golge_yazar(self):
        for arac, komut in self.KOMUTLAR:
            with self.subTest(komut=komut):
                o = self.pre(arac, komut)
                self.assertNotEqual(self.karar(o), "deny", o)
        neden = " ".join(k["neden"] for k in self.golge_kayitlari())
        self.assertIn("--ozetsiz", neden)
        self.assertIn("ORKESTRA_TESLIM_KAPISI=0", neden)
        self.assertIn("ORKESTRA_OZET_KAPISI=0", neden)
        self.assertIn("ORKESTRA_ADR_KAPISI=0", neden)

    def test_golge_uyarisi_modele_ulasir(self):
        o = self.pre("Bash", 'orkestra is kapat I-001 --ozetsiz "x"')
        self.assertIn("kapi_atlatma", (o.get("hookSpecificOutput") or {}).get("additionalContext", ""))

    def test_ihlal_modda_reddedilir(self):
        with open(os.path.join(self.sd, "kapi_atlatma.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "ihlal"}, f)
        for arac, komut in self.KOMUTLAR:
            with self.subTest(komut=komut):
                o = self.pre(arac, komut)
                self.assertEqual(self.karar(o), "deny", o)
                self.assertIn("kendi terminalinde", o["hookSpecificOutput"]["permissionDecisionReason"])

    def test_masum_komutlar_kayit_dusmez(self):
        with open(os.path.join(self.sd, "kapi_atlatma.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "ihlal"}, f)
        for komut in ("orkestra is kapat I-001", "echo ORKESTRA_TESLIM_KAPISI", "ORKESTRA_TESLIM_KAPISI=1 orkestra is liste",
                      'git commit -m "orkestra is kapat --ozetsiz anlatımı"'):
            with self.subTest(komut=komut):
                self.assertNotEqual(self.karar(self.pre("Bash", komut)), "deny")
        self.assertEqual(self.golge_kayitlari(), [])

    def test_yerel_birlesme_ajan_kabugunda_golgede_de_reddedilir(self):
        o = self.pre("Bash", "true; orkestra is kapat I-001 --yerel-birlesme abc123")
        self.assertEqual(self.karar(o), "deny", o)
        self.assertIn("kendi terminalinde", o["hookSpecificOutput"]["permissionDecisionReason"])


class BekliyorHatirlatma(unittest.TestCase):
    """(d) PR/kullanıcı kararı bekleyen işte hatırlatma 'kapat' demez, 'kullanıcı kararını bekle' der."""
    setUp_ = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    hook = TC.Cekirdek.hook

    def setUp(self):
        self.setUp_()
        self.klasor = os.path.join(self.proje, "is1")
        self.assertEqual(self.cli("is", "ac", "Bekleyen iş", "--klasor", self.klasor).returncode, 0)
        self.assertEqual(self.cli("is", "todo", "I-001", "--ekle", "tek madde").returncode, 0)

    def is_json(self):
        with open(os.path.join(self.klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_pr_kaydi_bekliyor_isaretler_ve_todo_hatirlatmasi_kapat_demez(self):
        r = self.cli("is", "teslim", "I-001", "--pr", "https://github.com/x/y/pull/7")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pull/7", self.is_json().get("bekliyor", ""))
        r = TC.kos([TC.CLI, "is", "todo", "I-001", "--bitti", "1"], self.proje, ortam={"ORKESTRA_OZET_KAPISI": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kullanıcı kararını bekle", r.stdout)
        self.assertNotIn("kapat", r.stdout.lower())
        self.assertNotIn("atla", r.stdout.lower())

    def test_stop_hatirlatmasi_bekliyor_iste_kapat_demez(self):
        self.cli("is", "teslim", "I-001", "--pr", "https://github.com/x/y/pull/7")
        self.cli("is", "todo", "I-001", "--bitti", "1")
        o = self.hook("Stop", {"stop_hook_active": False, "last_assistant_message": "tamam"})
        neden = o.get("reason", "")
        self.assertIn("kullanıcı kararını bekle", neden)
        self.assertNotIn("kapat", neden.lower())

    def test_bekliyor_olmayan_iste_eski_hatirlatma(self):
        r = TC.kos([TC.CLI, "is", "todo", "I-001", "--bitti", "1"], self.proje, ortam={"ORKESTRA_OZET_KAPISI": "1"})
        self.assertIn("orkestra is kapat I-001", r.stdout)

    def test_kapanis_teslim_reddi_bekliyor_isaretler_kapanis_siler(self):
        T.bekliyor_yaz(self.sd, "I-001", "teslim: PR bulunamadı")
        self.assertEqual(self.is_json().get("bekliyor"), "teslim: PR bulunamadı")
        self.assertEqual(self.cli("is", "kapat", "I-001").returncode, 0)
        self.assertNotIn("bekliyor", self.is_json())


class CaprazDepo(unittest.TestCase):
    """I-459: belgeleri bir depoda, kodu başka depoda olan iş `--yerel-birlesme <commit> --depo <yol>` ile teslim alır;
    commit kod deposunda, o deponun ayarıyla doğrulanır ve kapanışta kayıttaki depoda yeniden doğrulanır.
    İş deposunun uzak deposu yok (McD gibi); kod deposunun var."""
    setUp_ = TC.Cekirdek.setUp
    tearDown_ = TC.Cekirdek.tearDown

    def setUp(self):
        self.setUp_()
        git_hazirla(self.proje)
        self.klasor = os.path.join(self.proje, "is1")
        r = self.kos("is", "ac", "Çapraz depo işi", "--klasor", self.klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.kod = tempfile.mkdtemp(prefix="ork_kod_")
        git_hazirla(self.kod)
        git(self.kod, "checkout", "-q", "-b", "main")
        git(self.kod, "remote", "add", "origin", "https://example.invalid/x/kod.git")
        with open(os.path.join(self.kod, "a.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        git(self.kod, "add", "a.py")
        git(self.kod, "commit", "-qm", "kod")
        self.ana_sha = git(self.kod, "rev-parse", "HEAD")
        git(self.kod, "checkout", "-q", "-b", "yan")
        with open(os.path.join(self.kod, "b.py"), "w", encoding="utf-8") as f:
            f.write("y = 2\n")
        git(self.kod, "add", "b.py")
        git(self.kod, "commit", "-qm", "yan")
        self.yan_sha = git(self.kod, "rev-parse", "HEAD")
        git(self.kod, "checkout", "-q", "main")

    def tearDown(self):
        shutil.rmtree(self.kod, ignore_errors=True)
        self.tearDown_()

    def kos(self, *args, ajan=False, **ortam):
        a = [TC.CLI] + list(args) + (["--ajan-id", "ana", "--ajan-tipi", "ana"] if ajan else [])
        return TC.kos(a, self.proje, ortam={"ORKESTRA_TESLIM_KAPISI": "1", **ortam})

    def is_json(self):
        with open(os.path.join(self.klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_kod_deposundaki_ana_dal_commiti_kabul_ve_depo_kanitta(self):
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.ana_sha, "--depo", self.kod)
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.is_json()
        self.assertEqual(k.get("durum"), "kapandi")
        yb = k["teslim"]["yerel_birlesme"]
        self.assertEqual(yb["commit"], self.ana_sha)
        self.assertEqual(yb["dal"], "main")
        self.assertEqual(os.path.normcase(os.path.realpath(yb["depo"])), os.path.normcase(os.path.realpath(self.kod)))

    def test_depodaki_ana_dalda_olmayan_commit_reddedilir(self):
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.yan_sha, "--depo", self.kod)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ana dalda", r.stderr)
        self.assertEqual(self.is_json().get("durum"), "acik")

    def test_depo_olmadan_is_deposunda_aranir_ve_bulunmaz(self):
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.ana_sha)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("commit bulunamadı", r.stderr)

    def test_git_olmayan_depo_reddedilir(self):
        bos = tempfile.mkdtemp(prefix="ork_bos_")
        try:
            r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.ana_sha, "--depo", bos)
        finally:
            shutil.rmtree(bos, ignore_errors=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("git deposu değil", r.stderr)
        self.assertEqual(self.is_json().get("durum"), "acik")

    def test_depo_yerel_birlesmesiz_reddedilir(self):
        r = self.kos("is", "kapat", "I-001", "--depo", self.kod)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--yerel-birlesme", r.stderr)
        self.assertEqual(self.is_json().get("durum"), "acik")

    def test_ana_dal_kod_deposunun_ayarindan_okunur(self):
        os.makedirs(os.path.join(self.kod, ".claude", "orkestra"))
        with open(os.path.join(self.kod, ".claude", "orkestra", "teslim.json"), "w", encoding="utf-8") as f:
            json.dump({"ana_dal": "yan"}, f)
        # gerçek oturumdaki gibi proje dizini iş deposunu gösterir; ayar yine kod deposundan okunmalı
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.yan_sha, "--depo", self.kod,
                     CLAUDE_PROJECT_DIR=self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.is_json()["teslim"]["yerel_birlesme"]["dal"], "yan")

    def test_ajan_oturumunda_depo_ile_de_reddedilir(self):
        r = self.kos("is", "kapat", "I-001", "--yerel-birlesme", self.ana_sha, "--depo", self.kod, ajan=True)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("kendi terminalinde", r.stderr)
        self.assertEqual(self.is_json().get("durum"), "acik")

    def _kayit(self, yb):
        k = self.is_json()
        k["teslim"] = {"yerel_birlesme": yb} if yb else {}
        with open(os.path.join(self.klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False)
        return k

    def test_kapanista_kayittaki_depoda_yeniden_dogrulanir(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_TESLIM_KAPISI": "1"}):
            gecer = self._kayit({"commit": self.ana_sha, "dal": "main", "depo": self.kod})
            self.assertEqual(T.teslim_eksigi(self.sd, gecer), [])
            kalmaz = self._kayit({"commit": self.yan_sha, "dal": "main", "depo": self.kod})
            eksik = T.teslim_eksigi(self.sd, kalmaz)
        self.assertTrue(eksik, "ana dalda olmayan commit kapanışta geçmemeli")
        self.assertIn("doğrulanamadı", eksik[0])

    def test_silinmis_depo_kapanista_eksik_verir(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_TESLIM_KAPISI": "1"}):
            k = self._kayit({"commit": self.ana_sha, "dal": "main", "depo": os.path.join(self.kod, "yok")})
            self.assertTrue(T.teslim_eksigi(self.sd, k))

    def test_deposuz_eski_kayit_degismez(self):
        # iş deposunun uzak deposu yok: depo alanı olmayan kayıt eskisi gibi erken boş liste alır
        with mock.patch.dict(os.environ, {"ORKESTRA_TESLIM_KAPISI": "1"}):
            k = self._kayit({"commit": self.ana_sha, "dal": "main"})
            self.assertEqual(T.teslim_eksigi(self.sd, k), [])

    def test_ozet_gorunumu_depoyu_gosterir(self):
        import belge_gorunum as BG
        self.assertIn("depo", BG.yerel_birlesme_satiri({"commit": self.ana_sha, "depo": self.kod}))
        self.assertIn(self.ana_sha, BG.yerel_birlesme_satiri({"commit": self.ana_sha}))
        self.assertEqual(BG.yerel_birlesme_satiri(None), "—")


if __name__ == "__main__":
    unittest.main()
