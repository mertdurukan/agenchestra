"""`orkestra ortam calistir` (I-249, ADR-0001): yorumlayıcı çözümü, kurulu olmayan ortam reddi, bilinmeyen codebase, kimlik yolu."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ortam as O  # noqa: E402
import ortam_calistir as C  # noqa: E402


class Calistir(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.kok, "api"))
        with open(os.path.join(self.kok, "api", "requirements.txt"), "w") as f:
            f.write("x==1\n")
        self.yol = os.path.join(self.kok, "_v", "api")
        self.kayit = {"ad": "api", "dizin": "api", "tur": "python", "kilit_turu": "pip", "kilit_dosyasi": "requirements.txt",
                      "manifestler": ["requirements.txt"], "ortam_yolu": self.yol}

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def kur(self):
        def r(komut, cwd, env):
            os.makedirs(os.path.dirname(O.python_yolu(self.yol)), exist_ok=True)
            open(O.python_yolu(self.yol), "w").close()
            return 0, ""
        O.kur(self.kayit, self.kok, r, uv_var=False)

    def test_kurulu_degilse_reddedilir(self):
        with self.assertRaises(O.OrtamHata) as c:
            C.hazirla(self.kayit, self.kok, ["python", "-V"])
        self.assertIn("ortam kur", str(c.exception))

    def test_python_ortamin_yorumlayicisina_cevrilir(self):
        self.kur()
        komut, cwd, env = C.hazirla(self.kayit, self.kok, ["python", "-m", "pytest"])
        self.assertEqual(komut[0], O.python_yolu(self.yol))
        self.assertEqual(komut[1], "-I")
        self.assertEqual(komut[2:], ["-X", "utf8", "-m", "pytest"])
        self.assertEqual(cwd, os.path.join(self.kok, "api"))
        self.assertTrue(env["PATH"].startswith(os.path.dirname(O.python_yolu(self.yol))))

    def test_python_olmayan_komut_degismez(self):
        self.kur()
        komut, _, _ = C.hazirla(self.kayit, self.kok, ["pytest", "-q"])
        self.assertEqual(komut, ["pytest", "-q"])

    def test_bos_komut_reddedilir(self):
        self.kur()
        with self.assertRaises(O.OrtamHata):
            C.hazirla(self.kayit, self.kok, [])

    def test_bilinmeyen_codebase(self):
        sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(sd)
        with self.assertRaises(O.OrtamHata) as c:
            O.bul(self.kok, sd, "yok-boyle-bir-sey")
        self.assertIn("bilinmeyen codebase", str(c.exception))

    def test_kimlik_verilirse_kimlik_calistir_cwd_ve_env_ile_cagrilir(self):
        self.kur()
        with mock.patch("kimlik.calistir", return_value=0) as m:
            self.assertEqual(C.calistir(self.kayit, self.kok, ["python", "-V"], kimlik="servis", proje="p"), 0)
        args, kw = m.call_args
        self.assertEqual(args[0], "servis")
        self.assertEqual(kw["cwd"], os.path.join(self.kok, "api"))
        self.assertIn("PATH", kw["env_ek"])

    def test_gercek_koşu_ortamin_pythonu(self):
        self.kur()
        # sahte python.exe boş dosya: gerçek koşu yerine subprocess çağrısını sına
        with mock.patch("subprocess.run") as m:
            m.return_value.returncode = 7
            m.return_value.stdout = b""
            m.return_value.stderr = b""
            self.assertEqual(C.calistir(self.kayit, self.kok, ["python", "-V"]), 7)
        self.assertEqual(m.call_args[0][0][0], O.python_yolu(self.yol))


if __name__ == "__main__":
    unittest.main()
