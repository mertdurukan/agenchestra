"""P10 (I-026): proje kontrolleri (doktor.d) ve projeye_kur.py .gitignore satırları."""
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import doktor  # noqa: E402
from doktor import Baglam  # noqa: E402

DEPO = os.path.dirname(os.path.dirname(KOK))


def projeye_kur():
    spec = importlib.util.spec_from_file_location("projeye_kur_p10", os.path.join(DEPO, "araclar", "projeye_kur.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ProjeKontrolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proje = self.tmp.name
        self.d = os.path.join(self.proje, ".claude", "orkestra", "doktor.d")
        os.makedirs(self.d)
        p = mock.patch.dict(os.environ, {"ORKESTRA_HOME": os.path.join(self.tmp.name, "ev")})
        p.start()
        self.addCleanup(p.stop)

    def yaz(self, ad, kod):
        with open(os.path.join(self.d, ad), "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(kod))

    SAHTE = """
        from doktor import Kontrol, Sonuc
        KONTROLLER = [Kontrol("vpn", "VPN bağlı", "opsiyonel", lambda b: Sonuc("uyari", "VPN yok"))]
    """

    def kos(self, **kw):
        return doktor.kos(Baglam(proje=self.proje, kuru=True, **kw))

    def bul(self, s, id):
        return next((x for x in s["kontroller"] if x["id"] == id), None)

    def test_sahte_proje_kontrolu_cikti_icinde_gorunur(self):
        self.yaz("a_vpn.py", self.SAHTE)
        s = self.kos()
        x = self.bul(s, "proje:vpn")
        self.assertEqual((x["durum"], x["mesaj"]), ("uyari", "VPN yok"))
        self.assertEqual(len(s["kontroller"]), len(doktor.KONTROLLER) + 1)

    def test_bozuk_dosyalar_doktoru_dusurmez(self):
        self.yaz("b_sozdizimi.py", "def (:\n")
        self.yaz("c_patlar.py", "raise RuntimeError('yükleme patladı')\n")
        self.yaz("d_cikar.py", "import sys\nsys.exit(3)\n")
        self.yaz("e_yanlis_tip.py", "KONTROLLER = ['kontrol degil']\n")
        self.yaz("f_kontrolsuz.py", "x = 1\n")
        self.yaz("g_vpn.py", self.SAHTE)
        s = self.kos()
        for ad in ("b_sozdizimi.py", "c_patlar.py", "d_cikar.py", "e_yanlis_tip.py", "f_kontrolsuz.py"):
            x = self.bul(s, "proje:" + ad)
            self.assertEqual(x["durum"], "hata", ad)
            self.assertIn("yüklenemedi", x["mesaj"])
            self.assertEqual(x["sinif"], "opsiyonel")  # bozuk dosya çıkış kodunu 1 yapmaz
        self.assertIsNotNone(self.bul(s, "proje:vpn"))  # bozuk dosyalardan sonra sağlam olan yine yüklenir
        self.assertEqual([k for k in s["zorunlu_hata"] if k.startswith("proje:")], [])

    def test_arka_plan_kosusu_proje_kodunu_yuklemez(self):
        iz = os.path.join(self.proje, "calisti.txt")
        self.yaz("h_iz.py", f"open({iz!r}, 'w').close()\n" + textwrap.dedent(self.SAHTE))
        s = self.kos(proje_kod=False)
        self.assertFalse(os.path.exists(iz))
        self.assertIsNone(self.bul(s, "proje:vpn"))
        self.kos()  # kullanıcı koşusunda yüklenir
        self.assertTrue(os.path.exists(iz))

    def test_arka_plan_bayragi_cli_ve_baslaticida(self):
        import cfg
        os.environ.pop("ORKESTRA_DOKTOR_OTOMATIK", None)
        with mock.patch.object(cfg.subprocess, "Popen") as po:
            cfg.doktor_baslat(self.proje)
        self.assertIn("--arka-plan", po.call_args[0][0])
        ap = __import__("argparse").ArgumentParser()
        doktor.argumanlar(ap)
        self.assertTrue(ap.parse_args(["--arka-plan"]).arka_plan)

    def test_klasor_yoksa_bos(self):
        self.assertEqual(doktor.proje_kontrolleri(os.path.join(self.tmp.name, "yok")), [])
        self.assertEqual(doktor.proje_kontrolleri(None), [])


class GitignoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.makedirs(os.path.join(self.tmp.name, ".git"))
        self.yol = os.path.join(self.tmp.name, ".gitignore")
        self.m = projeye_kur()

    def calistir(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.gitignore(self.tmp.name, False)

    def oku(self):
        with open(self.yol, encoding="utf-8", newline="") as f:
            return f.read()

    def yaz(self, metin):
        with open(self.yol, "w", encoding="utf-8", newline="") as f:
            f.write(metin)

    def test_iki_kez_calisinca_cift_satir_yok(self):
        self.yaz("node_modules/\n")
        self.calistir()
        ilk = self.oku()
        self.calistir()
        self.assertEqual(self.oku(), ilk)
        for satir in self.m.GITIGNORE:
            self.assertEqual(ilk.splitlines().count(satir), 1, satir)

    def test_yerel_config_ve_doktor_d_satirlari_var(self):
        self.calistir()
        s = self.oku().splitlines()
        self.assertIn(".claude/orkestra/yerel.json", s)
        self.assertLess(s.index(".claude/orkestra/*"), s.index("!.claude/orkestra/doktor.d/"))  # tekrar dahil etme, joker satırdan sonra

    def test_crlf_korunur(self):
        self.yaz("a/\r\nb/\r\n")
        self.calistir()
        ham = self.oku()
        self.assertNotIn("\n", ham.replace("\r\n", ""))  # çıplak LF yok
        self.calistir()
        self.assertEqual(self.oku(), ham)

    def test_lf_korunur(self):
        self.yaz("a/\nb/\n")
        self.calistir()
        self.assertNotIn("\r", self.oku())

    def test_son_satir_yeni_satirsizsa_birlesmez(self):
        self.yaz("a/")
        self.calistir()
        self.assertEqual(self.oku().splitlines()[0], "a/")

    def test_var_olan_satirlar_crlf_dosyada_tekrarlanmaz(self):
        self.yaz("\r\n".join(self.m.GITIGNORE) + "\r\n")
        self.calistir()
        self.assertEqual(self.oku(), "\r\n".join(self.m.GITIGNORE) + "\r\n")

    def test_kuru_kosu_yazmaz(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.gitignore(self.tmp.name, True)
        self.assertFalse(os.path.exists(self.yol))

    def test_git_deposu_degilse_dokunmaz(self):
        os.rmdir(os.path.join(self.tmp.name, ".git"))
        self.calistir()
        self.assertFalse(os.path.exists(self.yol))


if __name__ == "__main__":
    unittest.main()
