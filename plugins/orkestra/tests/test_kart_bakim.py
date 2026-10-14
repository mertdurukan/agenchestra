"""G-012: kart bakımı. `py -3.13 -m pytest plugins/orkestra/tests/test_kart_bakim.py -q`

1) ork_lib.kartlar() yalnız G-<sayı>.json kart dosyalarını okur (yan dosya ve bozuk kayıtlar atlanır);
   `kart toplu` ve ozet.yaz bu durumda çökmez.
2) niyet: ana ajan kimliği yazabilir, gerçek alt ajan reddedilir, kimlik yokken eski davranış.
3) kart test-ayar --test-alani: test dosyaları kartın yazma_alani listesine de eklenir (tekrarsız).

Gerçek ~/.claude/orkestra-panel verisine dokunmaz (niyet.NIYET_YOLU/GENEL_DIZIN geçici dizine yönlendirilir).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cekirdek as C  # noqa: E402

sys.path.insert(0, os.path.join(C.KOK, "scripts"))
import ork_lib as L  # noqa: E402
import niyet  # noqa: E402
import ozet  # noqa: E402

ANA = dict(ajan_id="ana", ajan_tipi="ana")
PROJE_DENEME = "C:/proje_deneme"  # Temp altında olmamalı (niyet._gecici süzer)


def _json_yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        if isinstance(veri, str):
            f.write(veri)
        else:
            json.dump(veri, f)


# ---------------------------------------------------------------- 1) kartlar() süzgeci
class KartlarSuzgeci(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_kbakim_sd_")
        self.g = os.path.join(self.sd, "gorevler")

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def kirlet(self):
        _json_yaz(os.path.join(self.g, "G-001.json"), {"id": "G-001", "baslik": "gerçek kart"})
        _json_yaz(os.path.join(self.g, "G-002.onkontrol.json"), {"gecti": True, "sorunlar": []})
        _json_yaz(os.path.join(self.g, "G-003.denetim.json"), {"kararlar": []})
        _json_yaz(os.path.join(self.g, "G-004.json"), "{bozuk json")
        _json_yaz(os.path.join(self.g, "G-005.json"), {"baslik": "id yok"})
        _json_yaz(os.path.join(self.g, ".tmp_G-006.json"), {"id": "G-006"})
        _json_yaz(os.path.join(self.g, "notlar.json"), {"id": "X-1"})

    def test_yalniz_kart_dosyalari_doner(self):
        self.kirlet()
        self.assertEqual([k["id"] for k in L.kartlar(self.sd)], ["G-001"])

    def test_onkontrol_dosyasi_tek_basina_kart_sayilmaz(self):
        _json_yaz(os.path.join(self.g, "G-002.onkontrol.json"), {"gecti": False})
        self.assertEqual(L.kartlar(self.sd), [])

    def test_bos_ve_olmayan_klasor(self):
        self.assertEqual(L.kartlar(self.sd), [])  # gorevler/ yok
        os.makedirs(self.g)
        self.assertEqual(L.kartlar(self.sd), [])

    def test_birden_cok_gercek_kart_sirali(self):
        self.kirlet()
        _json_yaz(os.path.join(self.g, "G-010.json"), {"id": "G-010"})
        _json_yaz(os.path.join(self.g, "G-002.json"), {"id": "G-002"})
        self.assertEqual([k["id"] for k in L.kartlar(self.sd)], ["G-001", "G-002", "G-010"])

    def test_ozet_yaz_yan_dosyalarla_cokmez(self):
        self.kirlet()
        o = ozet.yaz(self.sd, self.sd)
        self.assertIsNotNone(o, "ozet.yaz None döndü (hata yutuldu)")
        self.assertTrue(os.path.exists(os.path.join(self.sd, "ozet.json")))
        self.assertFalse(os.path.exists(os.path.join(self.sd, "ozet_hata.txt")))


class KartTopluYanDosya(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kbakim_proje_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = C.kos([C.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def test_kart_toplu_onkontrol_dosyasi_varken_calisir(self):
        g = os.path.join(self.sd, "gorevler")
        _json_yaz(os.path.join(g, "G-900.onkontrol.json"), {"gecti": True})
        _json_yaz(os.path.join(g, "G-901.json"), "{bozuk")
        plan = os.path.join(self.proje, "plan.json")
        _json_yaz(plan, [{"baslik": "a", "basamak": "T2", "kabul_kriterleri": ["k"]}])
        r = C.kos([C.CLI, "kart", "toplu", plan], self.proje)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("KeyError", r.stderr)
        self.assertEqual(len(json.loads(r.stdout)), 1)


# ---------------------------------------------------------------- 2) niyet ana ajan kimliği
class NiyetAnaAjan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_kbakim_niyet_")
        self.yol = os.path.join(self.tmp, "niyet.jsonl")
        for ad, deger in (("NIYET_YOLU", self.yol), ("GENEL_DIZIN", self.tmp)):
            p = mock.patch.object(niyet, ad, deger)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(niyet, "_oturum_projesi", return_value=PROJE_DENEME)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def ns(self, **ek):
        d = dict(ne=None, neden=None, sonuc=None, baglam=None, oturum="oturum-1", goster=False)
        d.update(ek)
        return argparse.Namespace(**d)

    def kayitlar(self):
        if not os.path.exists(self.yol):
            return []
        with open(self.yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def test_ana_ajan_ne_neden_yazar(self):
        niyet.cmd(self.ns(ne="kart bakımı", neden="panel çökmesin", ajan_id="ana", ajan_tipi="ana"))
        k = self.kayitlar()
        self.assertEqual([x["tur"] for x in k], ["niyet"])
        self.assertEqual((k[0]["ne"], k[0]["neden"]), ("kart bakımı", "panel çökmesin"))

    def test_ana_ajan_sonuc_yazar(self):
        niyet.cmd(self.ns(sonuc="bitti", ajan_id="ana", ajan_tipi="ana"))
        k = self.kayitlar()
        self.assertEqual([x["tur"] for x in k], ["sonuc"])
        self.assertEqual(k[0]["sonuc"], "bitti")

    def test_yalniz_ajan_tipi_ana_yeter(self):
        niyet.cmd(self.ns(ne="x", neden="y", ajan_id="a1", ajan_tipi="ana"))
        self.assertEqual(len(self.kayitlar()), 1)

    def test_yalniz_ajan_id_ana_yeter(self):
        niyet.cmd(self.ns(ne="x", neden="y", ajan_id="ana", ajan_tipi=None))
        self.assertEqual(len(self.kayitlar()), 1)

    def test_gercek_alt_ajan_reddedilir(self):
        for tip in ("orkestra:isci-t2", "orkestra:denetci", "orkestra:test-yazari"):
            with self.assertRaises(SystemExit) as cm:
                niyet.cmd(self.ns(ne="x", neden="y", ajan_id="a123", ajan_tipi=tip))
            self.assertIn("yalnız ana ajan", str(cm.exception.code), tip)
        self.assertEqual(self.kayitlar(), [])

    def test_alt_ajan_sonuc_da_yazamaz(self):
        with self.assertRaises(SystemExit):
            niyet.cmd(self.ns(sonuc="bitti", ajan_id="a123", ajan_tipi="orkestra:isci-t2"))
        self.assertEqual(self.kayitlar(), [])

    def test_kimliksiz_eski_davranis(self):
        niyet.cmd(self.ns(ne="x", neden="y", ajan_id=None, ajan_tipi=None))
        self.assertEqual(len(self.kayitlar()), 1)
        niyet.cmd(self.ns(ne="x", neden="y"))  # öznitelikler hiç yok
        self.assertEqual(len(self.kayitlar()), 2)

    def test_ana_ajan_ne_neden_eksik_hata(self):
        with self.assertRaises(SystemExit) as cm:
            niyet.cmd(self.ns(ne="yalnız ne", ajan_id="ana", ajan_tipi="ana"))
        self.assertIn("birlikte", str(cm.exception.code))
        self.assertEqual(self.kayitlar(), [])


# ---------------------------------------------------------------- 3) test-ayar yazma alanı
class TestAyarYazmaAlani(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kbakim_ta_")
        self.dis = tempfile.mkdtemp(prefix="ork_kbakim_dis_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        self.dis_n = os.path.abspath(self.dis).replace("\\", "/")
        r = C.kos([C.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.dis, ignore_errors=True)

    def cli(self, *args):
        return C.kos([C.CLI] + list(args) + ["--ajan-id", "ana", "--ajan-tipi", "ana"], self.proje)

    def kart_ac(self, test_koku=None):
        a = ["kart", "yeni", "--baslik", "t", "--basamak", "T2", "--sinif", "kod", "--kabul", "k", "--yazma", "src/**",
             "--test-komutu", "python x.py", "--test-alani", "eski/*.py"]
        if test_koku:
            a += ["--test-koku", test_koku]
        r = C.kos([C.CLI] + a, self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def kart(self, gid):
        with open(os.path.join(self.sd, "gorevler", gid + ".json"), encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _n(s):
        return os.path.normcase(s).replace("\\", "/")

    def test_test_koku_varsa_mutlak_yol_eklenir(self):
        gid = self.kart_ac(test_koku=self.dis)
        r = self.cli("kart", "test-ayar", gid, "--test-alani", "testler/yeni_*.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        ya = [self._n(x) for x in self.kart(gid)["yazma_alani"]]
        self.assertIn(self._n(self.dis_n + "/testler/yeni_*.py"), ya)
        self.assertIn("src/**", self.kart(gid)["yazma_alani"])  # mevcut alan korunur

    def test_test_koku_yoksa_proje_goreli_eklenir(self):
        gid = self.kart_ac()
        r = self.cli("kart", "test-ayar", gid, "--test-alani", "testler/yeni_*.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        ya = self.kart(gid)["yazma_alani"]
        self.assertIn("testler/yeni_*.py", ya)
        self.assertIn("src/**", ya)

    def test_ikinci_cagri_tekrar_eklemez(self):
        gid = self.kart_ac(test_koku=self.dis)
        for _ in range(2):
            r = self.cli("kart", "test-ayar", gid, "--test-alani", "testler/yeni_*.py")
            self.assertEqual(r.returncode, 0, r.stderr)
        hedef = self._n(self.dis_n + "/testler/yeni_*.py")
        self.assertEqual([x for x in self.kart(gid)["yazma_alani"] if self._n(x) == hedef].__len__(), 1)

    def test_goreli_ikinci_cagri_tekrar_eklemez(self):
        gid = self.kart_ac()
        for _ in range(2):
            self.assertEqual(self.cli("kart", "test-ayar", gid, "--test-alani", "testler/yeni_*.py").returncode, 0)
        self.assertEqual(self.kart(gid)["yazma_alani"].count("testler/yeni_*.py"), 1)

    def test_test_alani_verilmezse_yazma_alani_degismez(self):
        gid = self.kart_ac(test_koku=self.dis)
        once = list(self.kart(gid)["yazma_alani"])
        r = self.cli("kart", "test-ayar", gid, "--test-komutu", "python y.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kart(gid)["yazma_alani"], once)


# ---------------------------------------------------------------- 3b) kilitli kartta test-ayar yazma alanı
class KilitliTestAyar(unittest.TestCase):
    BETIK = "import sys\nsys.exit(1)\n"  # kırmızı: her zaman başarısız

    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kbakim_kl_")
        self.dis = tempfile.mkdtemp(prefix="ork_kbakim_kldis_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        self.dis_n = os.path.abspath(self.dis).replace("\\", "/")
        self.komut = f'"{sys.executable}" testler/test_a.py'
        r = C.kos([C.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.dis, ignore_errors=True)

    def cli(self, *args, ajan_id="ana", ajan_tipi="ana"):
        return C.kos([C.CLI] + list(args) + ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi], self.proje)

    def kart(self, gid):
        with open(os.path.join(self.sd, "gorevler", gid + ".json"), encoding="utf-8") as f:
            return json.load(f)

    def kilitli_kart(self, test_koku):
        kok = self.dis if test_koku else self.proje
        _json_yaz(os.path.join(kok, "testler", "test_a.py"), self.BETIK)
        a = ["kart", "yeni", "--baslik", "t", "--basamak", "T2", "--sinif", "kod", "--kabul", "k", "--yazma", "src/**",
             "--test-komutu", self.komut, "--test-alani", "testler/*.py"]
        if test_koku:
            a += ["--test-koku", self.dis]
        r = C.kos([C.CLI] + a, self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        gid = r.stdout.strip()
        r = self.cli("kart", "test-kos", gid, "--asama", "kirmizi", ajan_id="w1", ajan_tipi="orkestra:isci-t2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.kart(gid)
        self.assertTrue(k["test_kilidi"])
        return gid, k

    def _kontrol(self, test_koku, beklenen):
        gid, once = self.kilitli_kart(test_koku)
        self.assertNotIn(beklenen, once["yazma_alani"])
        r = self.cli("kart", "test-ayar", gid, "--test-alani", "testler/*.py")
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("KeyError", r.stderr)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.kart(gid)
        self.assertIn(beklenen, [x.replace("\\", "/") for x in k["yazma_alani"]])
        self.assertIn("src/**", k["yazma_alani"])
        self.assertEqual(k["test_alani"], once["test_alani"])
        self.assertEqual(k["test_kilidi"], once["test_kilidi"])
        self.assertEqual(k.get("test_koku"), once.get("test_koku"))
        r = self.cli("kart", "test-ayar", gid, "--test-alani", "testler/*.py")  # tekrar: eklemez
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([x.replace("\\", "/") for x in self.kart(gid)["yazma_alani"]].count(beklenen), 1)

    def test_kilitli_test_koku_ile_ayni_alan_yazma_alanina_eklenir(self):
        self._kontrol(True, self.dis_n + "/testler/*.py")

    def test_kilitli_test_kokusuz_ayni_alan_yazma_alanina_eklenir(self):
        self._kontrol(False, "testler/*.py")

    def test_kilitliyken_farkli_alan_reddedilir(self):
        for koklu in (True, False):
            gid, once = self.kilitli_kart(koklu)
            r = self.cli("kart", "test-ayar", gid, "--test-alani", "baska/**")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("yalnız test_koku", r.stderr)
            self.assertEqual(self.kart(gid)["test_alani"], once["test_alani"])
            shutil.rmtree(os.path.join(self.proje, ".claude"), ignore_errors=True)
            self.assertEqual(C.kos([C.CLI, "baslat"], self.proje).returncode, 0)


if __name__ == "__main__":
    unittest.main()
