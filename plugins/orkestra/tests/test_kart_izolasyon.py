"""Kart izolasyonu: yazma alanı çakışma kapısı, kart başına git çalışma ağacı, teslimde birleştirme, hook tanıması.

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
OTURUM = "izolasyon-oturum"
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)


def kos(args, cwd, stdin=None):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("ORKESTRA_AGAC_KOKU", None)
    return ic_kos.kos(args, cwd=cwd, env=env, input=stdin)


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)


def oku(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read()


class KartIzolasyonu(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_izo_"))
        self.proje = os.path.join(self.taban, "depo")
        os.makedirs(self.proje)
        git(self.proje, "init", "-q", "-b", "main")
        git(self.proje, "config", "user.name", "Test")
        git(self.proje, "config", "user.email", "test@example.invalid")
        git(self.proje, "config", "core.autocrlf", "false")
        yaz(os.path.join(self.proje, ".gitignore"), ".claude/\n")
        yaz(os.path.join(self.proje, "a.txt"), "bir\n")
        yaz(os.path.join(self.proje, "src", "x.py"), "x = 1\n")
        yaz(os.path.join(self.proje, "docs", "d.md"), "# d\n")
        git(self.proje, "add", ".")
        git(self.proje, "commit", "-q", "-m", "ilk")
        r = kos([CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sd = os.path.join(self.proje, ".claude", "orkestra")

    def tearDown(self):
        for satir in git(self.proje, "worktree", "list", "--porcelain").splitlines():
            if satir.startswith("worktree ") and os.path.realpath(satir[9:]) != self.proje:
                subprocess.run(["git", "-C", self.proje, "worktree", "remove", "--force", satir[9:]], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)

    # ---------------------------------------------------------- yardımcılar
    def cli(self, *args, ajan_id="ana", ajan_tipi="ana"):
        return kos([CLI] + list(args) + ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi], self.proje)

    def kart(self, *yazma):
        a = ["kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2", "--kabul", "yapıldı", "--sinif", "belge"]
        for y in yazma:
            a += ["--yazma", y]
        r = self.cli(*a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), r

    def isleniyor(self, gid):
        return self.cli("kart", "durum", gid, "isleniyor", ajan_id="w-" + gid, ajan_tipi="orkestra:isci-t2")

    def goster(self, gid):
        return json.loads(self.cli("kart", "goster", gid).stdout)

    def agac(self, gid):
        r = self.cli("kart", "agac", gid)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def onayla(self, gid):
        self.assertEqual(self.cli("kart", "durum", gid, "is-bitti", "--ozet", "tamam", ajan_id="w1",
                                  ajan_tipi="orkestra:isci-t2").returncode, 0)
        r = self.cli("kart", "denetim", gid, "--karar", "onay", "--gerekce", "ok", ajan_id="d1", ajan_tipi="orkestra:denetci")
        self.assertEqual(r.returncode, 0, r.stderr)

    # ---------------------------------------------------------- 1. çakışma kapısı
    def test_kesisen_alan_ikinci_kart_reddedilir(self):
        g1, _ = self.kart("src/**")
        g2, uyari = self.kart("src/x.py")
        self.assertEqual(self.isleniyor(g1).returncode, 0)
        r = self.isleniyor(g2)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn(f"çakışma: {g1} (src/**)", r.stderr)
        self.assertNotEqual(self.goster(g2)["durum"], "isleniyor")
        g3, _ = self.kart("docs/**")
        self.assertEqual(self.isleniyor(g3).returncode, 0)  # kesişmeyen alan geçer

    def test_kart_yeni_cakismada_uyarir(self):
        g1, _ = self.kart("src/**")
        self.assertEqual(self.isleniyor(g1).returncode, 0)
        _, r = self.kart("src/*.py")
        self.assertIn("uyarı", r.stderr)
        self.assertIn(g1, r.stderr)

    def test_depo_koku_ve_yildiz_paylasilan_agacta_reddedilir(self):
        for desen in ("**", self.proje.replace("\\", "/"), self.proje.replace("\\", "/") + "/**"):
            g, _ = self.kart(desen)
            r = self.isleniyor(g)
            self.assertEqual(r.returncode, 5, desen)
            self.assertIn("kökünü", r.stderr)

    def test_depoyu_ust_klasorden_kapsayan_desenler_reddedilir(self):
        ust = self.taban.replace("\\", "/")
        depo = self.proje.replace("\\", "/")
        baska = os.path.join(self.taban, "baska_depo")  # yalnız önekin alt klasör taramasıyla bulunan kardeş depo
        os.makedirs(baska)
        git(baska, "init", "-q")
        # projeyi İÇERMEYEN üst klasör: depo yalnız alt klasör taramasıyla bulunur (eski kural bunları geçiriyordu)
        dis = os.path.join(self.taban, "dis")
        os.makedirs(os.path.join(dis, "kardes_depo"))
        git(os.path.join(dis, "kardes_depo"), "init", "-q")
        dis_u = dis.replace("\\", "/")
        # İzin listesinden sonra depo dışı joker de ret: 'ust/*.txt' fnmatch'te depo/a.txt'ye de uyar ('*' '/'ye uyar),
        # 'ust/bas*/src/**' ise kökü 'src' olan bir depoyu bütünüyle kapsayabilir (80e438e ikisini de geçiriyordu).
        for desen in (ust + "/**", depo + "*/**", ust + "/*", "*/**", ust + "/bas*/**", dis_u + "/**", dis_u + "/kar*/**",
                      dis_u + "/*", ust + "/bas*/src/**", ust + "/*.txt"):
            g, _ = self.kart(desen)
            r = self.isleniyor(g)
            self.assertEqual(r.returncode, 5, f"{desen}: {r.stdout}{r.stderr}")
            self.assertIn("kökünü", r.stderr, desen)
        self.assertTrue(L.desen_eslesir(self.proje, os.path.join(self.proje, "a.txt"), [ust + "/*.txt"]))
        for desen in ("src/*/**",):  # depo içinde, sabit öneki kökün altında olan geçer
            g, _ = self.kart(desen)
            r = self.isleniyor(g)
            self.assertEqual(r.returncode, 0, f"{desen}: {r.stderr}")
            self.cli("kart", "durum", g, "iptal")

    # izin listesi: sabit önek (ilk joker bileşenden önceki yol) bir git deposunun KESİN alt yolu olmalı
    def kapi(self, desen):
        g, _ = self.kart(desen)
        return g, self.isleniyor(g)

    def test_izin_listesi_depo_disi_joker_ve_klasor_reddedilir(self):
        ust = self.taban.replace("\\", "/")
        depo = self.proje.replace("\\", "/")
        torun = os.path.join(self.taban, "uu", "ara", "torun_depo")  # 'uu' torun deponun üst-üstü
        os.makedirs(torun)
        git(torun, "init", "-q")
        os.makedirs(os.path.join(self.taban, "dis_klasor"))
        # 80e438e: uzantılı desen yoklama yolunu ('.qq') kaçırıyor, torun depo aday sayılmıyordu
        for desen in (ust + "/**/*.py", ust + "/*/**/*.py", depo + "*/**/*.py", ust + "/uu/**", ust + "/dis_klasor"):
            g, r = self.kapi(desen)
            self.assertEqual(r.returncode, 5, f"{desen}: {r.stdout}{r.stderr}")
            self.assertIn("git deposunun içinde değil", r.stderr, desen)

    def test_izin_listesi_depo_koku_her_kalanla_reddedilir(self):
        depo = self.proje.replace("\\", "/")
        # fnmatch'te '*' '/'ye de uyar: kökteki '*.md' alt klasördeki dosyayı da kapsar, yani '**/*.md' ile aynıdır
        self.assertTrue(L.desen_eslesir(self.proje, os.path.join(self.proje, "docs", "d.md"), ["*.md"]))
        for desen in ("*.md", depo + "/*/x.py", depo + "/**/*.py"):  # sonuncuyu 80e438e de reddediyordu
            g, r = self.kapi(desen)
            self.assertEqual(r.returncode, 5, f"{desen}: {r.stdout}{r.stderr}")
            self.assertIn("deposunun kökünü kapsıyor", r.stderr, desen)

    def test_izin_listesi_git_disi_proje_ve_git_klasoru(self):
        t = self.taban  # git dışı klasör proje olursa kök proje klasörüdür
        self.assertFalse(L.kok_kapsiyor_mu(t, "docs/**"))
        self.assertFalse(L.kok_kapsiyor_mu(t, "notlar/*.md"))
        for desen in ("**", "*.md", "depo/**", "../**"):  # proje kökü, içteki deponun kökü, proje dışı
            self.assertTrue(L.kok_kapsiyor_mu(t, desen), desen)
        self.assertTrue(L.kok_kapsiyor_mu(self.proje, ".git/**"))  # git projesinde .git içi depo içi sayılmaz

    def test_izin_listesi_dar_desenler_kabul(self):
        ust = self.taban.replace("\\", "/")
        depo = self.proje.replace("\\", "/")
        yaz(os.path.join(self.taban, "notlar.md"), "n\n")
        # depo içi alt yol (var olmayan klasör dahil), depo dışında tek dosya literal yolu (var olan ya da yeni)
        for desen in (depo + "/src/**/*.py", depo + "/plugins/**", "docs/d.md", ust + "/notlar.md",
                      ust + "/yeni/rapor.md"):
            g, r = self.kapi(desen)
            self.assertEqual(r.returncode, 0, f"{desen}: {r.stderr}")
            self.cli("kart", "durum", g, "iptal")

    def test_ic_ice_depo_fiziksel_kesisimle_yakalanir(self):
        ic = os.path.join(self.proje, "vendor", "ara", "ic_depo")
        os.makedirs(ic)
        git(ic, "init", "-q")
        ic_u = ic.replace("\\", "/")
        # dış depoda iç depoyu kapsayan alan tek başına geçer (ana projede 'ACMECO/**' altında kod depoları var)
        g0, r = self.kapi("vendor/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        # iç depodaki kart, onu kapsayan dış kartla çakışır (80e438e 'farklı ağaç' diye atlıyordu)
        g1, r = self.kapi(ic_u + "/src/**")
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn(f"çakışma: {g0}", r.stderr)
        self.cli("kart", "durum", g0, "iptal")
        self.assertEqual(self.isleniyor(g1).returncode, 0)
        g2, r = self.kapi("vendor/**")  # ters sıra
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn(f"çakışma: {g1}", r.stderr)

    def test_farkli_calisma_agacindaki_kartlar_cakismaz(self):
        g1, _ = self.kart("src/**")
        self.assertEqual(self.isleniyor(g1).returncode, 0)
        g2, _ = self.kart("src/**")
        self.agac(g2)
        r = self.isleniyor(g2)
        self.assertEqual(r.returncode, 0, r.stderr)
        g3, _ = self.kart("**")  # tüm depo, ama kendi ağacında
        self.agac(g3)
        self.assertEqual(self.isleniyor(g3).returncode, 0)

    def test_desen_kesisimi_birim(self):
        p = self.proje
        self.assertTrue(L.desen_kesisir(p, "src/**", "src/x.py"))
        self.assertTrue(L.desen_kesisir(p, "README.md", "README.md"))
        self.assertTrue(L.desen_kesisir(p, "*.md", "README.md"))
        self.assertFalse(L.desen_kesisir(p, "src/**", "docs/**"))
        self.assertFalse(L.desen_kesisir(p, "src/a.py", "src/b.py"))
        self.assertFalse(L.desen_kesisir(p, "src/**", "src2/**"))  # bileşen bazında önek

    # ---------------------------------------------------------- 2. çalışma ağacı
    def test_agac_worktree_ve_dal_acar_kart_jsonuna_yazar(self):
        g, _ = self.kart("src/**")
        yol = self.agac(g)
        self.assertEqual(os.path.normcase(yol), os.path.normcase(self.proje.replace("\\", "/") + f"/.claude/worktrees/kart-{g}"))
        self.assertTrue(os.path.isfile(os.path.join(yol, "src", "x.py")))
        self.assertIn(f"kart/{g}", git(self.proje, "branch", "--list", f"kart/{g}"))
        k = self.goster(g)
        ca = k["calisma_agaci"]
        self.assertEqual((ca["yol"], ca["dal"]), (yol, f"kart/{g}"))
        self.assertEqual(ca["taban"], git(self.proje, "rev-parse", "HEAD").strip())
        self.assertEqual(k["yazma_alani"], [yol + "/src/**"])
        self.assertEqual(k["yazma_alani_ilk"], ["src/**"])
        self.assertEqual(k["calisma_agaci_satiri"], "Çalışma ağacı: " + yol)
        self.assertTrue(k["girdi"].startswith("Çalışma ağacı: " + yol))
        self.assertNotEqual(self.cli("kart", "agac", g).returncode, 0)  # ikinci kez açılmaz

    def test_birlestir_basarili_no_ff_ve_temizlik(self):
        g, _ = self.kart("src/**")
        yol = self.agac(g)
        yaz(os.path.join(yol, "src", "yeni.py"), "y = 2\n")
        git(yol, "add", "src/yeni.py")
        git(yol, "commit", "-q", "-m", "kart işi")
        r = self.cli("kart", "birlestir", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(oku(os.path.join(self.proje, "src", "yeni.py")), "y = 2\n")
        ebeveyn = git(self.proje, "rev-list", "--parents", "-n", "1", "HEAD").split()
        self.assertEqual(len(ebeveyn), 3)  # --no-ff: birleştirme commit'i
        self.assertFalse(os.path.exists(yol))
        self.assertEqual(git(self.proje, "branch", "--list", f"kart/{g}").strip(), "")
        k = self.goster(g)
        self.assertNotIn("calisma_agaci", k)
        self.assertEqual(k["yazma_alani"], ["src/**"])
        self.assertEqual(k["calisma_agaci_birlesik"]["commit"], ebeveyn[0])
        self.assertFalse(k["girdi"].startswith("Çalışma ağacı"))

    def test_birlestir_catismada_abort_ve_beklemede(self):
        g, _ = self.kart("a.txt")
        yol = self.agac(g)
        yaz(os.path.join(yol, "a.txt"), "kart\n")
        git(yol, "commit", "-q", "-am", "kart")
        yaz(os.path.join(self.proje, "a.txt"), "ana\n")
        git(self.proje, "commit", "-q", "-am", "ana")
        once = git(self.proje, "rev-parse", "HEAD").strip()
        r = self.cli("kart", "birlestir", g)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("a.txt", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.proje, ".git", "MERGE_HEAD")))
        self.assertEqual(git(self.proje, "rev-parse", "HEAD").strip(), once)
        self.assertEqual(oku(os.path.join(self.proje, "a.txt")), "ana\n")  # otomatik çözüm yok
        self.assertEqual(git(self.proje, "status", "--porcelain").strip(), "")
        k = self.goster(g)
        self.assertEqual(k["durum"], "beklemede")
        self.assertEqual(k["birlestirme_catismasi"], ["a.txt"])
        self.assertIn("a.txt", k["gecmis"][-1]["not"])
        self.assertTrue(os.path.isdir(yol))  # kart ağacı korunur

    def test_birlestir_ana_agacta_kirli_dosyada_reddeder(self):
        g, _ = self.kart("src/**")
        yol = self.agac(g)
        yaz(os.path.join(yol, "src", "x.py"), "x = 2\n")
        git(yol, "commit", "-q", "-am", "kart")
        yaz(os.path.join(self.proje, "src", "x.py"), "x = 99  # commitlenmemiş\n")
        r = self.cli("kart", "birlestir", g)
        self.assertEqual(r.returncode, 4)
        self.assertIn("ana ağaçta", r.stderr)
        self.assertEqual(oku(os.path.join(self.proje, "src", "x.py")), "x = 99  # commitlenmemiş\n")  # sessiz ezme yok
        self.assertIn(f"kart/{g}", git(self.proje, "branch", "--list", f"kart/{g}"))
        self.assertIn("calisma_agaci", self.goster(g))

    def test_birlestir_commitlenmemis_kart_dalinda_reddeder(self):
        g, _ = self.kart("src/**")
        yol = self.agac(g)
        yaz(os.path.join(yol, "src", "yarim.py"), "z = 3\n")
        r = self.cli("kart", "birlestir", g)
        self.assertEqual(r.returncode, 4)
        self.assertIn("kart dalında commitlenmemiş", r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(yol, "src", "yarim.py")))
        self.assertFalse(os.path.exists(os.path.join(self.proje, "src", "yarim.py")))

    def test_teslim_birlestirmeden_gecmez(self):
        g, _ = self.kart("a.txt")
        yol = self.agac(g)
        yaz(os.path.join(yol, "a.txt"), "kart\n")
        git(yol, "commit", "-q", "-am", "kart")
        yaz(os.path.join(self.proje, "a.txt"), "ana\n")
        git(self.proje, "commit", "-q", "-am", "ana")
        self.onayla(g)
        r = self.cli("kart", "teslim", g)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("teslim reddedildi", r.stderr)
        self.assertEqual(self.goster(g)["durum"], "beklemede")
        # birleşebilen kart teslimde birleştirilir
        g2, _ = self.kart("docs/**")
        yol2 = self.agac(g2)
        yaz(os.path.join(yol2, "docs", "e.md"), "# e\n")
        git(yol2, "add", "docs/e.md")
        git(yol2, "commit", "-q", "-m", "e")
        self.onayla(g2)
        r = self.cli("kart", "teslim", g2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.proje, "docs", "e.md")))
        self.assertEqual(self.goster(g2)["durum"], "teslim")
        self.assertFalse(os.path.exists(yol2))

    # ---------------------------------------------------------- 3. hook
    def test_hook_yazma_alani_calisma_agacini_tanir(self):
        g, _ = self.kart("src/**")
        yol = self.agac(g)
        tr = os.path.join(self.taban, "agent-w7.jsonl")
        yaz(tr, json.dumps({"type": "user", "message": {"role": "user", "content": f"#GOREV:{g} #SUREC:is\nYap."}}) + "\n")

        def karar(dosya, aid="w7", atip="orkestra:isci-t2"):
            girdi = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": "PreToolUse", "tool_name": "Write",
                     "tool_input": {"file_path": dosya, "content": "x"}}
            if aid:
                girdi.update(agent_id=aid, agent_type=atip, agent_transcript_path=tr)
            r = kos([HOOK, "PreToolUse"], self.proje, stdin=json.dumps(girdi))
            self.assertEqual(r.returncode, 0, r.stderr)
            o = json.loads(r.stdout) if r.stdout.strip() else {}
            return (o.get("hookSpecificOutput") or {}).get("permissionDecision")

        self.assertIsNone(karar(os.path.join(yol, "src", "y.py")))           # kendi ağacı, alan içi
        self.assertEqual(karar(os.path.join(yol, "docs", "z.md")), "deny")   # kendi ağacı, alan dışı
        self.assertEqual(karar(os.path.join(self.proje, "src", "y.py")), "deny")  # paylaşılan ağaç
        # ana ajan işleniyor kartın çalışma ağacındaki alanına yazmaz
        self.assertEqual(self.isleniyor(g).returncode, 0)
        self.assertEqual(karar(os.path.join(yol, "src", "y.py"), aid=None), "deny")
        self.assertIsNone(karar(os.path.join(self.taban, "scratch.txt"), aid=None))

    # ---------------------------------------------------------- 4. yazma_alaninda_mi: mutlak/göreli desen, proje dışı
    def isci_karari(self, gid, dosya):
        tr = os.path.join(self.taban, f"agent-{gid}.jsonl")
        yaz(tr, json.dumps({"type": "user", "message": {"role": "user", "content": f"#GOREV:{gid} #SUREC:is\nYap."}}) + "\n")
        girdi = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": "PreToolUse", "tool_name": "Write",
                 "tool_input": {"file_path": dosya, "content": "x"}, "agent_id": "w-" + gid,
                 "agent_type": "orkestra:isci-t2", "agent_transcript_path": tr}
        r = kos([HOOK, "PreToolUse"], self.proje, stdin=json.dumps(girdi))
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout) if r.stdout.strip() else {}
        return (o.get("hookSpecificOutput") or {}).get("permissionDecision")

    def test_a_proje_ici_mutlak_desen_dogru_karsilastirilir(self):
        mutlak = self.proje.replace("/", "\\") + "\\src\\**"  # ters bölü
        if os.name == "nt":
            mutlak = mutlak.upper()  # Windows: büyük/küçük harf farkı yok sayılır
        p = self.proje
        self.assertTrue(L.yazma_alaninda_mi(p, os.path.join(p, "src", "y.py"), [mutlak]))
        self.assertTrue(L.yazma_alaninda_mi(p, os.path.join(p, "src", "y.py"), ["src/**"]))
        self.assertFalse(L.yazma_alaninda_mi(p, os.path.join(p, "docs", "z.md"), [mutlak]))
        g, _ = self.kart(mutlak)
        self.assertIsNone(self.isci_karari(g, os.path.join(p, "src", "y.py")))       # önceden yanlışlıkla red
        self.assertEqual(self.isci_karari(g, os.path.join(p, "docs", "z.md")), "deny")

    def test_b_proje_disi_yol_desene_gore_denetlenir(self):
        dis = os.path.join(self.taban, "dis_depo")
        os.makedirs(os.path.join(dis, "src"))
        git(dis, "init", "-q")
        desen = dis.replace("\\", "/") + "/src/**"
        p = self.proje
        self.assertTrue(L.yazma_alaninda_mi(p, os.path.join(dis, "src", "a.py"), [desen]))
        self.assertFalse(L.yazma_alaninda_mi(p, os.path.join(dis, "b.txt"), [desen]))       # önceden serbestti
        self.assertFalse(L.yazma_alaninda_mi(p, os.path.join(dis, "b.txt"), ["src/**"]))
        g, _ = self.kart(desen)
        self.assertIsNone(self.isci_karari(g, os.path.join(dis, "src", "a.py")))
        self.assertEqual(self.isci_karari(g, os.path.join(dis, "b.txt")), "deny")
        # geçici klasördeki git dışı yol (scratchpad) serbest kalır
        self.assertIsNone(self.isci_karari(g, os.path.join(self.taban, "scratch", "not.txt")))


if __name__ == "__main__":
    unittest.main()
