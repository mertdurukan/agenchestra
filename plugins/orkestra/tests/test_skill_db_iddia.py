"""db-olcum ve iddia-dogrula skill'leri: proje adı taşımaz, ayar (eklenti varsayılanı + proje ezmesi) ile çalışır."""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.abspath(os.path.join(AD, ".."))
DB = os.path.join(KOK, "skills", "db-olcum", "scripts")
ID = os.path.join(KOK, "skills", "iddia-dogrula", "scripts")


def yukle(yol, ad):
    spec = importlib.util.spec_from_file_location(ad, yol)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(metin)


class ProjeAdiYok(unittest.TestCase):
    def test_skill_ve_ayar_dosyalarinda_proje_adi_yok(self):
        rx = re.compile(r"klibre|Boyner|RNV|McD")
        bulunan = []
        yollar = [os.path.join(KOK, "ayarlar", a) for a in ("db_olcum.json", "iddia_dogrula.json")]
        for kok in (os.path.join(KOK, "skills", "db-olcum"), os.path.join(KOK, "skills", "iddia-dogrula")):
            for dp, dn, fn in os.walk(kok):
                dn[:] = [d for d in dn if d != "__pycache__"]
                yollar += [os.path.join(dp, f) for f in fn]
        for y in yollar:
            with open(y, encoding="utf-8") as f:
                if rx.search(f.read()):
                    bulunan.append(os.path.relpath(y, KOK))
        self.assertEqual(bulunan, [])

    def test_ayar_dosyalari_gecerli_json(self):
        for a in ("db_olcum.json", "iddia_dogrula.json"):
            with open(os.path.join(KOK, "ayarlar", a), encoding="utf-8") as f:
                self.assertIsInstance(json.load(f), dict)


class Kapi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = yukle(os.path.join(DB, "kapi.py"), "kapi_test")

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = self.t.name
        self.k.PROJE = self.proje
        self.k.sonuclar.clear()

    def tearDown(self):
        self.t.cleanup()

    def ezme(self, d):
        yaz(os.path.join(self.proje, ".claude", "orkestra", "db_olcum.json"), json.dumps(d))
        self.k.AYAR = self.k.ayar_oku(self.proje)

    def test_varsayilan_ayar_yasak_saat_yok(self):
        self.k.AYAR = self.k.ayar_oku(self.proje)
        import datetime
        d, _ = self.k.pencere_uygun("kopya", datetime.time(18, 0))
        self.assertEqual(d, "GEÇTİ")

    def test_proje_ezmesi_yasak_saat_uygular_ve_ortamlar_birlesir(self):
        import datetime
        self.ezme({"ortamlar": {"kopya": {"host": "h.example", "yasak_saatler": [["17:15", "23:15"]]}}})
        self.assertEqual(self.k.AYAR["ortamlar"]["kopya"]["port"], 5432)   # varsayılan port korunur
        self.assertIn("prod", self.k.AYAR["ortamlar"])                       # ezilmeyen ortam durur
        self.assertEqual(self.k.pencere_uygun("kopya", datetime.time(18, 0))[0], "KALDI")
        self.assertEqual(self.k.pencere_uygun("kopya", datetime.time(17, 14))[0], "GEÇTİ")
        self.assertEqual(self.k.pencere_uygun("kopya", datetime.time(23, 15))[0], "GEÇTİ")

    def test_gece_yarisini_asan_aralik(self):
        import datetime
        self.ezme({"ortamlar": {"kopya": {"yasak_saatler": [["22:00", "02:00"]]}}})
        self.assertEqual(self.k.pencere_uygun("kopya", datetime.time(23, 30))[0], "KALDI")
        self.assertEqual(self.k.pencere_uygun("kopya", datetime.time(1, 0))[0], "KALDI")
        self.assertEqual(self.k.pencere_uygun("kopya", datetime.time(12, 0))[0], "GEÇTİ")

    def test_prod_agir_sorgu_mesai_uyarisi(self):
        import datetime
        self.k.AYAR = self.k.ayar_oku(self.proje)
        self.assertEqual(self.k.pencere_uygun("prod", datetime.time(10, 0), "agir", True)[0], "UYARI")
        self.assertEqual(self.k.pencere_uygun("prod", datetime.time(10, 0), "hafif", True)[0], "GEÇTİ")
        self.assertEqual(self.k.pencere_uygun("prod", datetime.time(10, 0), "agir", False)[0], "GEÇTİ")

    def test_sql_yasak_komut_ve_kolon_ezmesi(self):
        self.ezme({"yasak_kolon_kaliplari": ["gizli_kolon"]})
        self.assertIsNotNone(self.k.yasak_kontrol("delete from t"))
        self.assertIsNone(self.k.yasak_kontrol("select 1 as 'Residue Update 0'"))   # tırnak içi metin komut sayılmaz
        self.assertEqual(self.k.yasak_kontrol("select gizli_kolon from t"), "gizli_kolon")
        self.assertEqual(self.k.yasak_kontrol("select password from t"), None)   # ezme varsayılan kolon listesini değiştirir

    def test_kimlik_dosyasi_projede_ise_kalir(self):
        self.k.AYAR = self.k.ayar_oku(self.proje)
        yaz(os.path.join(self.proje, "alt", "db.py"), "x = 1\n")
        self.k.db_py_kontrol(None)
        self.assertIn("KALDI", self.k.sonuclar)


class Iskelet(unittest.TestCase):
    def kos(self, proje, *arg):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=proje, PYTHONUTF8="1")
        return subprocess.run([sys.executable, "-I", os.path.join(DB, "iskelet.py"), *arg],
                              capture_output=True, text=True, encoding="utf-8", env=env)

    def test_senkron_hesabi_ayardaysa_betige_girer_degilse_girmez(self):
        with tempfile.TemporaryDirectory() as t:
            r = self.kos(t, "--klasor", os.path.join(t, "o"), "--ad", "v1_a", "--soru", "s")
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(t, "o", "v1_a.py"), encoding="utf-8") as f:
                self.assertNotIn("pg_stat_activity", f.read())
            yaz(os.path.join(t, ".claude", "orkestra", "db_olcum.json"), json.dumps({"senkron_kullanici": "esitleyici_hesap"}))
            r = self.kos(t, "--klasor", os.path.join(t, "o"), "--ad", "v2_b", "--soru", "s")
            self.assertEqual(r.returncode, 0, r.stderr)
            metin = open(os.path.join(t, "o", "v2_b.py"), encoding="utf-8").read()
            self.assertIn("usename = 'esitleyici_hesap'", metin)
            compile(metin, "v2_b.py", "exec")   # üretilen betik geçerli Python

    def test_var_olan_dosyanin_ustune_yazmaz(self):
        with tempfile.TemporaryDirectory() as t:
            self.kos(t, "--klasor", t, "--ad", "v1_a", "--soru", "s")
            r = self.kos(t, "--klasor", t, "--ad", "v1_a", "--soru", "s")
            self.assertNotEqual(r.returncode, 0)


class Rapor(unittest.TestCase):
    def kos(self, proje, *arg):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=proje, PYTHONUTF8="1")
        return subprocess.run([sys.executable, "-I", os.path.join(ID, "rapor.py"), *arg],
                              capture_output=True, text=True, encoding="utf-8", env=env)

    def test_ayar_proje_ezmesi_yerine_gecer(self):
        with tempfile.TemporaryDirectory() as t:
            r = self.kos(t, "ayar")
            self.assertEqual(json.loads(r.stdout)["rapor_dizini"], "calisma/dogrulama")
            yaz(os.path.join(t, ".claude", "orkestra", "iddia_dogrula.json"), json.dumps({"rapor_dizini": "belgeler/dogrulama"}))
            d = json.loads(self.kos(t, "ayar").stdout)
            self.assertEqual(d["rapor_dizini"], "belgeler/dogrulama")
            self.assertEqual(d["calisma_dizini"], "calisma")

    def test_iskelet_sonra_denetle_yer_tutucuda_kalir_doldurulunca_gecer(self):
        with tempfile.TemporaryDirectory() as t:
            liste = os.path.join(t, "iddialar.csv")
            yaz(liste, "kid;iddia\nK001;Birinci\n")
            rapor, kanit = os.path.join(t, "r.md"), os.path.join(t, "kanit")
            self.assertEqual(self.kos(t, "iskelet", liste, "--rapor", rapor, "--kanit", kanit).returncode, 0)
            self.assertEqual(self.kos(t, "denetle", rapor, "--iddialar", liste).returncode, 1)
            yaz(rapor, "# R\n\n## Özet tablo\n\n| KID | Karar | Önerilen yeni metin |\n|---|---|---|\n| K001 | DOĞRULANDI | — |\n\n"
                       "## Kanıtlar\n\n### K001 — birinci\n- **İddia:** Birinci\n- kod `a/b.py:12` gösteriyor\n\n## Açık kalanlar\n- yok\n")
            r = self.kos(t, "denetle", rapor, "--iddialar", liste)
            self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
