"""Codebase ortamı kurucusu ve veri kaynağı profili (I-249, ADR-0001): sahte runner, gerçek ağ/kurulum yok."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ortam as O  # noqa: E402
import ortam_db as D  # noqa: E402


class Kurucu(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.kok, "api"))
        with open(os.path.join(self.kok, "api", "requirements.txt"), "w") as f:
            f.write("x==1\n")
        with open(os.path.join(self.kok, "api", "uv.lock"), "w") as f:
            f.write("v1")
        self.yol = os.path.join(self.kok, "_v", "api")
        self.kayit = {"ad": "api", "yer": "api", "tur": "python", "kilit_turu": "uv", "kilit_dosyasi": "uv.lock",
                      "manifestler": ["requirements.txt"], "ortam_yolu": self.yol}
        self.komutlar = []

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def runner(self, kod=0):
        def r(komut, cwd, env):
            self.komutlar.append((komut, cwd, env))
            if kod == 0 and ("venv" in komut or komut[0] == "uv"):
                os.makedirs(os.path.dirname(O.python_yolu(self.yol)), exist_ok=True)
                open(O.python_yolu(self.yol), "w").close()
            return kod, "hata satiri"
        return r

    def test_uv_varsa_uv_sync_locked(self):
        s = O.kur(self.kayit, self.kok, self.runner(), uv_var=True)
        self.assertEqual(s["arac"], "uv")
        self.assertEqual(self.komutlar[0][0], ["uv", "sync", "--locked"])
        self.assertEqual(self.komutlar[0][2]["UV_PROJECT_ENVIRONMENT"], self.yol)
        self.assertEqual(O.dogrula(self.kayit, self.kok)["durum"], "guncel")

    def test_uv_yoksa_pip_yedegi(self):
        s = O.kur(self.kayit, self.kok, self.runner(), uv_var=False)
        self.assertEqual(s["arac"], "pip")
        self.assertIn("-r", self.komutlar[1][0])

    def test_kilit_degisince_eski(self):
        O.kur(self.kayit, self.kok, self.runner(), uv_var=True)
        with open(os.path.join(self.kok, "api", "uv.lock"), "w") as f:
            f.write("v2")
        self.assertEqual(O.dogrula(self.kayit, self.kok)["durum"], "eski")

    def test_hatada_yarim_ortam_silinir(self):
        os.makedirs(self.yol)
        with self.assertRaises(O.OrtamHata) as c:
            O.kur(self.kayit, self.kok, self.runner(kod=1), uv_var=True)
        self.assertIn("kod 1", str(c.exception))
        self.assertFalse(os.path.exists(self.yol))
        self.assertEqual(O.dogrula(self.kayit, self.kok)["durum"], "yok")

    def test_kilitsiz_node_reddedilir(self):
        k = dict(self.kayit, tur="node", kilit_turu="kilitsiz", ortam_yolu=os.path.join(self.kok, "api", "node_modules"))
        with self.assertRaises(O.OrtamHata):
            O.kur(k, self.kok, self.runner())

    def test_node_npm_ci(self):
        k = dict(self.kayit, tur="node", kilit_turu="npm-ci", kilit_dosyasi="package-lock.json", manifestler=["package.json"],
                 ortam_yolu=os.path.join(self.kok, "api", "node_modules"))
        O.kur(k, self.kok, self.runner())
        self.assertEqual(self.komutlar[0][0], ["npm", "ci"])


class Profil(unittest.TestCase):
    def test_gecerli_profil_salt_okunur(self):
        p = D.profil("klibre_pg", {"tur": "postgres", "kimlik": "klibre_db", "kapi": ".claude/skills/db-olcum/scripts/kapi.py"})
        self.assertTrue(p["salt_okunur"])
        self.assertEqual(p["kimlik"], "klibre_db")

    def test_salt_okunur_olmayan_reddedilir(self):
        with self.assertRaises(D.ProfilHata):
            D.profil("x", {"tur": "postgres", "kimlik": "k", "salt_okunur": False})

    def test_sir_kalibi_reddedilir(self):
        for deger in ("password=abc123", "postgres://kul:parola@host/db", "A" * 40):
            with self.assertRaises(D.ProfilHata, msg=deger):
                D.profil("x", {"tur": "postgres", "kimlik": deger})

    def test_kimlik_cozulmedi_ve_baglanti_yok(self):
        d = tempfile.mkdtemp()
        os.environ["ORKESTRA_KIMLIK_DIZINI"] = d
        try:
            os.makedirs(os.path.join(d, "p"))
            with open(os.path.join(d, "p", "klibre_db.env"), "w") as f:
                f.write("A=1\n")
            p = D.profil("a", {"tur": "postgres", "kimlik": "klibre_db"})
            self.assertEqual(D.coz(p, "p")["kimlik_durumu"], "var")
            self.assertEqual(D.coz(dict(p, kimlik="yok_kayit"), "p")["kimlik_durumu"], "çözülemedi")
        finally:
            os.environ.pop("ORKESTRA_KIMLIK_DIZINI", None)
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
