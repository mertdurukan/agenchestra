"""P3 (I-026): cfg çözümleyici — öncelik, parmak izi, sır reddi, yazım."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cfg  # noqa: E402


class CfgTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ev = os.path.join(self.tmp.name, "ev")
        self.proje = os.path.join(self.tmp.name, "proje")
        os.makedirs(os.path.join(self.proje, ".claude", "orkestra"))
        env = {"ORKESTRA_HOME": self.ev}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for ad in cfg.ORTAM.values():
            os.environ.pop(ad, None)
        os.environ["ORKESTRA_HOME"] = self.ev
        eski_kesif = dict(cfg.KESIF)  # gerçek keşif işlevleri testleri etkilemesin
        cfg.KESIF.clear()
        self.addCleanup(lambda: (cfg.KESIF.clear(), cfg.KESIF.update(eski_kesif)))

    def proje_yaz(self, d):
        with open(cfg.proje_dosyasi(self.proje), "w", encoding="utf-8") as f:
            json.dump({"degerler": d}, f)

    def test_oncelik_sirasi(self):
        cfg.KESIF["python"] = lambda: "kesif-py"
        self.assertEqual(cfg.kaynakli_al("python"), ("kesif-py", "kesif"))
        cfg.makine_yaz({"python": "makine-py"})
        self.assertEqual(cfg.kaynakli_al("python"), ("makine-py", "makine"))
        self.proje_yaz({"python": "proje-py"})
        self.assertEqual(cfg.kaynakli_al("python", self.proje), ("proje-py", "proje"))
        os.environ["ORKESTRA_PYTHON"] = "ortam-py"
        self.assertEqual(cfg.kaynakli_al("python", self.proje), ("ortam-py", "ortam"))

    def test_varsayilan_ve_yok(self):
        self.assertEqual(cfg.kaynakli_al("bash", varsayilan="b"), ("b", "varsayilan"))
        self.assertEqual(cfg.kaynakli_al("bash"), (None, "yok"))

    def test_kesif_hatasi_dusurmez(self):
        def boz():
            raise RuntimeError("x")
        cfg.KESIF["bash"] = boz
        self.assertEqual(cfg.kaynakli_al("bash"), (None, "yok"))

    def test_parmak_izi_degisince_makine_eski(self):
        cfg.makine_yaz({"python": "p1"})
        self.assertTrue(cfg.makine_taze_mi())
        with mock.patch.object(cfg, "parmak_izi", return_value="baska-makine"):
            self.assertFalse(cfg.makine_taze_mi())
            self.assertEqual(cfg.kaynakli_al("python"), (None, "yok"))

    def test_yeni_makinede_eski_degerler_atilir(self):
        cfg.makine_yaz({"python": "p1", "bash": "b1"})
        with mock.patch.object(cfg, "parmak_izi", return_value="baska-makine"):
            cfg.makine_yaz({"python": "p2"})
            d = cfg.makine_oku()
        self.assertEqual(set(d["degerler"]), {"python"})
        self.assertEqual(d["parmak"], "baska-makine")

    def test_yazim_birlestirir(self):
        cfg.makine_yaz({"python": "p"})
        cfg.makine_yaz({"bash": "b"})
        self.assertEqual(set(cfg.makine_oku()["degerler"]), {"python", "bash"})

    def test_sir_reddedilir(self):
        for ad, deger in (("api_key", "x"), ("python", "sk-" + "a" * 24), ("langfuse_token", "y")):
            with self.assertRaises(ValueError, msg=ad):
                cfg.makine_yaz({ad: deger})
        self.assertFalse(os.path.exists(cfg.makine_dosyasi()))

    def test_bozuk_dosya_bos_sayilir(self):
        os.makedirs(self.ev)
        with open(cfg.makine_dosyasi(), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertFalse(cfg.makine_taze_mi())
        self.assertEqual(cfg.kaynakli_al("python"), (None, "yok"))

    def test_gecici_dosya_kalmaz(self):
        cfg.makine_yaz({"python": "p"})
        self.assertEqual(os.listdir(self.ev), ["makine.json"])


class KesifTest(unittest.TestCase):
    """P4: keşif tek yerde; geçersiz (bayat) değer bir sonraki katmana düşer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"ORKESTRA_HOME": os.path.join(self.tmp.name, "ev")})
        p.start()
        self.addCleanup(p.stop)
        for ad in cfg.ORTAM.values():
            os.environ.pop(ad, None)

    def test_bayat_makine_degeri_kesfe_duser(self):
        yok = os.path.join(self.tmp.name, "yok", "claude.exe")
        cfg.makine_yaz({"claude_exe": yok})
        gercek = os.path.join(self.tmp.name, "claude.exe")
        open(gercek, "w").close()
        with mock.patch.dict(cfg.KESIF, {"claude_exe": lambda: gercek}):
            self.assertEqual(cfg.kaynakli_al("claude_exe"), (gercek, "kesif"))

    def test_gecersiz_ortam_degeri_atlanir_python_atlanmaz(self):
        os.environ["CLAUDE_CODE_EXECPATH"] = os.path.join(self.tmp.name, "yok.exe")
        with mock.patch.dict(cfg.KESIF, {"claude_exe": lambda: None}):
            self.assertEqual(cfg.kaynakli_al("claude_exe"), (None, "yok"))
        os.environ["ORKESTRA_PYTHON"] = "/yok/python"  # python doğrulanmaz: aynen kabul
        self.assertEqual(cfg.kaynakli_al("python"), ("/yok/python", "ortam"))

    def test_kesif_python_son_care_sys_executable(self):
        with mock.patch.object(cfg.shutil, "which", return_value=None):
            self.assertEqual(cfg.kesif_python(), sys.executable)

    def test_bash_system32_stub_atlanir(self):
        stub = r"C:\Windows\System32\bash.exe"
        bos = {"ProgramFiles": "", "ProgramFiles(x86)": "", "LOCALAPPDATA": ""}
        with mock.patch.object(cfg.shutil, "which", side_effect=lambda a: stub if a == "bash" else None), \
                mock.patch.dict(os.environ, bos):
            self.assertIsNone(cfg.kesif_bash())

    def test_bash_git_kurulumundan_bulunur(self):
        git = os.path.join(self.tmp.name, "Git")
        os.makedirs(os.path.join(git, "cmd"))
        os.makedirs(os.path.join(git, "bin"))
        for f in (os.path.join(git, "cmd", "git.exe"), os.path.join(git, "bin", "bash.exe")):
            open(f, "w").close()
        gitexe = os.path.join(git, "cmd", "git.exe")
        with mock.patch.object(cfg.shutil, "which", side_effect=lambda a: gitexe if a == "git" else None):
            self.assertEqual(cfg.kesif_bash(), os.path.join(git, "bin", "bash.exe"))

    def test_panel_port(self):
        self.assertEqual(cfg.panel_port(), 8765)
        os.environ["ORKESTRA_PANEL_PORT"] = "9001"
        self.assertEqual(cfg.panel_port(), 9001)
        os.environ["ORKESTRA_PANEL_PORT"] = "abc"
        self.assertEqual(cfg.panel_port(), 8765)
        os.environ["ORKESTRA_PANEL_PORT"] = "99999"
        self.assertEqual(cfg.panel_port(), 8765)


class SurumTest(unittest.TestCase):
    """P4-K2: eklenti_surumu() zinciri: plugin.json version > önbellek klasör adı > git özeti > '?'."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def kok(self, *parca, manifest=None):
        kok = os.path.join(self.tmp.name, *parca)
        os.makedirs(os.path.join(kok, ".claude-plugin"))
        if manifest is not None:
            with open(os.path.join(kok, ".claude-plugin", "plugin.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f)
        return kok

    def surum(self, kok):
        with mock.patch.object(cfg, "eklenti_koku", return_value=kok):
            return cfg.eklenti_surumu()

    def test_manifest_surumu_oncelikli(self):
        self.assertEqual(self.surum(self.kok("orkestra", "1.2.3", manifest={"version": "9.9"})), "9.9")

    def test_onbellek_klasor_adi(self):
        self.assertEqual(self.surum(self.kok("x", "orkestra", "0.4.1", manifest={"name": "orkestra"})), "0.4.1")

    def test_git_ozeti(self):
        kok = self.kok("depo", "orkestra", manifest={"name": "orkestra"})
        sonuc = mock.Mock(returncode=0, stdout="abc1234\n")
        with mock.patch.object(cfg.subprocess, "run", return_value=sonuc):
            self.assertEqual(self.surum(kok), "git-abc1234")

    def test_hicbiri_yoksa_soru_isareti(self):
        kok = self.kok("depo", "orkestra")  # manifest dosyası yok
        with mock.patch.object(cfg.subprocess, "run", side_effect=OSError("git yok")):
            self.assertEqual(self.surum(kok), "?")
        with mock.patch.object(cfg.subprocess, "run", return_value=mock.Mock(returncode=128, stdout="")):
            self.assertEqual(self.surum(kok), "?")

    def test_bozuk_manifest_dusurmez(self):
        kok = self.kok("depo", "orkestra")
        with open(os.path.join(kok, ".claude-plugin", "plugin.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        with mock.patch.object(cfg.subprocess, "run", side_effect=OSError):
            self.assertEqual(self.surum(kok), "?")


if __name__ == "__main__":
    unittest.main()
