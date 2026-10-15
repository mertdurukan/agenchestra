"""Kart başına test_koku (G-009): testleri proje dışı bir depoda olan kod kartları için test kapısı.

`py -3.13 -m pytest plugins/orkestra/tests/test_test_koku.py -q`

Geçici bir proje (orkestra durum klasörü) ve ondan AYRI geçici bir test kökü kullanılır; ağ ya da DB yoktur.
Test komutu test kökündeki küçük bir python dosyasıdır: cwd'de `bayrak.txt` varsa 0, yoksa 1 döner. Böylece
komutun test kökünde koştuğu da sınanır.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cekirdek as C  # noqa: E402
import test_calistir_akisi as CA  # noqa: E402

sys.path.insert(0, os.path.join(C.KOK, "scripts"))
import ork_lib as L  # noqa: E402

BETIK = (
    "import os, sys\n"
    "print('kosuldu', os.getcwd())\n"
    "sys.exit(0 if os.path.exists('bayrak.txt') else 1)\n"
)
ANA = dict(ajan_id="ana", ajan_tipi="ana")
ISCI = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t2")
DENETCI = dict(ajan_id="d1", ajan_tipi="orkestra:denetci")


def _yaz(kok, goreli, icerik):
    yol = os.path.join(kok, *goreli.split("/"))
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(icerik)
    return yol


def _sha(yol):
    with open(yol, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TabanTest(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_tkoku_proje_")
        self.dis = tempfile.mkdtemp(prefix="ork_tkoku_dis_")  # proje DIŞI test kökü
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = C.kos([C.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        _yaz(self.dis, "testler/test_a.py", BETIK)
        self.komut = f'"{sys.executable}" testler/test_a.py'
        self.dis_n = os.path.abspath(self.dis).replace("\\", "/")

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.dis, ignore_errors=True)

    def cli(self, *args, ajan_id=None, ajan_tipi=None):
        a = [C.CLI] + list(args)
        if ajan_id:
            a += ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi]
        return C.kos(a, self.proje)

    def kod_karti(self, test_koku=None, sinif="kod", alan="testler/*.py", komut=None):
        a = ["kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "dış test", "--basamak", "T2", "--sinif", sinif, "--kabul", "çalışır",
             "--yazma", "src/**"]
        if sinif == "kod":
            a += ["--test-komutu", komut or self.komut, "--test-alani", alan, "--tdd"]
        if test_koku is not None:
            a += ["--test-koku", test_koku]
        return self.cli(*a)

    def kart(self, gid):
        with open(os.path.join(self.sd, "gorevler", gid + ".json"), encoding="utf-8") as f:
            return json.load(f)

    def kart_sayisi(self):
        d = os.path.join(self.sd, "gorevler")
        return len([x for x in os.listdir(d) if x.endswith(".json") and not x.endswith(".denetim.json")]) \
            if os.path.isdir(d) else 0

    def bayrak(self, kok, var=True):
        yol = os.path.join(kok, "bayrak.txt")
        if var:
            with open(yol, "w") as f:
                f.write("1")
        elif os.path.exists(yol):
            os.remove(yol)

    def kilitli_kart(self):
        r = self.kod_karti(test_koku=self.dis)
        self.assertEqual(r.returncode, 0, r.stderr)
        gid = r.stdout.strip()
        r = self.cli("kart", "test-kos", gid, "--asama", "kirmizi", **ISCI)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return gid


# ---------------------------------------------------------------- 1) alan doğrulama
class AlanDogrulama(TabanTest):
    def test_kart_yeni_mutlak_dizin_saklanir(self):
        r = self.kod_karti(test_koku=self.dis)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kart(r.stdout.strip())["test_koku"], self.dis_n)

    def test_goreli_yol_hata(self):
        os.makedirs(os.path.join(self.proje, "alt"))
        r = self.kod_karti(test_koku="alt")
        self.assertEqual(r.returncode, 2)
        self.assertIn("mutlak", r.stderr)
        self.assertEqual(self.kart_sayisi(), 0)

    def test_olmayan_dizin_hata(self):
        r = self.kod_karti(test_koku=os.path.join(self.dis, "yok_boyle_klasor"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("dizini yok", r.stderr)
        self.assertEqual(self.kart_sayisi(), 0)

    def test_kod_olmayan_kartta_hata(self):
        r = self.kod_karti(test_koku=self.dis, sinif="arastirma")
        self.assertEqual(r.returncode, 2)
        self.assertIn("yalnız kod kartında", r.stderr)

    def test_alansiz_kod_karti_test_koku_tasimaz(self):
        r = self.kod_karti()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("test_koku", self.kart(r.stdout.strip()))

    def test_kart_toplu_json_alani(self):
        plan = [{"soru": "Kısa test sorusu?", "baslik": "a", "basamak": "T2", "sinif": "kod", "tdd": True, "kabul_kriterleri": ["k"], "yazma_alani": ["src/**"],
                 "test_komutu": self.komut, "test_alani": ["testler/*.py"], "test_koku": self.dis}]
        yol = os.path.join(self.proje, "plan.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(plan, f)
        r = self.cli("kart", "toplu", yol)
        self.assertEqual(r.returncode, 0, r.stderr)
        gid = json.loads(r.stdout)[0]["id"]
        self.assertEqual(self.kart(gid)["test_koku"], self.dis_n)

    def test_kart_toplu_gecersiz_kok_hic_kart_olusturmaz(self):
        plan = [{"soru": "Kısa test sorusu?", "baslik": "iyi", "basamak": "T2", "sinif": "belge", "kabul_kriterleri": ["k"]},
                {"soru": "Kısa test sorusu?", "baslik": "kötü", "basamak": "T2", "sinif": "kod", "tdd": True, "kabul_kriterleri": ["k"],
                 "test_komutu": self.komut, "test_alani": ["testler/*.py"], "test_koku": "goreli/yol"}]
        yol = os.path.join(self.proje, "plan.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(plan, f)
        r = self.cli("kart", "toplu", yol)
        self.assertEqual(r.returncode, 2)
        self.assertIn("mutlak", r.stderr)
        self.assertEqual(self.kart_sayisi(), 0)


# ---------------------------------------------------------------- 3) kart_proje_koku (saf işlev)
class KartProjeKoku(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_tkoku_lib_")
        self.proje = os.path.join(self.tmp, "proje")
        self.depo = os.path.join(self.tmp, "depo")
        self.agac = os.path.join(self.tmp, "depo-kart-G-1")
        for d in (self.proje, os.path.join(self.depo, "alt"), self.agac):
            os.makedirs(d)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_test_kokusuz_proje(self):
        self.assertEqual(L.kart_proje_koku(self.proje, {"id": "G-1"}), self.proje)

    def test_test_koku_varsa_o(self):
        k = {"id": "G-1", "test_koku": self.depo}
        self.assertEqual(os.path.normcase(L.kart_proje_koku(self.proje, k)), os.path.normcase(os.path.abspath(self.depo)))

    def test_agac_varsa_test_kokunun_agactaki_karsiligi(self):
        k = {"id": "G-1", "test_koku": os.path.join(self.depo, "alt"),
             "calisma_agaci": {"depo": self.depo, "yol": self.agac}}
        self.assertEqual(os.path.normcase(L.kart_proje_koku(self.proje, k)),
                         os.path.normcase(os.path.abspath(os.path.join(self.agac, "alt"))))
        k["test_koku"] = self.depo
        self.assertEqual(os.path.normcase(L.kart_proje_koku(self.proje, k)), os.path.normcase(os.path.abspath(self.agac)))

    def test_test_koku_agac_deposunda_degilse_valueerror(self):
        k = {"id": "G-1", "test_koku": self.proje, "calisma_agaci": {"depo": self.depo, "yol": self.agac}}
        with self.assertRaises(ValueError) as cm:
            L.kart_proje_koku(self.proje, k)
        self.assertIn("test_koku", str(cm.exception))

    def test_test_koku_dogrula(self):
        self.assertEqual(L.test_koku_dogrula(self.depo), os.path.abspath(self.depo).replace("\\", "/"))
        for kotu in ("", "goreli", os.path.join(self.tmp, "yok"), None):
            with self.assertRaises(ValueError):
                L.test_koku_dogrula(kotu)


# ---------------------------------------------------------------- 3) proje dışı kökte uçtan uca kapı
class DisKokKapi(TabanTest):
    def test_test_kokusuz_kart_dis_testi_bulamaz(self):
        """Sorunun kendisi (geriye uyum): test_koku yokken test_alani proje köküne göredir."""
        r = self.kod_karti()
        gid = r.stdout.strip()
        r = self.cli("kart", "test-kos", gid, "--asama", "kirmizi", **ISCI)
        self.assertEqual(r.returncode, 2)
        self.assertIn("hiçbir proje dosyasına uymuyor", r.stderr)
        self.assertIsNone(self.kart(gid).get("test_kilidi"))

    def test_kirmizi_kilit_yesil_onay(self):
        gid = self.kilitli_kart()
        k = self.kart(gid)
        self.assertEqual(k["test_kilidi"]["dosyalar"],
                         {"testler/test_a.py": _sha(os.path.join(self.dis, "testler", "test_a.py"))})
        self.assertIn(os.path.normcase(os.path.abspath(self.dis)).replace("\\", "/"),
                      os.path.normcase(k["test_kosulari"][-1]["cikti_kuyrugu"]).replace("\\", "/"))  # cwd = test kökü
        self.assertEqual(self.cli("kart", "durum", gid, "isleniyor", **ISCI).returncode, 0)
        self.bayrak(self.dis)  # "kod" yazıldı: test artık geçer (komut test kökünde koşar)
        r = self.cli("kart", "durum", gid, "is-bitti", "--ozet", "bitti", **ISCI)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli("kart", "test-kos", gid, "--asama", "yesil", **ISCI)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GEÇTİ", r.stdout)
        r = self.cli("kart", "denetim", gid, "--karar", "onay", "--gerekce", "tamam", **DENETCI)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("onaylandi", r.stdout)

    def test_onay_kapisi_dis_kokteki_sapmayi_gorur(self):
        gid = self.kilitli_kart()
        self.cli("kart", "durum", gid, "isleniyor", **ISCI)
        self.bayrak(self.dis)
        self.cli("kart", "durum", gid, "is-bitti", **ISCI)
        self.assertEqual(self.cli("kart", "test-kos", gid, "--asama", "yesil", **ISCI).returncode, 0)
        _yaz(self.dis, "testler/test_a.py", BETIK + "# değişti\n")
        r = self.cli("kart", "denetim", gid, "--karar", "onay", "--gerekce", "tamam", **DENETCI)
        self.assertEqual(r.returncode, 3)
        self.assertIn("kilitten saptı", r.stderr)


# ---------------------------------------------------------------- 2) test-ayar
class TestAyar(TabanTest):
    def test_kilit_yokken_serbest_ve_gecmise_yazilir(self):
        r = self.kod_karti()
        gid = r.stdout.strip()
        r = self.cli("kart", "test-ayar", gid, "--test-koku", self.dis, "--test-komutu", "python x.py",
                     "--test-alani", "testler/**", **ANA)
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.kart(gid)
        self.assertEqual((k["test_koku"], k["test_komutu"], k["test_alani"]), (self.dis_n, "python x.py", ["testler/**"]))
        olay = k["gecmis"][-1]
        self.assertEqual(olay["olay"], "test-ayar")
        self.assertEqual(set(olay["degisen"]), {"test_koku", "test_komutu", "test_alani"})
        self.assertIsNone(olay["degisen"]["test_koku"]["eski"])

    def test_yalniz_ana_ajan(self):
        gid = self.kod_karti().stdout.strip()
        r = self.cli("kart", "test-ayar", gid, "--test-koku", self.dis, **ISCI)
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("test_koku", self.kart(gid))

    def test_gecersiz_kok_hata(self):
        gid = self.kod_karti().stdout.strip()
        for kotu in ("goreli", os.path.join(self.dis, "yok")):
            r = self.cli("kart", "test-ayar", gid, "--test-koku", kotu, **ANA)
            self.assertEqual(r.returncode, 2, kotu)
        self.assertNotIn("test_koku", self.kart(gid))

    def test_kilitliyken_test_koku_tutarli_kok_kabul(self):
        gid = self.kilitli_kart()
        yeni = tempfile.mkdtemp(prefix="ork_tkoku_yeni_")
        self.addCleanup(shutil.rmtree, yeni, True)
        shutil.copytree(os.path.join(self.dis, "testler"), os.path.join(yeni, "testler"))
        r = self.cli("kart", "test-ayar", gid, "--test-koku", yeni, **ANA)
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.kart(gid)
        self.assertEqual(k["test_koku"], os.path.abspath(yeni).replace("\\", "/"))
        self.assertEqual(k["gecmis"][-1]["olay"], "test-ayar")
        self.assertTrue(k["test_kilidi"])  # kilit korunur

    def test_kilitliyken_tutarsiz_kok_red(self):
        gid = self.kilitli_kart()
        for degisiklik in ("icerik", "ek_dosya", "bos"):
            yeni = tempfile.mkdtemp(prefix="ork_tkoku_yeni_")
            self.addCleanup(shutil.rmtree, yeni, True)
            if degisiklik != "bos":
                shutil.copytree(os.path.join(self.dis, "testler"), os.path.join(yeni, "testler"))
            if degisiklik == "icerik":
                _yaz(yeni, "testler/test_a.py", BETIK + "# farklı\n")
            elif degisiklik == "ek_dosya":
                _yaz(yeni, "testler/test_b.py", "x = 1\n")
            r = self.cli("kart", "test-ayar", gid, "--test-koku", yeni, **ANA)
            self.assertEqual(r.returncode, 2, degisiklik)
            self.assertIn("kilitle aynı değil", r.stderr)
            self.assertEqual(self.kart(gid)["test_koku"], self.dis_n, degisiklik)

    def test_kok_degisince_eski_kokteki_yesil_onay_kaniti_degil(self):
        """Eski kökte yeşil → test-ayar ile kilit-tutarlı ama kodsuz yeni kök → onay reddedilir; yeni kökte yeşil
        koşulunca (kod/bayrak oraya da gelince) onay geçer."""
        gid = self.kilitli_kart()
        self.cli("kart", "durum", gid, "isleniyor", **ISCI)
        self.bayrak(self.dis)
        self.cli("kart", "durum", gid, "is-bitti", **ISCI)
        self.assertEqual(self.cli("kart", "test-kos", gid, "--asama", "yesil", **ISCI).returncode, 0)
        self.assertEqual(os.path.normcase(self.kart(gid)["test_kosulari"][-1].get("kok") or ""),
                         os.path.normcase(self.dis_n))
        yeni = tempfile.mkdtemp(prefix="ork_tkoku_yeni_")
        self.addCleanup(shutil.rmtree, yeni, True)
        shutil.copytree(os.path.join(self.dis, "testler"), os.path.join(yeni, "testler"))  # bayrak yok: burada FAIL eder
        r = self.cli("kart", "test-ayar", gid, "--test-koku", yeni, **ANA)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli("kart", "denetim", gid, "--karar", "onay", "--gerekce", "x", **DENETCI)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("test kökü", r.stderr)
        r = self.cli("kart", "test-kos", gid, "--asama", "yesil", **ISCI)
        self.assertEqual(r.returncode, 4, r.stdout)  # yeni kökte kod yok: yeşil geçmez
        self.assertNotEqual(self.cli("kart", "denetim", gid, "--karar", "onay", "--gerekce", "x", **DENETCI).returncode, 0)
        self.bayrak(yeni)
        self.assertEqual(self.cli("kart", "test-kos", gid, "--asama", "yesil", **ISCI).returncode, 0)
        r = self.cli("kart", "denetim", gid, "--karar", "onay", "--gerekce", "x", **DENETCI)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("onaylandi", r.stdout)

    def test_kilitliyken_komut_ve_alan_degismez(self):
        gid = self.kilitli_kart()
        for arg in (["--test-komutu", "python y.py"], ["--test-alani", "testler/**"]):
            r = self.cli("kart", "test-ayar", gid, *arg, **ANA)
            self.assertEqual(r.returncode, 2, arg)
            self.assertIn("yalnız test_koku", r.stderr)
        k = self.kart(gid)
        self.assertEqual((k["test_komutu"], k["test_alani"]), (self.komut, ["testler/*.py"]))
        self.assertNotEqual(k["gecmis"][-1]["olay"], "test-ayar")


# ---------------------------------------------------------------- 4) hook
class HookTestKoku(TabanTest):
    def setUp(self):
        super().setUp()
        self.tdir = os.path.join(self.proje, "_transkript")
        os.makedirs(os.path.join(self.tdir, C.OTURUM, "subagents"))
        self.ana_tr = os.path.join(self.tdir, C.OTURUM + ".jsonl")
        open(self.ana_tr, "w").close()

    def hook(self, girdi):
        g = {"session_id": C.OTURUM, "cwd": self.proje, "transcript_path": self.ana_tr, "hook_event_name": "PreToolUse"}
        g.update(girdi)
        r = C.kos([C.HOOK, "PreToolUse"], self.proje, stdin=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def karar(self, c):
        return (c.get("hookSpecificOutput") or {}).get("permissionDecision")

    def neden(self, c):
        return (c.get("hookSpecificOutput") or {}).get("permissionDecisionReason") or ""

    def ajan(self, aid, gorev, surec):
        os.makedirs(os.path.join(self.sd, "oturumlar"), exist_ok=True)
        with open(os.path.join(self.sd, "oturumlar", f"ajan_{aid}.json"), "w", encoding="utf-8") as f:
            json.dump({"gorev": gorev, "surec": surec, "ajan": "orkestra:isci-t2"}, f)

    def yaz(self, tam, arac="Write", **ek):
        return self.hook(dict({"tool_name": arac, "tool_input": {"file_path": tam, "content": "x"}}, **ek))

    def test_kilitli_dis_test_herkese_kapali(self):
        gid = self.kilitli_kart()
        hedef = os.path.join(self.dis, "testler", "test_a.py")
        for arac in ("Write", "Edit", "MultiEdit"):
            c = self.yaz(hedef, arac)  # ana ajan
            self.assertEqual(self.karar(c), "deny", arac)
            self.assertIn("kilitli test", self.neden(c))
        self.ajan("w9", gid, "test-yaz")
        c = self.yaz(hedef, agent_id="w9", agent_type="orkestra:test-yazari")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("kilitli test", self.neden(c))

    def test_dis_kilit_proje_icindeki_ayni_goreli_yolu_kilitlemez(self):
        self.kilitli_kart()
        c = self.yaz(os.path.join(self.proje, "testler", "test_a.py"))
        self.assertNotEqual(self.karar(c), "deny", self.neden(c))

    def test_test_yaz_disi_ajan_dis_test_alanina_yazamaz(self):
        gid = self.kod_karti(test_koku=self.dis).stdout.strip()
        self.ajan("w1", gid, "is")
        c = self.yaz(os.path.join(self.dis, "testler", "test_yeni.py"), agent_id="w1", agent_type="orkestra:isci-t2")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("yalnız #SUREC:test-yaz", self.neden(c))

    def test_test_yaz_dis_test_alanina_yazar_disina_yazamaz(self):
        gid = self.kod_karti(test_koku=self.dis).stdout.strip()
        self.ajan("t1", gid, "test-yaz")
        c = self.yaz(os.path.join(self.dis, "testler", "test_yeni.py"), agent_id="t1", agent_type="orkestra:test-yazari")
        self.assertNotEqual(self.karar(c), "deny", self.neden(c))
        c = self.yaz(os.path.join(self.dis, "src", "x.py"), agent_id="t1", agent_type="orkestra:test-yazari")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("yalnız test_alani içine", self.neden(c))

    def test_test_kokusuz_kart_geriye_uyumlu(self):
        r = C.kos([C.CLI, "kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "eski", "--basamak", "T2", "--kabul", "k", "--sinif", "kod", "--tdd",
                   "--test-komutu", "python -m unittest", "--test-alani", "testler/**", "--yazma", "src/**"], self.proje)
        gid = r.stdout.strip()
        yol = os.path.join(self.sd, "gorevler", gid + ".json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        k["test_kilidi"] = {"zaman": "2026-10-13T10:00:00+03:00", "dosyalar": {"testler/test_a.py": "0" * 64}}
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)
        c = self.yaz(os.path.join(self.proje, "testler", "test_a.py"))
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("kilitli test", self.neden(c))
        c = self.yaz(os.path.join(self.dis, "testler", "test_a.py"))  # proje dışındaki aynı ad kilitli değil
        self.assertNotEqual(self.karar(c), "deny", self.neden(c))
        self.ajan("w2", gid, "is")
        c = self.yaz(os.path.join(self.proje, "testler", "test_b.py"), agent_id="w2", agent_type="orkestra:isci-t2")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("yalnız #SUREC:test-yaz", self.neden(c))
        c = self.yaz(os.path.join(self.dis, "testler", "test_b.py"), agent_id="w2", agent_type="orkestra:isci-t2")
        self.assertNotIn("test-yaz", self.neden(c))

    def test_dis_kok_yol_varyantlari(self):
        """Kök ve hedef yolu büyük/küçük harf ve ters bölü/düz bölü varyantlarıyla verilse de kural aynı çalışır."""
        if os.name != "nt":
            self.skipTest("büyük/küçük harf duyarsız yol yalnız Windows'ta")
        kok_varyant = os.path.abspath(self.dis).upper().replace("/", "\\")
        r = self.kod_karti(test_koku=kok_varyant)
        self.assertEqual(r.returncode, 0, r.stderr)
        gid = r.stdout.strip()
        self.assertEqual(self.cli("kart", "test-kos", gid, "--asama", "kirmizi", **ISCI).returncode, 0)
        for hedef in (os.path.join(self.dis, "testler", "test_a.py").lower().replace("\\", "/"),
                      os.path.join(self.dis, "TESTLER", "TEST_A.PY").replace("/", "\\")):
            c = self.yaz(hedef)
            self.assertEqual(self.karar(c), "deny", hedef)
            self.assertIn("kilitli test", self.neden(c))
        self.ajan("w5", gid, "is")
        for hedef in (os.path.join(self.dis, "testler", "test_yeni.py").upper(),
                      os.path.join(self.dis, "testler", "test_yeni.py").replace("\\", "/").lower()):
            c = self.yaz(hedef, agent_id="w5", agent_type="orkestra:isci-t2")
            self.assertEqual(self.karar(c), "deny", hedef)
            self.assertIn("yalnız #SUREC:test-yaz", self.neden(c))

    def test_test_ayar_tek_basina_calistirilir(self):
        c = self.hook({"tool_name": "Bash", "tool_input": {"command": f"orkestra kart test-ayar G-001 --test-koku {self.dis_n}; echo x"}})
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("tek başına", self.neden(c))
        c = self.hook({"tool_name": "Bash", "tool_input": {"command": f"orkestra kart test-ayar G-001 --test-koku {self.dis_n}"}})
        self.assertEqual(self.karar(c), "allow")
        self.assertIn("--ajan-tipi ana", c["hookSpecificOutput"]["updatedInput"]["command"])


# ---------------------------------------------------------------- birleştirme kilit kapısı (dış depo)
def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class BirlestirmeKilidiDisDepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_tkoku_git_")
        self.proje = os.path.join(self.tmp, "proje")
        self.depo = os.path.join(self.tmp, "depo")
        os.makedirs(self.proje)
        os.makedirs(self.depo)
        _git(self.depo, "init", "-q", "-b", "main")
        _git(self.depo, "config", "user.name", "t")
        _git(self.depo, "config", "user.email", "test@example.invalid")
        _git(self.depo, "config", "core.autocrlf", "false")
        self.test_yol = _yaz(self.depo, "testler/test_a.py", BETIK)
        _git(self.depo, "add", "-A")
        _git(self.depo, "commit", "-q", "-m", "ilk")
        self.taban = _git(self.depo, "rev-parse", "HEAD")
        self.agac = self.depo + "-kart-G-1"
        _git(self.depo, "worktree", "add", "-q", "-b", "kart/G-1", self.agac, self.taban)
        self.kart = {"id": "G-1", "sinif": "kod", "durum": "isleniyor", "test_koku": self.depo,
                     "test_alani": ["testler/*.py"],
                     "test_kilidi": {"zaman": "-", "dosyalar": {"testler/test_a.py": _sha(self.test_yol)}},
                     "calisma_agaci": {"depo": self.depo, "yol": self.agac, "dal": "kart/G-1", "taban": self.taban}}

    def tearDown(self):
        subprocess.run(["git", "-C", self.depo, "worktree", "remove", "--force", self.agac], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.agac, ignore_errors=True)

    def test_dis_depodaki_kilitli_testi_degistiren_dal_kilit_verir(self):
        _yaz(self.agac, "testler/test_a.py", BETIK + "# dalda değişti\n")
        _git(self.agac, "commit", "-q", "-am", "test değişti")
        ihlaller, hata = L.birlestirme_kilit_ihlalleri(self.proje, self.kart, [])
        self.assertIsNone(hata)
        self.assertEqual(ihlaller, [("testler/test_a.py", "G-1", "değişmiş")])
        s = L.kart_agaci_birlestir(self.kart, proje=self.proje, ks=[])
        self.assertEqual(s["sonuc"], "kilit", s["mesaj"])

    def test_kilitli_teste_dokunmayan_dal_ihlal_vermez(self):
        _yaz(self.agac, "src/kod.py", "x = 1\n")
        _git(self.agac, "add", "-A")
        _git(self.agac, "commit", "-q", "-m", "kod")
        self.assertEqual(L.birlestirme_kilit_ihlalleri(self.proje, self.kart, []), ([], None))


# ---------------------------------------------------------------- 5) calistir.js istemleri
@unittest.skipUnless(CA.NODE, CA.NODE_YOK_GEREKCE)
class CalistirIstemi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_tkoku_js_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(CA.KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def istemler(self, kart):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"gorevler": [kart]}, f, ensure_ascii=False)
        p = subprocess.run([CA.NODE, self.kosum, CA.BETIK, yol], capture_output=True,
                           env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"), timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        c = [x for x in json.loads(p.stdout.decode("utf-8"))["cagrilar"] if x["phase"] != "Ön kontrol"]
        return {x["agentType"]: x["istem"] for x in reversed(c)}

    def test_test_koku_istemde_gorunur(self):
        ist = self.istemler(CA.kod_karti(test_koku="C:/dis/depo"))
        self.assertIn("Test kökü", ist["orkestra:test-yazari"])
        self.assertIn("C:/dis/depo", ist["orkestra:test-yazari"])
        self.assertIn("C:/dis/depo", ist["orkestra:isci-t2"])

    def test_test_koku_yoksa_proje(self):
        ist = self.istemler(CA.kod_karti())
        self.assertIn("Test kökü (test komutu burada koşar, test alanı buna göredir): proje kökü",
                      ist["orkestra:test-yazari"])
        self.assertIn("proje kökü", ist["orkestra:isci-t2"])


if __name__ == "__main__":
    unittest.main()
