"""Yasak içerik kapısı: yazım anı hook'u ve push öncesi tarama; yapılandırma yokken sessiz."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import push_kapisi  # noqa: E402,F401
import icerik_kapisi as IK  # noqa: E402

DESEN = r"(?<![a-z])zzmusteri(?![a-z])"


def git(kok, *a):
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", kok, *a], capture_output=True, text=True, encoding="utf-8").stdout.strip()


class IcerikKapisi(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_ik_")
        git(self.kok, "init", "-q", "-b", "main")
        git(self.kok, "config", "user.email", "t@example.com")
        git(self.kok, "config", "user.name", "t")
        self.dosya = os.path.join(self.kok, "a.py")
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("ORKESTRA_ICERIK_YASAK", "ORKESTRA_ICERIK_KAPISI"):
            os.environ.pop(k, None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.kok, ignore_errors=True)

    def ayar_yaz(self):
        p = os.path.join(self.kok, IK.AYAR_ADI)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"icerik_desenleri": [DESEN]}, f)

    def kapi(self, arac, girdi):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook._icerik_kapisi(arac, girdi, self.dosya)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        if not ham:
            return False
        return json.loads(ham.splitlines()[-1])["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_yazim_ihlali_reddedilir(self):
        self.ayar_yaz()
        self.assertTrue(self.kapi("Edit", {"file_path": self.dosya, "old_string": "x", "new_string": "ZZMusteri verisi"}))
        self.assertTrue(self.kapi("Write", {"file_path": self.dosya, "content": "a\nzzmusteri\n"}))
        self.assertTrue(self.kapi("MultiEdit", {"file_path": self.dosya, "edits": [{"old_string": "a", "new_string": "zzmusteri"}]}))

    def test_temiz_metin_gecer(self):
        self.ayar_yaz()
        self.assertFalse(self.kapi("Edit", {"file_path": self.dosya, "old_string": "x", "new_string": "AcmeRetail"}))
        self.assertFalse(self.kapi("Write", {"file_path": self.dosya, "content": "zzmusterilik"}))  # sözcük sınırı

    def test_yapilandirma_yokken_sessiz(self):
        self.assertFalse(self.kapi("Write", {"file_path": self.dosya, "content": "zzmusteri"}))

    def test_ortam_degiskeni_ve_kapatma(self):
        os.environ["ORKESTRA_ICERIK_YASAK"] = DESEN
        self.assertTrue(self.kapi("Write", {"file_path": self.dosya, "content": "zzmusteri"}))
        os.environ["ORKESTRA_ICERIK_KAPISI"] = "0"
        self.assertFalse(self.kapi("Write", {"file_path": self.dosya, "content": "zzmusteri"}))

    def test_bozuk_desen_ve_ayar_fail_open(self):
        p = os.path.join(self.kok, IK.AYAR_ADI)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertFalse(self.kapi("Write", {"file_path": self.dosya, "content": "zzmusteri"}))
        os.environ["ORKESTRA_ICERIK_YASAK"] = "(acik["
        self.assertFalse(self.kapi("Write", {"file_path": self.dosya, "content": "zzmusteri"}))

    def test_push_taramasi_eklenen_satiri_yakalar(self):
        self.ayar_yaz()
        with open(self.dosya, "w", encoding="utf-8") as f:
            f.write("temiz\n")
        git(self.kok, "add", "a.py")
        git(self.kok, "commit", "-q", "-m", "bir")
        with open(self.dosya, "a", encoding="utf-8") as f:
            f.write("zzmusteri sizdi\n")
        git(self.kok, "commit", "-qam", "iki")
        sonuc = IK.push_ihlalleri(self.kok, lambda k, *a: git(k, *a), ["HEAD~1..HEAD"])
        self.assertEqual(len(sonuc), 1)
        self.assertEqual(IK.push_ihlalleri(self.kok, lambda k, *a: git(k, *a), ["HEAD~2..HEAD~1"]), [])

    def test_push_kapisi_kontrol_ihlalde_1_temizde_0(self):
        import push_kapisi as PK
        self.ayar_yaz()
        with open(self.dosya, "w", encoding="utf-8") as f:
            f.write("temiz" + chr(10))
        git(self.kok, "add", "a.py")
        git(self.kok, "commit", "-q", "-m", "bir")
        ilk = git(self.kok, "rev-parse", "HEAD")
        with open(self.dosya, "a", encoding="utf-8") as f:
            f.write("zzmusteri" + chr(10))
        git(self.kok, "commit", "-qam", "iki")
        son = git(self.kok, "rev-parse", "HEAD")
        degisim = "refs/heads/main %s refs/heads/main %s" + chr(10)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(PK.kontrol("origin", degisim % (son, ilk), self.kok), 1)
            self.assertEqual(PK.kontrol("origin", degisim % (ilk, ilk), self.kok), 0)
        os.remove(os.path.join(self.kok, IK.AYAR_ADI))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(PK.kontrol("origin", degisim % (son, ilk), self.kok), 0)


if __name__ == "__main__":
    unittest.main()
