"""I-318 / ADR-0133: bağsız oturumda dosya yazan kabuk komutu kapıdan geçer; onay bekleyen işte proje dışı kalıcı yol da.
Her vaka gerçek pre_tool_use hook'unu çağırır. Kapı fail-open olduğu için her vakada önce aynı kurulumda Write'ın
reddedildiği gösterilir (boş geçme önlemi).
"""
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
import is_kaydi  # noqa: E402
import is_onay  # noqa: E402

OTURUM = "kabuk1234567890-oturum"

# Meşru komutlar: bağsız oturumda da reddedilmemeli (yanlış pozitif eşiği: hiçbiri reddedilmez).
def mesru(gecici):
    return [
        "ls -la",
        "git status",
        "git log --oneline | head -5",
        "git diff --stat",
        "python -m pytest -q tests/test_x.py",
        "echo merhaba 2>&1",
        "cat README.md",
        "grep -rn bugun src | head",
        "python -c \"print(open('a.txt').read())\"",
        "python scripts/x.py --json 2>&1 | tail -3",
        "orkestra is liste > /dev/null 2>&1",
        "python - <<'EOF'\nprint(open('a.txt', 'r').read())\nEOF",
        f"git log --oneline > {gecici}/log.txt",
        f"cp a.txt {gecici}/yedek.txt",
    ]


class _Kabuk(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kabuk_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        # Gerçek %TEMP% proje dizinini de kapsar; testte geçici kök proje dışında ayrı bir dizindir.
        self.gecici = tempfile.mkdtemp(prefix="ork_gecici_").replace(os.sep, "/")
        self._gk = mock.patch.object(is_onay, "_gecici_kokler", lambda: [self.gecici, os.path.expanduser("~/.claude")])
        self._gk.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_IS_KAPISI",
                  "ORKESTRA_BAGSIZ_KABUK_KAPISI", "ORKESTRA_ONAY_KAPISI"):
            os.environ.pop(k, None)
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje
        os.environ["ORKESTRA_SIRA_KAPISI"] = "0"
        # merkez kayıt şart: iş sistemi hiç kullanılmamış projede kapı bilerek serbesttir
        self.a = is_kaydi.is_ac(self.sd, "Fatura raporlama entegrasyonu", os.path.join(self.proje, "isler", "001-fatura"))

    def tearDown(self):
        self._gk.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.gecici, ignore_errors=True)

    def baglan(self, oid=OTURUM):
        with open(os.path.join(self.sd, "oturumlar", oid + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": self.a["id"]}, f)

    def pre(self, arac, yol=None, komut=None, **ek):
        girdi = {"tool_name": arac, "cwd": self.proje, "session_id": OTURUM,
                 "tool_input": {"file_path": yol, "content": "x"} if yol else {"command": komut or "echo merhaba"}}
        girdi.update(ek)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(girdi)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        if not ham:
            return False, ""
        h = json.loads(ham.splitlines()[-1]).get("hookSpecificOutput", {})
        return h.get("permissionDecision") == "deny", h.get("permissionDecisionReason", "")

    def kod(self, ad="uygulama.py"):
        return os.path.join(self.proje, "src", ad)

    def kabuk(self, komut, **ek):
        return self.pre("Bash", komut=komut, **ek)

    def gunluk(self, tur):
        try:
            with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
                return [json.loads(s) for s in f if s.strip() and json.loads(s).get("tur") == tur]
        except OSError:
            return []

    def kok_kurulum_dogrula(self):
        """Boş geçme önlemi: aynı kurulumda Write reddedilir, yani kapı gerçekten devrede."""
        self.assertTrue(self.pre("Write", self.kod())[0])


class BagsizKabukReddi(_Kabuk):
    def test_yazma_yollari_reddedilir(self):
        self.kok_kurulum_dogrula()
        vakalar = [
            "echo x > src/a.py",
            "echo x >> src/a.py",
            "echo x | tee src/a.py",
            "sed -i s/a/b/ src/a.py",
            "cp tmp.txt src/b.py",
            "mv tmp.txt src/b.py",
            "rm src/a.py",
            "python - <<'EOF'\nopen('src/a.py', 'w').write('x')\nEOF",
            "python - <<'EOF'\nopen(yol, 'w').write('x')\nEOF",
            "python - <<'EOF'\nfrom pathlib import Path\nPath('src/a.py').write_text('x')\nEOF",
        ]
        for komut in vakalar:
            with self.subTest(komut=komut):
                deny, neden = self.kabuk(komut)
                self.assertTrue(deny, komut)
                self.assertIn("orkestra is devam", neden)
                self.assertIn("kabuk komutu", neden)

    def test_powershell_yazimi_reddedilir(self):
        self.kok_kurulum_dogrula()
        self.assertTrue(self.pre("PowerShell", komut="Set-Content -Path src/a.py -Value x")[0])

    def test_alt_ajan_kabuk_yazimi_da_reddedilir(self):
        self.kok_kurulum_dogrula()
        self.assertTrue(self.kabuk("echo x > src/a.py", agent_id="a123456", agent_type="orkestra:isci")[0])

    def test_red_metni_kapsami_dogru_soyler(self):
        deny, neden = self.kabuk("echo x > src/a.py")
        self.assertTrue(deny)
        self.assertIn("dosya yazan kabuk komutu", neden)
        self.assertNotIn("bağlanmadan dosya yazılamaz", neden)

    def test_bagli_oturum_serbest(self):
        self.baglan()
        self.assertFalse(self.kabuk("echo x > src/a.py")[0])


class YanlisPozitifVeMuafiyet(_Kabuk):
    def test_mesru_komutlar_reddedilmez(self):
        self.kok_kurulum_dogrula()
        self.assertGreaterEqual(len(mesru(self.gecici)), 12)
        for komut in mesru(self.gecici):
            with self.subTest(komut=komut):
                self.assertFalse(self.kabuk(komut)[0], komut)

    def test_gecici_dizine_yazim_serbest(self):
        self.kok_kurulum_dogrula()
        self.assertFalse(self.kabuk(f"echo x > {self.gecici}/a.txt")[0])
        self.assertFalse(self.kabuk("python - <<'EOF'\nopen('" + self.gecici + "/a.txt', 'w').write('x')\nEOF")[0])


class ModVeKapatma(_Kabuk):
    def test_env_kapatir(self):
        self.kok_kurulum_dogrula()
        os.environ["ORKESTRA_BAGSIZ_KABUK_KAPISI"] = "0"
        self.assertFalse(self.kabuk("echo x > src/a.py")[0])

    def test_golge_modu_engellemez_ama_kaydeder(self):
        self.kok_kurulum_dogrula()
        with open(os.path.join(self.sd, "bagsiz_kabuk.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "golge"}, f)
        self.assertFalse(self.kabuk("echo x > src/a.py")[0])
        self.assertTrue(self.gunluk("kapi_golge"))
        self.assertFalse(self.gunluk("kapi_ret"))

    def test_ihlal_modu_ret_kaydeder(self):
        self.kok_kurulum_dogrula()
        self.assertTrue(self.kabuk("echo x > src/a.py")[0])
        self.assertTrue(self.gunluk("kapi_ret"))

    def test_kapi_hatasinda_serbest(self):
        self.kok_kurulum_dogrula()
        with mock.patch.object(is_onay, "kabuk_kalici_yazimlar", side_effect=RuntimeError("bozuk")):
            self.assertFalse(self.kabuk("echo x > src/a.py")[0])

    def test_oturum_kimligi_yoksa_serbest(self):
        self.kok_kurulum_dogrula()
        self.assertFalse(self.kabuk("echo x > src/a.py", session_id=None)[0])


class OnayBeklerkenProjeDisi(_Kabuk):
    """S3: onay bekleyen bağlı işte proje dışındaki kalıcı yol (başka depo, eklenti kaynağı) kapıda, geçici dizin serbest."""

    def setUp(self):
        super().setUp()
        os.environ["ORKESTRA_SIRA_KAPISI"] = "1"
        os.environ["ORKESTRA_DOGRULAMA_KAPISI"] = "0"
        self.sd2 = self.sd
        self.b = is_kaydi.is_ac(self.sd, "Onay bekleyen iş", os.path.join(self.proje, "isler", "002-onay"))
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": self.b["id"]}, f)
        self.disarda = tempfile.mkdtemp(prefix="ork_disarda_", dir=os.path.dirname(self.proje))
        self.dis_dosya = os.path.join(self.disarda, "eklenti", "scripts", "hook.py")

    def tearDown(self):
        shutil.rmtree(self.disarda, ignore_errors=True)
        super().tearDown()

    def test_kurulum_onay_bekliyor(self):
        self.assertEqual(is_kaydi.is_al(self.sd, self.b["id"]).get("onay"), "bekliyor")
        self.assertTrue(self.pre("Write", self.kod())[0])

    def test_proje_disi_write_reddedilir(self):
        deny, neden = self.pre("Write", self.dis_dosya)
        self.assertTrue(deny)
        self.assertIn("proje dışındaki kalıcı yola", neden)

    def test_proje_disi_kabuk_yazimi_reddedilir(self):
        self.assertTrue(self.pre("Bash", komut=f"echo x > {self.dis_dosya.replace(os.sep, '/')}")[0])

    def test_gecici_dizin_ve_kullanici_klasoru_serbest(self):
        self.assertFalse(self.pre("Write", os.path.join(self.gecici, "x", "a.txt"))[0])
        self.assertFalse(self.pre("Write", os.path.expanduser("~/.claude/projects/x/memory/not.md"))[0])
        self.assertFalse(self.pre("Bash", komut=f"echo x > {self.gecici}/a.txt")[0])


class GeciciYol(unittest.TestCase):
    def test_gecici_yol_mu(self):
        self.assertTrue(is_onay.gecici_yol_mu(os.path.join(tempfile.gettempdir(), "x", "y.txt")))
        self.assertTrue(is_onay.gecici_yol_mu(os.path.expanduser("~/.claude/settings.json")))
        self.assertFalse(is_onay.gecici_yol_mu(os.path.join(KOK, "scripts", "hook.py")))


if __name__ == "__main__":
    unittest.main()
