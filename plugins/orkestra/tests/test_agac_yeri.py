"""Kart çalışma ağacının yeri (G-060): `<depo>/.claude/worktrees/kart-<id>`, `ORKESTRA_AGAC_KOKU`, iptalde temizlik,
`kart agac-temizle` ve eski düzen (`<depo>-kart-<id>`) uyumu.

Her test tempfile altında kendi git deposunu ve orkestra durum klasörünü kurar; gerçek depoya dokunmaz.
`py -3.13 -m pytest plugins/orkestra/tests/test_agac_yeri.py`
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
OTURUM = "agac-yeri-oturum"
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402


def kos(args, cwd, stdin=None, env_ek=None):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("ORKESTRA_AGAC_KOKU", None)
    env.update(env_ek or {})
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


def oku(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read()


def n(yol):
    """Karşılaştırma biçimi: '/' ayracı, küçük harf, çözülmüş gerçek yol."""
    return os.path.normcase(os.path.realpath(yol)).replace("\\", "/").rstrip("/")


def agaclar(depo):
    """`git worktree list --porcelain` ile kayıtlı ağaç yolları (normalize), ana ağaç dahil."""
    return [n(s[9:]) for s in git(depo, "worktree", "list", "--porcelain").splitlines() if s.startswith("worktree ")]


class Temel(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_ayr_"))
        self.proje = os.path.join(self.taban, "depo")
        os.makedirs(self.proje)
        git(self.proje, "init", "-q", "-b", "main")
        git(self.proje, "config", "user.name", "Test")
        git(self.proje, "config", "user.email", "test@example.invalid")
        git(self.proje, "config", "core.autocrlf", "false")
        # .claude/ tümden yok sayılmaz: yalnız orkestra durum klasörü; böylece .claude/worktrees ayrıca ele alınmalı
        yaz(os.path.join(self.proje, ".gitignore"), ".claude/orkestra/\n__pycache__/\n")
        yaz(os.path.join(self.proje, "a.txt"), "bir\n")
        yaz(os.path.join(self.proje, "src", "x.py"), "x = 1\n")
        yaz(os.path.join(self.proje, "docs", "d.md"), "# d\n")
        git(self.proje, "add", ".")
        git(self.proje, "commit", "-q", "-m", "ilk")
        self.eski_env = os.environ.get("ORKESTRA_AGAC_KOKU")
        os.environ.pop("ORKESTRA_AGAC_KOKU", None)

    def tearDown(self):
        if self.eski_env is None:
            os.environ.pop("ORKESTRA_AGAC_KOKU", None)
        else:
            os.environ["ORKESTRA_AGAC_KOKU"] = self.eski_env
        try:
            for satir in git(self.proje, "worktree", "list", "--porcelain").splitlines():
                if satir.startswith("worktree ") and n(satir[9:]) != n(self.proje):
                    subprocess.run(["git", "-C", self.proje, "worktree", "remove", "--force", satir[9:]],
                                   capture_output=True)
        except AssertionError:
            pass
        shutil.rmtree(self.taban, ignore_errors=True)

    def depo(self):
        return self.proje.replace("\\", "/")


# ======================================================================= kütüphane düzeyi
class AgacYeriKutuphane(Temel):
    def kart(self, gid="G-001", desen="src/**"):
        return {"id": gid, "yazma_alani": [desen]}

    def test_varsayilan_yol_depo_ici_gizli_klasor_ve_kart_dali(self):  # kriter 1
        ca, yeni = L.kart_agaci_ac(self.proje, self.kart(), "HEAD")
        beklenen = os.path.join(self.proje, ".claude", "worktrees", "kart-G-001")
        self.assertEqual(n(ca["yol"]), n(beklenen))
        self.assertEqual(ca["dal"], "kart/G-001")
        self.assertTrue(os.path.isfile(os.path.join(beklenen, "src", "x.py")))
        self.assertIn("kart/G-001", git(self.proje, "branch", "--list", "kart/G-001"))
        self.assertIn(n(beklenen), agaclar(self.proje))
        # deponun üst klasöründe yeni klasör oluşmaz
        self.assertEqual(os.listdir(self.taban), ["depo"])
        # yazma alanı ağaca çevrilir
        self.assertEqual([n(y) for y in yeni], [n(beklenen) + "/src/**"])

    def test_agac_koku_ortam_degiskeni(self):  # kriter 2
        kok = os.path.join(self.taban, "kokler")
        os.environ["ORKESTRA_AGAC_KOKU"] = kok
        ca, _ = L.kart_agaci_ac(self.proje, self.kart(), "HEAD")
        beklenen = os.path.join(kok, "depo", "kart-G-001")
        self.assertEqual(n(ca["yol"]), n(beklenen))
        self.assertTrue(os.path.isfile(os.path.join(beklenen, "src", "x.py")))
        self.assertFalse(os.path.exists(os.path.join(self.proje, ".claude", "worktrees")))
        self.assertIn(n(beklenen), agaclar(self.proje))
        self.assertEqual(os.listdir(self.taban).count("depo-kart-G-001"), 0)

    def test_agac_koku_depo_disinda_exclude_degismez(self):  # kriter 2/3 uç
        os.environ["ORKESTRA_AGAC_KOKU"] = os.path.join(self.taban, "kokler")
        L.kart_agaci_ac(self.proje, self.kart(), "HEAD")
        ex = os.path.join(self.proje, ".git", "info", "exclude")
        self.assertNotIn(".claude/worktrees", oku(ex) if os.path.exists(ex) else "")

    def test_exclude_bir_kez_eklenir_gitignore_degismez_status_temiz(self):  # kriter 3
        gi_once = oku(os.path.join(self.proje, ".gitignore"))
        L.kart_agaci_ac(self.proje, self.kart("G-001"), "HEAD")
        L.kart_agaci_ac(self.proje, self.kart("G-002", "docs/**"), "HEAD")
        ex = oku(os.path.join(self.proje, ".git", "info", "exclude"))
        satirlar = [s.strip() for s in ex.splitlines() if s.strip().rstrip("/") == ".claude/worktrees"]
        self.assertEqual(len(satirlar), 1, ex)
        durum = git(self.proje, "status", "--porcelain", "--untracked-files=all")
        self.assertNotIn(".claude/worktrees", durum)
        self.assertEqual(durum.strip(), "")
        self.assertEqual(oku(os.path.join(self.proje, ".gitignore")), gi_once)

    def test_zaten_yok_sayilan_klasor_icin_exclude_eklenmez(self):  # kriter 3 uç
        yaz(os.path.join(self.proje, ".gitignore"), ".claude/\n")
        git(self.proje, "add", ".gitignore")
        git(self.proje, "commit", "-q", "-m", "gi")
        L.kart_agaci_ac(self.proje, self.kart(), "HEAD")
        ex = os.path.join(self.proje, ".git", "info", "exclude")
        self.assertNotIn(".claude/worktrees", oku(ex) if os.path.exists(ex) else "")
        self.assertEqual(git(self.proje, "status", "--porcelain", "--untracked-files=all").strip(), "")

    def test_git_koku_ve_agac_esdegeri_agac_icindeki_yol(self):  # kriter 4
        k = self.kart()
        ca, _ = L.kart_agaci_ac(self.proje, k, "HEAD")
        k["calisma_agaci"] = ca
        yol = ca["yol"]
        dosya = os.path.join(yol, "src", "x.py")
        self.assertEqual(n(L.git_koku(dosya)), n(yol))
        self.assertEqual(n(L.git_koku(os.path.join(yol, "olmayan", "alt", "y.py"))), n(yol))  # var olmayan kuyruk
        self.assertEqual(n(L.git_koku(os.path.join(self.proje, "src", "x.py"))), n(self.proje))
        self.assertEqual(n(L.agac_esdegeri(k, dosya)), n(os.path.join(self.proje, "src", "x.py")))
        self.assertTrue(L.agac_esdegeri(k, dosya).startswith(self.proje.replace("\\", "/")[:3]))
        # ana ağaçtaki yol ağaç içinde değil: eşdeğer yok
        self.assertIsNone(L.agac_esdegeri(k, os.path.join(self.proje, "src", "x.py")))
        # ağaç depo içinde olsa da onun altındaki yol "ana ağaç" sayılmaz
        self.assertNotEqual(n(L.git_koku(dosya)), n(self.proje))

    def test_ayni_depoda_iki_kart_ayri_agac(self):  # kriter 1 uç
        a, _ = L.kart_agaci_ac(self.proje, self.kart("G-001"), "HEAD")
        b, _ = L.kart_agaci_ac(self.proje, self.kart("G-002", "docs/**"), "HEAD")
        self.assertNotEqual(n(a["yol"]), n(b["yol"]))
        self.assertTrue(os.path.isdir(a["yol"]) and os.path.isdir(b["yol"]))

    def test_ayni_kart_icin_ikinci_acilis_reddedilir(self):  # hata yolu
        k = self.kart()
        ca, _ = L.kart_agaci_ac(self.proje, k, "HEAD")
        k["calisma_agaci"] = ca
        with self.assertRaises(ValueError):
            L.kart_agaci_ac(self.proje, k, "HEAD")


# ======================================================================= CLI düzeyi
class AgacYeriCli(Temel):
    def setUp(self):
        super().setUp()
        r = kos([CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sd = os.path.join(self.proje, ".claude", "orkestra")

    def cli(self, *args, ajan_id="ana", ajan_tipi="ana", env_ek=None):
        return kos([CLI] + list(args) + ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi], self.proje, env_ek=env_ek)

    def kart(self, desen="src/**"):
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2", "--kabul", "yapıldı", "--sinif", "belge", "--yazma", desen)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def agac(self, gid, env_ek=None):
        r = self.cli("kart", "agac", gid, env_ek=env_ek)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def goster(self, gid):
        return json.loads(self.cli("kart", "goster", gid).stdout)

    def kart_dosyasi(self, gid):
        return os.path.join(self.sd, "gorevler", gid + ".json")

    def durum_yaz(self, gid, durum):
        """Kartı doğrudan teslim/iptal yapar (yalnız test kurulumu)."""
        yol = self.kart_dosyasi(gid)
        k = json.loads(oku(yol))
        k["durum"] = durum
        yaz(yol, json.dumps(k, ensure_ascii=False, indent=2) + "\n")

    def dal_var(self, dal):
        return bool(git(self.proje, "branch", "--list", dal).strip())

    def cikti(self, r):
        return (r.stdout + r.stderr).replace("\\", "/")

    def temizle(self, *ek, env_ek=None):
        return self.cli("kart", "agac-temizle", *ek, env_ek=env_ek)

    def eski_duzen_ac(self, gid):
        """Eski düzende (`<depo>-kart-<id>`) ağaç açıp kart dosyasına elle yazar."""
        yol = self.proje.replace("\\", "/") + f"-kart-{gid}"
        dal = f"kart/{gid}"
        taban = git(self.proje, "rev-parse", "HEAD").strip()
        git(self.proje, "worktree", "add", "-q", "-b", dal, yol, taban)
        kd = self.kart_dosyasi(gid)
        k = json.loads(oku(kd))
        k["calisma_agaci"] = {"depo": self.proje.replace("\\", "/"), "yol": yol, "dal": dal, "taban": taban}
        yaz(kd, json.dumps(k, ensure_ascii=False, indent=2) + "\n")
        return yol

    # ------------------------------------------------------------ kriter 1/2 CLI
    def test_cli_agac_yeni_yola_acar_ve_karta_yazar(self):
        g = self.kart()
        yol = self.agac(g)
        self.assertEqual(n(yol), n(os.path.join(self.proje, ".claude", "worktrees", f"kart-{g}")))
        ca = self.goster(g)["calisma_agaci"]
        self.assertEqual((n(ca["yol"]), ca["dal"]), (n(yol), f"kart/{g}"))
        self.assertEqual(os.listdir(self.taban), ["depo"])

    def test_cli_agac_koku_ortami(self):
        g = self.kart()
        kok = os.path.join(self.taban, "kokler")
        yol = self.agac(g, env_ek={"ORKESTRA_AGAC_KOKU": kok})
        self.assertEqual(n(yol), n(os.path.join(kok, "depo", f"kart-{g}")))
        self.assertTrue(os.path.isdir(yol))

    # ------------------------------------------------------------ kriter 2/4: yazma alanı kontrolü ağaç içinde
    def test_hook_agac_depo_icinde_olsa_da_ana_agac_sayilmaz(self):
        g = self.kart()
        yol = self.agac(g)
        aid = f"w-{g}"
        yaz(os.path.join(self.sd, "oturumlar", f"ajan_{aid}.json"),
            json.dumps({"gorev": g, "surec": "is", "ajan": "orkestra:isci-t2"}))

        def karar(dosya):
            girdi = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": "PreToolUse", "tool_name": "Write",
                     "tool_input": {"file_path": dosya, "content": "x"}, "agent_id": aid,
                     "agent_type": "orkestra:isci-t2"}
            r = kos([HOOK, "PreToolUse"], self.proje, stdin=json.dumps(girdi))
            self.assertEqual(r.returncode, 0, r.stderr)
            return ((json.loads(r.stdout) if r.stdout.strip() else {}).get("hookSpecificOutput") or {}).get(
                "permissionDecision")

        self.assertIsNone(karar(os.path.join(yol, "src", "y.py")))                # kendi ağacı, alan içi
        self.assertEqual(karar(os.path.join(yol, "docs", "z.md")), "deny")        # kendi ağacı, alan dışı
        self.assertEqual(karar(os.path.join(self.proje, "src", "y.py")), "deny")  # paylaşılan ağaç

    # ------------------------------------------------------------ kriter 5: iptal
    def test_iptal_temiz_agaci_kaldirir_birlesmis_dali_siler(self):
        g = self.kart()
        yol = self.agac(g)
        r = self.cli("kart", "durum", g, "iptal")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(yol))
        self.assertNotIn(n(yol), agaclar(self.proje))
        self.assertFalse(self.dal_var(f"kart/{g}"))  # tabanla aynı noktada: birleşmiş sayılır
        self.assertEqual(self.goster(g)["durum"], "iptal")

    def test_iptal_birlesmemis_dal_silinmez_agac_kalkar(self):
        g = self.kart()
        yol = self.agac(g)
        yaz(os.path.join(yol, "src", "yeni.py"), "y = 2\n")
        git(yol, "add", "src/yeni.py")
        git(yol, "commit", "-q", "-m", "birleşmemiş iş")
        r = self.cli("kart", "durum", g, "iptal")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(yol))
        self.assertTrue(self.dal_var(f"kart/{g}"))  # git branch -d reddeder: iş kaybolmaz
        self.assertEqual(self.goster(g)["durum"], "iptal")

    def test_iptal_kirli_agacta_gecer_agac_ve_kayit_kalir_uyari_yazar(self):
        g = self.kart()
        yol = self.agac(g)
        yaz(os.path.join(yol, "src", "kirli.py"), "k = 1\n")
        r = self.cli("kart", "durum", g, "iptal")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("uyar", self.cikti(r).lower())
        self.assertTrue(os.path.isfile(os.path.join(yol, "src", "kirli.py")))  # force yok: dosya kaybolmaz
        self.assertIn(n(yol), agaclar(self.proje))
        k = self.goster(g)
        self.assertEqual(k["durum"], "iptal")
        self.assertEqual(n(k["calisma_agaci"]["yol"]), n(yol))
        self.assertTrue(self.dal_var(f"kart/{g}"))

    def test_iptal_agacsiz_kart_sorunsuz(self):
        g = self.kart()
        r = self.cli("kart", "durum", g, "iptal")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.goster(g)["durum"], "iptal")

    # ------------------------------------------------------------ kriter 6: agac-temizle
    def kurulum_karisik(self):
        """A açık, B teslim, C iptal, D kartsız, F kirli+teslim, E kalıp dışı. Yolları döner."""
        y = {}
        for ad in "ABCDF":
            g = self.kart(f"docs/{ad}/**")
            y[ad] = (g, self.agac(g))
        self.durum_yaz(y["B"][0], "teslim")
        self.durum_yaz(y["C"][0], "iptal")
        os.remove(self.kart_dosyasi(y["D"][0]))
        self.durum_yaz(y["F"][0], "teslim")
        yaz(os.path.join(y["F"][1], "kirli.txt"), "k\n")
        dogrula = os.path.join(self.taban, "depo-dogrula")
        git(self.proje, "worktree", "add", "-q", "--detach", dogrula, "HEAD")
        y["E"] = ("-", dogrula)
        return y

    def test_agac_temizle_kuru_kosu_hicbir_sey_silmez(self):
        y = self.kurulum_karisik()
        once = agaclar(self.proje)
        dallar = git(self.proje, "branch", "--list")
        r = self.temizle()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(agaclar(self.proje), once)
        self.assertEqual(git(self.proje, "branch", "--list"), dallar)
        for ad in "ABCDF":
            self.assertTrue(os.path.isdir(y[ad][1]), ad)
        c = self.cikti(r)
        for ad in "BCD":  # adaylar yol olarak çıktıda geçer
            self.assertIn(f"kart-{y[ad][0]}", c, ad)
        self.assertNotIn(f"kart-{y['A'][0]}", c)  # açık kart aday değildir
        self.assertIn("kalıp dışı", c.lower())
        self.assertIn("depo-dogrula", c)

    def test_agac_temizle_uygula_yalniz_biten_ve_kartsiz_agaclari_kaldirir(self):
        y = self.kurulum_karisik()
        r = self.temizle("--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        kalan = agaclar(self.proje)
        for ad in "BCD":
            self.assertFalse(os.path.exists(y[ad][1]), f"{ad} kaldırılmalıydı")
            self.assertNotIn(n(y[ad][1]), kalan, ad)
        self.assertTrue(os.path.isdir(y["A"][1]))                  # açık kart
        self.assertIn(n(y["A"][1]), kalan)
        self.assertTrue(os.path.isdir(y["E"][1]))                  # kalıp dışı
        self.assertIn(n(y["E"][1]), kalan)
        self.assertTrue(os.path.isfile(os.path.join(y["F"][1], "kirli.txt")))  # kirli atlanır
        self.assertIn(n(y["F"][1]), kalan)
        self.assertIn("kart-" + y["F"][0], self.cikti(r))          # atlandığı söylenir
        # açık kartın dalı korunur
        self.assertTrue(self.dal_var(f"kart/{y['A'][0]}"))

    def test_agac_temizle_uygula_bos_durumda_hata_vermez(self):
        r = self.temizle("--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.temizle()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(agaclar(self.proje), [n(self.proje)])

    def test_agac_temizle_uygula_klasoru_elle_silinmis_kaydi_prune_eder(self):
        g = self.kart()
        yol = self.agac(g)
        self.durum_yaz(g, "teslim")
        shutil.rmtree(yol)
        r = self.temizle("--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(n(yol), agaclar(self.proje))

    def test_agac_temizle_agac_koku_duzenini_tanir(self):
        kok = os.path.join(self.taban, "kokler")
        env = {"ORKESTRA_AGAC_KOKU": kok}
        g1, g2 = self.kart("docs/**"), self.kart("src/**")
        y1, y2 = self.agac(g1, env_ek=env), self.agac(g2, env_ek=env)
        self.durum_yaz(g1, "teslim")
        r = self.temizle("--uygula", env_ek=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(y1))
        self.assertTrue(os.path.isdir(y2))  # açık kart

    # ------------------------------------------------------------ kriter 7: eski düzen
    def test_eski_duzen_birlestirme_calisir(self):
        g = self.kart()
        yol = self.eski_duzen_ac(g)
        yaz(os.path.join(yol, "src", "yeni.py"), "y = 2\n")
        git(yol, "add", "src/yeni.py")
        git(yol, "commit", "-q", "-m", "kart işi")
        r = self.cli("kart", "birlestir", g)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(oku(os.path.join(self.proje, "src", "yeni.py")), "y = 2\n")
        self.assertFalse(os.path.exists(yol))
        self.assertFalse(self.dal_var(f"kart/{g}"))
        self.assertNotIn("calisma_agaci", self.goster(g))

    def test_eski_duzen_agac_temizle_taniyip_yalniz_biteni_kaldirir(self):
        g1, g2 = self.kart("docs/**"), self.kart("src/**")
        y1, y2 = self.eski_duzen_ac(g1), self.eski_duzen_ac(g2)
        self.durum_yaz(g1, "teslim")
        kuru = self.temizle()
        self.assertEqual(kuru.returncode, 0, kuru.stdout + kuru.stderr)
        self.assertTrue(os.path.isdir(y1) and os.path.isdir(y2))
        self.assertIn(f"depo-kart-{g1}", self.cikti(kuru))
        self.assertNotIn(f"depo-kart-{g2}", self.cikti(kuru))
        r = self.temizle("--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(y1))
        self.assertTrue(os.path.isdir(y2))
        self.assertIn(n(y2), agaclar(self.proje))

    # ------------------------------------------------------------ kriter 5/6 (hedef 5): kayıtlı yol taşınmaz
    def test_kayitli_yol_agac_koku_degisince_de_korunur(self):
        g = self.kart()
        yol = self.agac(g)
        r = self.cli("kart", "goster", g, env_ek={"ORKESTRA_AGAC_KOKU": os.path.join(self.taban, "baska")})
        self.assertEqual(n(json.loads(r.stdout)["calisma_agaci"]["yol"]), n(yol))
        yaz(os.path.join(yol, "src", "yeni.py"), "y = 2\n")
        git(yol, "add", "src/yeni.py")
        git(yol, "commit", "-q", "-m", "iş")
        r = self.cli("kart", "birlestir", g, env_ek={"ORKESTRA_AGAC_KOKU": os.path.join(self.taban, "baska")})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(yol))

# ======================================================================= G-060 ret: kartlar proje A'da, ağaçlar depo B'de
class AgacTemizleCaprazDepo(Temel):
    """Proje A (durum klasörü + kartlar) ile ağaçların açıldığı depo B (self.proje) ayrıdır."""
    A_GIT = False

    def setUp(self):
        super().setUp()
        self.A = os.path.join(self.taban, "projeA")
        os.makedirs(self.A)
        if self.A_GIT:
            git(self.A, "init", "-q", "-b", "main")
            git(self.A, "config", "user.name", "Test")
            git(self.A, "config", "user.email", "test@example.invalid")
            yaz(os.path.join(self.A, ".gitignore"), ".claude/orkestra/\n")
            yaz(os.path.join(self.A, "r.txt"), "r\n")
            git(self.A, "add", ".")
            git(self.A, "commit", "-q", "-m", "ilk")
        r = kos([CLI, "baslat"], self.A)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sd = os.path.join(self.A, ".claude", "orkestra")
        self.B = self.proje.replace("\\", "/")

    def cli(self, *args):
        return kos([CLI] + list(args) + ["--ajan-id", "ana", "--ajan-tipi", "ana"], self.A)

    def kart(self):
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2", "--kabul", "yapıldı", "--sinif", "belge", "--yazma", "src/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def kd(self, gid):
        return os.path.join(self.sd, "gorevler", gid + ".json")

    def kart_guncelle(self, gid, **alanlar):
        k = json.loads(oku(self.kd(gid)))
        k.update(alanlar)
        yaz(self.kd(gid), json.dumps(k, ensure_ascii=False, indent=2) + "\n")

    def agac_ac(self, gid, eski=False):
        yol = self.B + (f"-kart-{gid}" if eski else f"/.claude/worktrees/kart-{gid}")
        taban = git(self.proje, "rev-parse", "HEAD").strip()
        git(self.proje, "worktree", "add", "-q", "-b", f"kart/{gid}", yol, taban)
        return yol, {"depo": self.B, "yol": yol, "dal": f"kart/{gid}", "taban": taban}

    def cikti(self, r):
        return (r.stdout + r.stderr).replace("\\", "/")

    def kurulum(self):
        """Yeni düzen: acik, teslim (yalnız calisma_agaci_birlesik), iptal (calisma_agaci); eski düzen: eski_teslim.
        Kalıp dışı: depo-dogrula. Kartların hiçbirinde A'nın içinde ağaç yoktur."""
        y = {}
        for ad, eski in (("acik", False), ("teslim", False), ("iptal", False), ("eski_teslim", True)):
            g = self.kart()
            yol, ca = self.agac_ac(g, eski)
            y[ad] = (g, yol, ca)
        self.kart_guncelle(y["acik"][0], calisma_agaci=y["acik"][2])
        self.kart_guncelle(y["teslim"][0], durum="teslim", calisma_agaci_birlesik=y["teslim"][2])
        self.kart_guncelle(y["iptal"][0], durum="iptal", calisma_agaci=y["iptal"][2])
        self.kart_guncelle(y["eski_teslim"][0], durum="teslim", calisma_agaci_birlesik=y["eski_teslim"][2])
        dogrula = os.path.join(self.taban, "depo-dogrula")
        git(self.proje, "worktree", "add", "-q", "--detach", dogrula, "HEAD")
        y["kalip"] = ("-", dogrula, None)
        return y

    def test_kuru_kosu_B_adaylarini_listeler_hicbir_sey_silmez(self):
        y = self.kurulum()
        once = agaclar(self.proje)
        dallar = git(self.proje, "branch", "--list")
        r = self.cli("kart", "agac-temizle")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = self.cikti(r)
        for ad in ("teslim", "iptal", "eski_teslim"):
            self.assertIn(y[ad][1].replace("\\", "/"), c, ad)
        self.assertEqual(agaclar(self.proje), once)
        self.assertEqual(git(self.proje, "branch", "--list"), dallar)
        for ad in y:
            self.assertTrue(os.path.isdir(y[ad][1]), ad)
        self.assertNotIn("temizlenecek kart çalışma ağacı yok", c)
        self.assertNotIn("git deposu değil", c)

    def test_uygula_B_biteni_kaldirir_aciga_ve_kalip_disina_dokunmaz(self):
        y = self.kurulum()
        r = self.cli("kart", "agac-temizle", "--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = self.cikti(r)
        kalan = agaclar(self.proje)
        for ad in ("teslim", "iptal", "eski_teslim"):
            self.assertFalse(os.path.exists(y[ad][1]), f"{ad} kaldırılmalıydı")
            self.assertNotIn(n(y[ad][1]), kalan, ad)
        self.assertTrue(os.path.isdir(y["acik"][1]))
        self.assertIn(n(y["acik"][1]), kalan)
        self.assertNotIn(f"kart-{y['acik'][0]}", c)  # açık kart çıktıda geçmez
        self.assertTrue(os.path.isdir(y["kalip"][1]))
        self.assertIn(n(y["kalip"][1]), kalan)
        self.assertIn("kalıp dışı", c.lower())
        self.assertIn("depo-dogrula", c)
        self.assertTrue(git(self.proje, "branch", "--list", f"kart/{y['acik'][0]}").strip())

    def test_depo_yalniz_teslim_kartin_birlesik_alanindan_bilinse_de_taranir(self):
        g = self.kart()
        yol, ca = self.agac_ac(g)
        self.kart_guncelle(g, durum="teslim", calisma_agaci_birlesik=ca)
        k = json.loads(oku(self.kd(g)))
        self.assertNotIn("calisma_agaci", k)
        kuru = self.cli("kart", "agac-temizle")
        self.assertEqual(kuru.returncode, 0, kuru.stdout + kuru.stderr)
        self.assertIn(yol, self.cikti(kuru))
        self.assertTrue(os.path.isdir(yol))
        r = self.cli("kart", "agac-temizle", "--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(yol))
        self.assertNotIn(n(yol), agaclar(self.proje))

    def test_depo_yalniz_kaldirildi_alanindan_bilinse_de_taranir(self):
        g = self.kart()
        yol, ca = self.agac_ac(g)
        self.kart_guncelle(g, durum="iptal", calisma_agaci_kaldirildi=ca)
        r = self.cli("kart", "agac-temizle", "--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(yol))

    def test_hicbir_kartta_depo_bilgisi_yoksa_hata_vermez_ve_B_dokunulmaz(self):
        g = self.kart()
        yol, _ = self.agac_ac(g)
        self.kart_guncelle(g, durum="teslim")
        r = self.cli("kart", "agac-temizle", "--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isdir(yol))  # B hiçbir kartta anılmıyor: taranamaz, silinmez

    def test_kirli_biten_agac_B_de_atlanir(self):
        g = self.kart()
        yol, ca = self.agac_ac(g)
        self.kart_guncelle(g, durum="teslim", calisma_agaci_birlesik=ca)
        yaz(os.path.join(yol, "kirli.txt"), "k\n")
        r = self.cli("kart", "agac-temizle", "--uygula")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(yol, "kirli.txt")))
        self.assertIn("kirli", self.cikti(r))


class AgacTemizleCaprazDepoAGit(AgacTemizleCaprazDepo):
    """Aynı sınamalar; proje A da bir git deposu."""
    A_GIT = True


if __name__ == "__main__":
    unittest.main()
