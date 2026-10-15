"""Kart çalışma ağacı + test kapısı: kilitli test, test_alani ve test-kos ağaçtaki karşılığa göre işler.

Her test geçici bir git deposu açar (tempfile); gerçek depoya dokunmaz.
`python -m unittest discover -s plugins/orkestra/tests -v`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
OTURUM = "agac-test-oturum"

KIRMIZI_TEST = ("import os, sys, unittest\n"
                "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"
                "import x\n"
                "class T(unittest.TestCase):\n"
                "    def test_f(self):\n"
                "        self.assertEqual(x.f(), 2)\n")


def kos(args, cwd, stdin=None):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run([sys.executable] + args, cwd=cwd, env=env, input=stdin, capture_output=True, text=True,
                          encoding="utf-8")


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)


class AgacTestKapisi(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_agt_"))
        self.proje = os.path.join(self.taban, "depo")
        os.makedirs(self.proje)
        git(self.proje, "init", "-q", "-b", "main")
        git(self.proje, "config", "user.name", "Test")
        git(self.proje, "config", "user.email", "test@example.invalid")
        git(self.proje, "config", "core.autocrlf", "false")
        yaz(os.path.join(self.proje, ".gitignore"), ".claude/\n__pycache__/\n")
        yaz(os.path.join(self.proje, "src", "x.py"), "def f():\n    return 1\n")
        yaz(os.path.join(self.proje, "tests", "test_x.py"), KIRMIZI_TEST)
        yaz(os.path.join(self.proje, "docs", "d.md"), "# d\n")
        git(self.proje, "add", ".")
        git(self.proje, "commit", "-q", "-m", "ilk")
        r = kos([CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli("kart", "yeni", "--baslik", "kod", "--basamak", "T2", "--kabul", "ok", "--sinif", "kod", "--tdd",
                     "--test-komutu", f'"{sys.executable}" -m unittest discover -s tests', "--test-alani", "tests/**",
                     "--yazma", "src/**", "--yazma", "tests/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.g = r.stdout.strip()

    def tearDown(self):
        for satir in git(self.proje, "worktree", "list", "--porcelain").splitlines():
            if satir.startswith("worktree ") and os.path.realpath(satir[9:]) != self.proje:
                subprocess.run(["git", "-C", self.proje, "worktree", "remove", "--force", satir[9:]], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)

    # ---------------------------------------------------------- yardımcılar
    def cli(self, *args, ajan_id="ana", ajan_tipi="ana"):
        return kos([CLI] + list(args) + ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi], self.proje)

    def kirmizi(self):
        r = self.cli("kart", "test-kos", self.g, "--asama", "kirmizi", ajan_id="tw", ajan_tipi="orkestra:isci-t2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def agac(self):
        r = self.cli("kart", "agac", self.g)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def karar(self, dosya, surec="is", ana=False, gorev=None):
        """(karar, neden) — karar None ise hook geçti."""
        girdi = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": "PreToolUse", "tool_name": "Write",
                 "tool_input": {"file_path": dosya, "content": "x"}}
        if not ana:
            # Etiket önbelleği (test_test_kilidi_hook.py ile aynı yol): hook #GOREV/#SUREC'i buradan okur.
            gorev = gorev or self.g
            aid = f"w-{gorev}-{surec}"
            yaz(os.path.join(self.proje, ".claude", "orkestra", "oturumlar", f"ajan_{aid}.json"),
                json.dumps({"gorev": gorev, "surec": surec, "ajan": "orkestra:isci-t2"}))
            girdi.update(agent_id=aid, agent_type="orkestra:isci-t2")
        r = kos([HOOK, "PreToolUse"], self.proje, stdin=json.dumps(girdi))
        self.assertEqual(r.returncode, 0, r.stderr)
        h = (json.loads(r.stdout) if r.stdout.strip() else {}).get("hookSpecificOutput") or {}
        return h.get("permissionDecision"), h.get("permissionDecisionReason") or ""

    # ---------------------------------------------------------- (a) ağaçtaki kilitli test
    def test_a_agactaki_kilitli_teste_test_yaz_ve_ana_ajan_yazamaz(self):
        self.kirmizi()
        yol = self.agac()
        hedef = os.path.join(yol, "tests", "test_x.py")
        for surec, ana in (("test-yaz", False), ("is", False), ("is", True)):
            k, neden = self.karar(hedef, surec, ana=ana)
            self.assertEqual(k, "deny", f"{surec} ana={ana}")
            self.assertIn("kilitli test", neden)
        # paylaşılan ağaçtaki karşılığı da kilitli kalır
        self.assertEqual(self.karar(os.path.join(self.proje, "tests", "test_x.py"), ana=True)[0], "deny")
        # kilitli olmayan ağaç dosyası ana ajana kilit gerekçesiyle kapanmaz
        k, neden = self.karar(os.path.join(yol, "src", "x.py"), ana=True)
        self.assertNotIn("kilitli test", neden)

    # ---------------------------------------------------------- (b) ağaçta test alanı / src
    def test_b_agacta_kod_iscisi_test_alanina_yazamaz_srcye_yazar(self):
        yol = self.agac()
        k, neden = self.karar(os.path.join(yol, "tests", "test_y.py"), "is")
        self.assertEqual(k, "deny")
        self.assertIn("test_alani", neden)
        self.assertIsNone(self.karar(os.path.join(yol, "src", "y.py"), "is")[0])
        self.assertIsNone(self.karar(os.path.join(yol, "tests", "test_y.py"), "test-yaz")[0])
        k, neden = self.karar(os.path.join(yol, "src", "y.py"), "test-yaz")
        self.assertEqual(k, "deny")
        self.assertIn("test-yaz yalnız test_alani", neden)

    # ---------------------------------------------------------- (c) sıra
    def test_c_sira_paylasilan_depo_test_alani_agac_yazma_alani(self):
        yol = self.agac()
        # 1) paylaşılan depo reddi test-yaz'ın test_alani geçişinden önce gelir
        for surec in ("test-yaz", "is"):
            k, neden = self.karar(os.path.join(self.proje, "tests", "test_y.py"), surec)
            self.assertEqual(k, "deny", surec)
            self.assertIn("çalışma ağacı var", neden, surec)
        # 2) ağaçta test alanı denetimi, ağaç yazma alanı denetiminden önce
        k, neden = self.karar(os.path.join(yol, "tests", "test_y.py"), "is")
        self.assertIn("test_alani", neden)
        # 3) test alanı dışı, yazma alanı dışı → ağaç yazma alanı reddi
        k, neden = self.karar(os.path.join(yol, "docs", "z.md"), "is")
        self.assertEqual(k, "deny")
        self.assertIn("yazma alanı dışında", neden)
        self.assertIn("çalışma ağacı:", neden)

    # ---------------------------------------------------------- (d) test-kos ağaçta
    def test_d_yesil_agactaki_kodla_gecer_bozuk_kilitli_test_gecmez(self):
        self.kirmizi()
        yol = self.agac()
        yaz(os.path.join(yol, "src", "x.py"), "def f():\n    return 2\n")  # düzeltme yalnız ağaçta
        r = self.cli("kart", "test-kos", self.g, "--asama", "yesil", ajan_id="tw", ajan_tipi="orkestra:isci-t2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GEÇTİ", r.stdout)
        # ağaçtaki kilitli test boşaltılır; paylaşılan ağaçta kod da düzeltilse yeşil geçmez
        yaz(os.path.join(yol, "tests", "test_x.py"),
            "import unittest\nclass T(unittest.TestCase):\n    def test_f(self):\n        pass\n")
        yaz(os.path.join(self.proje, "src", "x.py"), "def f():\n    return 2\n")
        r = self.cli("kart", "test-kos", self.g, "--asama", "yesil", ajan_id="tw", ajan_tipi="orkestra:isci-t2")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("kilitten saptı", r.stdout)

    # ---------------------------------------------------------- (e) kilit sahibi ≠ ağaç sahibi
    def test_e_baska_kartin_agacinda_kilitli_test_yazilamaz(self):
        self.kirmizi()  # G1 (self.g) tests/test_x.py'yi kilitler
        r = self.cli("kart", "yeni", "--baslik", "k2", "--basamak", "T2", "--kabul", "ok",
                     "--yazma", "tests/**", "--yazma", "src/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        g2 = r.stdout.strip()
        r = self.cli("kart", "agac", g2)
        self.assertEqual(r.returncode, 0, r.stderr)
        yol2 = r.stdout.strip()
        hedef = os.path.join(yol2, "tests", "test_x.py")
        yazimlar = [hedef]
        if os.name == "nt":
            yazimlar.append(hedef.upper().replace("/", "\\"))
        for dosya in yazimlar:
            for surec, ana in (("is", False), ("test-yaz", False), ("is", True)):
                k, neden = self.karar(dosya, surec, ana=ana, gorev=g2)
                self.assertEqual(k, "deny", f"{dosya} {surec} ana={ana}")
                self.assertIn("kilitli test", neden)
                self.assertIn(self.g, neden)  # kilit sahibi G1, ağaç sahibi G2
        # G2'nin kilitsiz dosyaları açık kalır
        self.assertIsNone(self.karar(os.path.join(yol2, "src", "y.py"), "is", gorev=g2)[0])
        self.assertIsNone(self.karar(os.path.join(yol2, "tests", "test_y.py"), "is", gorev=g2)[0])
        # G1 kendi ağacını da açınca G2 ağacındaki karşılık yine kapalı
        self.agac()
        self.assertEqual(self.karar(hedef, "is", gorev=g2)[0], "deny")
        self.assertEqual(self.karar(hedef, "is", ana=True)[0], "deny")

    # ---------------------------------------------------------- (g) birleştirme kilit kapısı
    def goster(self, gid):
        r = self.cli("kart", "goster", gid)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def commit(self, yol, mesaj="c"):
        git(yol, "add", "-A")
        git(yol, "commit", "-q", "-m", mesaj)

    def test_g_baska_kartin_kilitli_testini_degistiren_dal_birlesmez(self):
        self.kirmizi()  # G1 tests/test_x.py'yi kilitler
        r = self.cli("kart", "yeni", "--baslik", "k2", "--basamak", "T2", "--kabul", "ok",
                     "--yazma", "tests/**", "--yazma", "src/**")
        g2 = r.stdout.strip()
        yol2 = self.cli("kart", "agac", g2).stdout.strip()
        # hook dışı yol: doğrudan dosya sistemi + commit (git checkout benzeri dolaylı yazım)
        yaz(os.path.join(yol2, "tests", "test_x.py"), "import unittest\n")
        self.commit(yol2, "kilitli testi değiştir")
        isci = dict(ajan_id="w2", ajan_tipi="orkestra:isci-t2")
        self.assertEqual(self.cli("kart", "durum", g2, "is-bitti", "--ozet", "b", **isci).returncode, 0)
        r = self.cli("kart", "denetim", g2, "--karar", "onay", "--gerekce", "t", ajan_id="d1", ajan_tipi="orkestra:denetci")
        self.assertEqual(r.returncode, 0, r.stderr)
        bas = git(self.proje, "rev-parse", "HEAD").strip()
        for komut in (("kart", "teslim", g2), ("kart", "birlestir", g2)):
            r = self.cli(*komut)
            self.assertEqual(r.returncode, 4, f"{komut}: {r.stdout}{r.stderr}")
            self.assertIn("kilitli test", r.stderr)
            self.assertIn(self.g, r.stderr)  # kilit sahibi
            self.assertIn("tests/test_x.py", r.stderr)
            self.assertEqual(git(self.proje, "rev-parse", "HEAD").strip(), bas, komut)  # main değişmedi
            with open(os.path.join(self.proje, "tests", "test_x.py"), encoding="utf-8") as f:
                self.assertEqual(f.read(), KIRMIZI_TEST)
            k = self.goster(g2)
            self.assertEqual(k["durum"], "beklemede", komut)
            self.assertTrue((k.get("calisma_agaci") or {}).get("yol"), komut)  # worktree korunur
            self.assertTrue(os.path.isdir(yol2), komut)
            self.assertTrue(git(self.proje, "branch", "--list", f"kart/{g2}").strip(), komut)
        # kilitli test eski hâline döner, kilitsiz dosya değişir → birleştirme geçer
        yaz(os.path.join(yol2, "tests", "test_x.py"), KIRMIZI_TEST)
        yaz(os.path.join(yol2, "src", "y.py"), "Y = 1\n")
        self.commit(yol2, "geri al + kilitsiz dosya")
        r = self.cli("kart", "birlestir", g2)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(git(self.proje, "rev-parse", "HEAD").strip(), bas)
        self.assertTrue(os.path.isfile(os.path.join(self.proje, "src", "y.py")))
        with open(os.path.join(self.proje, "tests", "test_x.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), KIRMIZI_TEST)

    def test_g_kendi_kilitli_testi_dalda_degisirse_birlesmez(self):
        yol = self.agac()
        test_y = "import unittest\nclass Y(unittest.TestCase):\n    def test_y(self):\n        pass\n"
        yaz(os.path.join(yol, "tests", "test_y.py"), test_y)
        self.kirmizi()  # ağaçta: test_x.py ve test_y.py kilitlenir
        self.assertIn("tests/test_y.py", self.goster(self.g)["test_kilidi"]["dosyalar"])
        yaz(os.path.join(yol, "src", "x.py"), "def f():\n    return 2\n")
        self.commit(yol, "testler + düzeltme")
        yaz(os.path.join(yol, "tests", "test_y.py"), "import unittest\n")  # hook dışı: kilit bozulur
        self.commit(yol, "kilitli testi boz")
        bas = git(self.proje, "rev-parse", "HEAD").strip()
        r = self.cli("kart", "birlestir", self.g)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("kilitli test", r.stderr)
        self.assertIn("tests/test_y.py", r.stderr)
        self.assertIn(self.g, r.stderr)
        self.assertEqual(git(self.proje, "rev-parse", "HEAD").strip(), bas)
        self.assertTrue(os.path.isdir(yol))
        # dalda kilitteki içerik geri gelince (yeni kilitli test kilitteki hâliyle) birleştirme geçer
        yaz(os.path.join(yol, "tests", "test_y.py"), test_y)
        self.commit(yol, "geri al")
        r = self.cli("kart", "birlestir", self.g)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.proje, "tests", "test_y.py")))

    def test_g_satir_sonu_donusumu_kilidi_bozmaz(self):
        git(self.proje, "config", "core.autocrlf", "true")  # ağaç aynı yapılandırmayı paylaşır
        yol = self.agac()
        with open(os.path.join(yol, "tests", "test_crlf.py"), "wb") as f:
            f.write(b"import unittest\r\nclass C(unittest.TestCase):\r\n    def test_c(self):\r\n        pass\r\n")
        with open(os.path.join(yol, "tests", "test_lf.py"), "wb") as f:
            f.write(b"import unittest\nclass L(unittest.TestCase):\n    def test_l(self):\n        pass\n")
        self.kirmizi()
        self.commit(yol, "crlf ve lf testler")
        r = self.cli("kart", "birlestir", self.g)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# ---------------------------------------------------------- (f) depo projenin alt klasörü
class AgacProjeKokunuKapsamiyor(unittest.TestCase):
    """Depo projenin alt klasörüyken kart ağacı proje kökünü kapsamaz: test_komutu proje kökünde koşar, ağaçtaki kodu
    sınayamaz. Kod kartına ağaç açılmaz; eski (önceden açılmış) ağaçlı kod kartında test-kos ve onay kapısı açık hata verir."""

    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_agk_"))
        self.proje = os.path.join(self.taban, "proje")  # git deposu değil
        self.depo = os.path.join(self.proje, "depo")
        os.makedirs(self.depo)
        git(self.depo, "init", "-q", "-b", "main")
        git(self.depo, "config", "user.name", "Test")
        git(self.depo, "config", "user.email", "test@example.invalid")
        git(self.depo, "config", "core.autocrlf", "false")
        yaz(os.path.join(self.depo, ".gitignore"), "__pycache__/\n")
        yaz(os.path.join(self.depo, "src", "x.py"), "def f():\n    return 1\n")
        yaz(os.path.join(self.depo, "tests", "test_x.py"), KIRMIZI_TEST)
        git(self.depo, "add", ".")
        git(self.depo, "commit", "-q", "-m", "ilk")
        r = kos([CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli("kart", "yeni", "--baslik", "kod", "--basamak", "T2", "--kabul", "ok", "--sinif", "kod", "--tdd",
                     "--test-komutu", f'"{sys.executable}" -m unittest discover -s depo/tests',
                     "--test-alani", "depo/tests/**", "--yazma", "depo/src/**", "--yazma", "depo/tests/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.g = r.stdout.strip()

    def tearDown(self):
        for satir in git(self.depo, "worktree", "list", "--porcelain").splitlines():
            if satir.startswith("worktree ") and os.path.realpath(satir[9:]) != self.depo:
                subprocess.run(["git", "-C", self.depo, "worktree", "remove", "--force", satir[9:]], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)

    def cli(self, *args, ajan_id="ana", ajan_tipi="ana"):
        return kos([CLI] + list(args) + ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi], self.proje)

    def kart(self, gid=None):
        with open(os.path.join(self.proje, ".claude", "orkestra", "gorevler", f"{gid or self.g}.json"),
                  encoding="utf-8") as f:
            return json.load(f)

    def test_f1_kod_kartina_proje_kokunu_kapsamayan_agac_acilmaz(self):
        r = self.cli("kart", "agac", self.g)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("proje kökünü kapsamıyor", r.stderr)
        self.assertFalse(os.path.exists(f"{self.depo}-kart-{self.g}"))
        self.assertEqual(git(self.depo, "branch", "--list", f"kart/{self.g}").strip(), "")
        self.assertNotIn("calisma_agaci", self.kart())
        # kod kartı olmayan kart aynı düzende ağaç açabilir (testi yok, kapı yok)
        r = self.cli("kart", "yeni", "--baslik", "belge", "--basamak", "T2", "--kabul", "ok", "--yazma", "depo/src/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        g2 = r.stdout.strip()
        r = self.cli("kart", "agac", g2)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_f2_eski_agacli_kod_kartinda_test_kos_ve_onay_acik_hata(self):
        isci = dict(ajan_id="tw", ajan_tipi="orkestra:isci-t2")
        r = self.cli("kart", "test-kos", self.g, "--asama", "kirmizi", **isci)  # paylaşılan ağaçta, ağaç yokken
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.cli("kart", "durum", self.g, "is-bitti", "--ozet", "bitti", ajan_id="tw", ajan_tipi="orkestra:arsivci")  # kapısız: yeşil aşağıda elle
        self.assertEqual(r.returncode, 0, r.stderr)
        yaz(os.path.join(self.depo, "src", "x.py"), "def f():\n    return 2\n")
        r = self.cli("kart", "test-kos", self.g, "--asama", "yesil", **isci)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # Bu sürümden önce açılmış ağaç: depo projenin altında, ağaç proje kökünü kapsamıyor
        yol = f"{self.depo}-kart-{self.g}"
        git(self.depo, "worktree", "add", "-q", "-b", f"kart/{self.g}", yol, "HEAD")
        k = self.kart()
        k["calisma_agaci"] = {"depo": self.depo.replace("\\", "/"), "yol": yol.replace("\\", "/"),
                              "dal": f"kart/{self.g}", "taban": "HEAD"}
        yaz(os.path.join(self.proje, ".claude", "orkestra", "gorevler", f"{self.g}.json"),
            json.dumps(k, ensure_ascii=False, indent=2) + "\n")
        kosu_sayisi = len(k["test_kosulari"])
        r = self.cli("kart", "test-kos", self.g, "--asama", "yesil", **isci)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("proje kökünü kapsamıyor", r.stderr)
        self.assertNotIn("GEÇTİ", r.stdout)
        self.assertEqual(len(self.kart()["test_kosulari"]), kosu_sayisi)  # paylaşılan ağaçta koşu kaydedilmedi
        r = self.cli("kart", "denetim", self.g, "--karar", "onay", "--gerekce", "tamam",
                     ajan_id="d1", ajan_tipi="orkestra:denetci")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("proje kökünü kapsamıyor", r.stderr)
        self.assertEqual(self.kart()["denetimler"], [])


if __name__ == "__main__":
    unittest.main()
