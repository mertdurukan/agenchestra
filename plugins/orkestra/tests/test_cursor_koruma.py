"""Issue #14 PR-1: araclar/cursor_koruma.py. Gecici git deposunda taban + dal kurar; bayt esitligi,
yazma izin listesi, ortak kod govde isareti ve kural kaynagi (taban) denetlenir."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(KOK / "araclar"))
import cursor_koruma as K  # noqa: E402

KURALLAR = KOK / "plugins" / "orkestra" / "cursor" / "koruma_kurallari.json"
GIT_VAR = shutil.which("git") is not None


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false"] + list(args),
                   cwd=str(cwd), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _yaz(kok, yol, icerik):
    p = Path(kok) / yol
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(icerik if isinstance(icerik, bytes) else icerik.encode("utf-8"))


class EslesmeTest(unittest.TestCase):
    def test_onek_ve_fnmatch(self):
        self.assertTrue(K.esles("plugins/orkestra/skills/is/SKILL.md", "plugins/orkestra/skills/**"))
        self.assertFalse(K.esles("plugins/orkestra/skills2/x", "plugins/orkestra/skills/**"))
        self.assertTrue(K.esles("araclar/cursor_kur.py", "araclar/cursor_*"))
        self.assertFalse(K.esles("araclar/changelog.py", "araclar/cursor_*"))
        self.assertTrue(K.esles("a/b/", "a/b/"))

    def test_gercek_kurallar_gecerli(self):
        k = json.loads(KURALLAR.read_text(encoding="utf-8"))
        for alan in ("bayt_esit", "yazma_izin", "ortak_kod", "cerceve"):
            self.assertTrue(k[alan], alan)
        # bayt esit ile yazma izni cakismaz (ornek dosyalarla)
        for ornek in ("plugins/orkestra/scripts/hook.py", "plugins/orkestra/skills/is/SKILL.md",
                      "plugins/orkestra/hooks/hooks.json", "plugins/orkestra/agents/denetci.md",
                      "plugins/orkestra/workflows/calistir.js", ".claude-plugin/marketplace.json",
                      "plugins/orkestra/.claude-plugin/plugin.json"):
            self.assertTrue(K.eslesir_mi(ornek, k["bayt_esit"]), ornek)
            self.assertFalse(K.eslesir_mi(ornek, k["yazma_izin"]), ornek)
        # cursor-hooks.json bayt esit kapsaminda degil, izinli
        self.assertFalse(K.eslesir_mi("plugins/orkestra/hooks/cursor-hooks.json", k["bayt_esit"]))
        self.assertTrue(K.eslesir_mi("plugins/orkestra/hooks/cursor-hooks.json", k["yazma_izin"]))
        # ortak kod ayri sinif: izin listesinde degil
        for o in k["ortak_kod"]:
            self.assertFalse(K.eslesir_mi(o, k["bayt_esit"]), o)
            self.assertFalse(K.eslesir_mi(o, k["yazma_izin"]), o)


@unittest.skipUnless(GIT_VAR, "git yok")
class DenetimTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ork_koruma_")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        _git(self.d, "init", "-q", "-b", "main")
        _yaz(self.d, "plugins/orkestra/cursor/koruma_kurallari.json", KURALLAR.read_bytes())
        _yaz(self.d, "plugins/orkestra/scripts/hook.py", b"hook\r\nsatir\n")  # CR korunur
        _yaz(self.d, "plugins/orkestra/hooks/hooks.json", "{}\n")
        _yaz(self.d, "plugins/orkestra/skills/is/SKILL.md", "is\n")
        _yaz(self.d, "plugins/orkestra/agents/denetci.md", "denetci\n")
        _yaz(self.d, "plugins/orkestra/scripts/doktor.py", "doktor\n")
        _yaz(self.d, "plugins/orkestra/scripts/cursor_hook.py", "ch\n")
        _yaz(self.d, "README.md", "r\n")
        _git(self.d, "add", "-A")
        _git(self.d, "commit", "-q", "-m", "taban")
        _git(self.d, "checkout", "-q", "-b", "cursor/x")

    def _commit(self):
        _git(self.d, "add", "-A")
        _git(self.d, "commit", "-q", "-m", "dal")

    def _calistir(self, govde=""):
        return K.denetle("main", govde, self.d)

    def test_degisiklik_yok_temiz(self):
        ihlal, uyari, _ = self._calistir()
        self.assertEqual(ihlal, [])
        self.assertEqual(uyari, [])

    def test_izinli_yazma_temiz(self):
        _yaz(self.d, "plugins/orkestra/scripts/cursor_hook.py", "yeni\n")
        _yaz(self.d, "araclar/cursor_kur.py", "x\n")
        _yaz(self.d, "adr/ADR-9999-x.md", "x\n")
        _yaz(self.d, "plugins/orkestra/tests/test_cursor_yeni.py", "x\n")
        _yaz(self.d, "README.md", "r2\n")
        self._commit()
        ihlal, _, _ = self._calistir()
        self.assertEqual(ihlal, [])

    def test_hook_py_degisimi_ihlal(self):
        _yaz(self.d, "plugins/orkestra/scripts/hook.py", b"hook\nsatir\n")  # yalniz CR farki: bayt duzeyi
        self._commit()
        ihlal, _, _ = self._calistir()
        self.assertEqual(len([i for i in ihlal if "hook.py" in i and "degismis" in i]), 1, ihlal)

    def test_claude_dosyasi_eklenir_silinir(self):
        _yaz(self.d, "plugins/orkestra/skills/yeni/SKILL.md", "y\n")
        os.remove(str(Path(self.d) / "plugins/orkestra/agents/denetci.md"))
        self._commit()
        ihlal, _, _ = self._calistir()
        self.assertTrue(any("eklenmis" in i and "skills/yeni" in i for i in ihlal), ihlal)
        self.assertTrue(any("silinmis" in i and "denetci.md" in i for i in ihlal), ihlal)

    def test_izin_disi_yol_ihlal(self):
        _yaz(self.d, "plugins/orkestra/scripts/baska.py", "x\n")
        self._commit()
        ihlal, _, _ = self._calistir()
        self.assertEqual(ihlal, ["yazma_izin: izin listesinde olmayan yol: plugins/orkestra/scripts/baska.py"])

    def test_ortak_kod_govde_isareti(self):
        _yaz(self.d, "plugins/orkestra/scripts/doktor.py", "doktor2\n")
        self._commit()
        ihlal, _, _ = self._calistir("## Paylaşılan koda dokunuldu mu\nHayır.\n")
        self.assertEqual(len(ihlal), 1, ihlal)
        ihlal, _, _ = self._calistir("")
        self.assertEqual(len(ihlal), 1, ihlal)
        ihlal, uyari, _ = self._calistir("## Paylaşılan koda dokunuldu mu\r\nEvet: doktor.py:10-20, CURSOR_VERSION\r\n")
        self.assertEqual(ihlal, [])
        self.assertEqual(len(uyari), 1)

    def test_kurallar_tabandan_okunur(self):
        # PR kendi kuralini gevsetir: hook.py'yi izne ekler. Taban kurali gecerli kalir.
        k = json.loads(KURALLAR.read_text(encoding="utf-8"))
        k["bayt_esit"] = []
        _yaz(self.d, "plugins/orkestra/cursor/koruma_kurallari.json", json.dumps(k))
        _yaz(self.d, "plugins/orkestra/scripts/hook.py", "farkli\n")
        self._commit()
        ihlal, uyari, _ = self._calistir()
        self.assertTrue(any("hook.py" in i for i in ihlal), ihlal)
        self.assertTrue(any("cercevesi degisti" in u for u in uyari), uyari)

    def test_tabanda_kural_yoksa_head_surumu_ve_uyari(self):
        _git(self.d, "checkout", "-q", "main")
        _git(self.d, "rm", "-q", "plugins/orkestra/cursor/koruma_kurallari.json")
        _git(self.d, "commit", "-q", "-m", "kuralsiz taban")
        _git(self.d, "checkout", "-q", "-b", "cursor/y")
        _yaz(self.d, "plugins/orkestra/cursor/koruma_kurallari.json", KURALLAR.read_bytes())
        self._commit()
        ihlal, uyari, _ = self._calistir()
        self.assertEqual(ihlal, [])
        self.assertTrue(any("tabanda yok" in u for u in uyari), uyari)

    def test_liste_sha256_ve_cli(self):
        _yaz(self.d, "plugins/orkestra/scripts/cursor_hook.py", "yeni\n")
        self._commit()
        liste = K.sha256_listesi("HEAD", ["plugins/orkestra/scripts/hook.py"], self.d)
        import hashlib
        self.assertEqual(liste, {"plugins/orkestra/scripts/hook.py": hashlib.sha256(b"hook\r\nsatir\n").hexdigest()})
        cwd = os.getcwd()
        os.chdir(self.d)
        try:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                kod = K.main(["--denetle", "--taban", "main"])
            self.assertEqual(kod, 0, out.getvalue() + err.getvalue())
            _yaz(self.d, "plugins/orkestra/hooks/hooks.json", "{ }\n")
            self._commit()
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                kod = K.main(["--denetle", "--taban", "main"])
            self.assertEqual(kod, 1)
            self.assertIn("::error::", out.getvalue())
        finally:
            os.chdir(cwd)

    def test_gecersiz_taban_kod_2(self):
        cwd = os.getcwd()
        os.chdir(self.d)
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(K.main(["--denetle", "--taban", "yok/yok"]), 2)
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
