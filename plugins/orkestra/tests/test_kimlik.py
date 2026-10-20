"""Kimlik klasörü (ADR-0008): okuyucu değer sızdırmaz, öncelik, ACL, ajan engeli, aktarım."""
import os
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import kimlik as K  # noqa: E402
import izin_politikasi as IP  # noqa: E402

CLI = os.path.join(KOK, "scripts", "orkestra.py")
SIR = "s3kr3t-DEGER-9876"


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.eski = {k: os.environ.get(k) for k in ("ORKESTRA_KIMLIK_DIZINI", "ORKESTRA_KIMLIK_PROJE", "DB_PW")}
        os.environ["ORKESTRA_KIMLIK_DIZINI"] = os.path.join(self.t, "cred")
        os.environ["ORKESTRA_KIMLIK_PROJE"] = "Proje"
        os.environ.pop("DB_PW", None)
        os.makedirs(os.path.join(self.t, "cred", "Proje"))
        os.makedirs(os.path.join(self.t, "cred", "_ortak"))
        with open(os.path.join(self.t, "cred", "Proje", "db.env"), "w") as f:
            f.write(f"# yorum\nDB_PW={SIR}\nexport DB_USER='kul'\n")
        with open(os.path.join(self.t, "cred", "_ortak", "mail.env"), "w") as f:
            f.write("MAIL_KEY=ortakdeger\n")

    def tearDown(self):
        for k, v in self.eski.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def cli(self, *a):
        env = dict(os.environ)
        return subprocess.run([sys.executable, CLI, "kimlik", *a], capture_output=True, text=True, env=env, encoding="utf-8")


class Okuyucu(Temel):
    def test_al_ve_oncelik(self):
        self.assertEqual(K.al("db", "DB_PW"), SIR)
        self.assertEqual(K.al("db", "DB_USER"), "kul")
        os.environ["DB_PW"] = "ortamdan"
        self.assertEqual(K.al("db", "DB_PW"), "ortamdan")

    def test_ortak_yedek(self):
        self.assertEqual(K.al("mail", "MAIL_KEY"), "ortakdeger")

    def test_hata_degersiz(self):
        with self.assertRaises(K.KimlikHata) as c:
            K.al("db", "YOK_ANAHTAR")
        self.assertNotIn(SIR, str(c.exception))
        with self.assertRaises(K.KimlikHata):
            K.al("../db", "DB_PW")  # yol kaçışı

    def test_cli_deger_yazmaz(self):
        for a in (("liste",), ("var", "db", "DB_PW"), ("var", "db", "YOK"), ("denetle",)):
            r = self.cli(*a)
            self.assertNotIn(SIR, r.stdout + r.stderr, a)
        self.assertIn("DB_PW", self.cli("liste").stdout)
        self.assertEqual(self.cli("var", "db", "DB_PW").returncode, 0)
        self.assertEqual(self.cli("var", "db", "YOK").returncode, 1)

    def test_calistir_ortam_verir_cikti_maskeli(self):
        r = self.cli("calistir", "db", "--", sys.executable, "-c", "import os;print(os.environ['DB_PW']);print('ok')")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn(SIR, r.stdout + r.stderr)
        self.assertIn("***", r.stdout)
        self.assertIn("ok", r.stdout)


class Yapi(Temel):
    def test_kur_acl_ve_denetle(self):
        yeni = os.path.join(self.t, "yeni")
        os.environ["ORKESTRA_KIMLIK_DIZINI"] = yeni
        K.kur()
        self.assertTrue(os.path.isdir(os.path.join(yeni, "Proje")))
        self.assertEqual(K.izin_gevsek_mi(yeni), [])

    def test_aktar_kopyalar_ezmez_deger_yazmaz(self):
        kay = os.path.join(self.t, "Keys")
        os.makedirs(kay)
        with open(os.path.join(kay, "yeni.env"), "w") as f:
            f.write("A_KEY=abc12345\n")
        with open(os.path.join(kay, "db.env"), "w") as f:
            f.write("DB_PW=baska\n")
        kuru = K.aktar(kay)
        self.assertFalse(os.path.exists(os.path.join(self.t, "cred", "Proje", "yeni.env")))
        K.aktar(kay, uygula=True)
        self.assertEqual(K.al("yeni", "A_KEY"), "abc12345")
        self.assertEqual(K.al("db", "DB_PW"), SIR)  # var olan ezilmedi
        self.assertEqual({s: d for s, d, _ in kuru}["db"], "atlandı (hedefte var)")
        self.assertTrue(os.path.isfile(os.path.join(kay, "yeni.env")))  # kaynak silinmedi


class AjanEngeli(unittest.TestCase):
    def test_dosya_ve_kabuk_engeli(self):
        yol = os.path.join(os.path.expanduser("~"), ".orkestra", "credentials", "McD", "db.env")
        self.assertEqual(IP.karar("Read", {"file_path": yol})[0], "deny")
        self.assertEqual(IP.karar("Edit", {"file_path": yol})[0], "deny")
        self.assertEqual(IP.karar("Bash", {"command": f"cat {yol}"})[0], "deny")
        self.assertEqual(IP.karar("Grep", {"path": os.path.dirname(yol), "pattern": "x"})[0], "deny")

    def test_okuyucu_komutu_serbest(self):
        self.assertNotEqual(IP.karar("Bash", {"command": "orkestra kimlik liste"})[0], "deny")
        self.assertNotEqual(IP.karar("Read", {"file_path": "C:/Mert/McD/CLAUDE.md"})[0], "deny")


if __name__ == "__main__":
    unittest.main()
