"""I-083 P1: bayatlık uyarısı yalnız guncelle'nin kopyaladığı dosya kümesindeki gerçek farkta ya da GitHub main ilerideyken çıkar.

Sözleşme:
- cursor_kur.kopyalanir(goreli: str) -> bool: tek dahil/hariç yüklemi; cursor_kur.dosyalar onu kullanır.
- ork_lib.bayatlik(calisan, kaynak_depo): yalnız kaynakta olan, kopyalanan dosyaları sayar; CRLF yok sayılır; alt süreç açmaz.
- oturum_bakim.surum_adimi(sd: str) -> dict | None: guncelle.kontrol sonucu; günde en çok bir getir=True denemesi
  (damga: sd/SURUM_DAMGA dosyasının mtime'ı, her denemede yazılır); SURUM_ZAMAN_ASIMI_SN (30) aşılırsa None.
  _adimlar listesinin son adımı ("surum", ...).
- hook.guncellik_satirlari(onbellek: dict) -> list[str]: bakım önbelleğinden uyarı satırları; ağ/alt süreç yok.
`python -m pytest tests/test_bayatlik_kume.py -q`
"""
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import cursor_kur  # noqa: E402
import guncelle  # noqa: E402
import hook  # noqa: E402
import ork_lib as L  # noqa: E402
import oturum_bakim  # noqa: E402


def _yaz(yol, icerik: bytes):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "wb") as f:
        f.write(icerik)


def _getir_degeri(cagri) -> bool:
    if "getir" in cagri.kwargs:
        return bool(cagri.kwargs["getir"])
    if len(cagri.args) > 1:
        return bool(cagri.args[1])
    return True


# ---------------------------------------------------------------- (a) tek dahil/hariç yüklemi

class KopyalanirKumeTest(unittest.TestCase):
    def test_kume_kopyalanir_dahil_dosyalar(self):
        for g in ("scripts/ork_lib.py", "skills/is/SKILL.md", ".mcp.json", "hooks/cursor-hooks.json", "bin/orkestra.cmd"):
            self.assertTrue(cursor_kur.kopyalanir(g), g)

    def test_kume_kopyalanir_haric_dizinler(self):
        for g in ("tests/test_x.py", "docs/a.md", "evals/e.json", "x/y.txt", "scripts/__pycache__/a.cpython-313.pyc",
                  ".git/config", "node_modules/p/index.js", ".pytest_cache/v", "skills/s/tests/t.py", "panel/docs/a.md"):
            self.assertFalse(cursor_kur.kopyalanir(g), g)

    def test_kume_kopyalanir_haric_dosya_ve_uzanti(self):
        for g in ("readme-for-human.md", "scripts/a.pyc", "scripts/a.pyo", "uv.lock", "skills/s/readme-for-human.md"):
            self.assertFalse(cursor_kur.kopyalanir(g), g)

    def test_kume_kopyalanir_onek_benzeri_dizin_haric_degil(self):
        self.assertTrue(cursor_kur.kopyalanir("testsuite/a.py"))
        self.assertTrue(cursor_kur.kopyalanir("scripts/docs_yaz.py"))

    def test_kume_dosyalar_yuklemi_kullanir(self):
        kok = tempfile.mkdtemp(prefix="ork_kume_")
        self.addCleanup(shutil.rmtree, kok, True)
        _yaz(os.path.join(kok, "scripts", "a.py"), b"a")
        _yaz(os.path.join(kok, "scripts", "b.py"), b"b")
        with mock.patch.object(cursor_kur, "kopyalanir", side_effect=lambda g: g != "scripts/b.py"):
            d = cursor_kur.dosyalar(kok)
        self.assertEqual(sorted(d), ["scripts/a.py"])

    def test_kume_haric_listesi_tek_yerde(self):
        """Kopya hariç kümesi (tests/evals/docs) yalnız cursor_kur.py'de tanımlı; harita.py'nin ayrı HARIC_DIZIN'i başka amaçlıdır."""
        scripts = os.path.join(KOK, "scripts")
        tanim = re.compile(r"^[ \t]*[A-Za-z_]\w*[ \t]*=.*['\"]evals['\"].*['\"]tests['\"]|"
                           r"^[ \t]*[A-Za-z_]\w*[ \t]*=.*['\"]tests['\"].*['\"]evals['\"]", re.M)
        bulunan = []
        for dizin, altlar, adlar in os.walk(scripts):
            altlar[:] = [a for a in altlar if a != "__pycache__"]
            for ad in adlar:
                if ad.endswith(".py"):
                    with open(os.path.join(dizin, ad), encoding="utf-8", errors="replace") as f:
                        if tanim.search(f.read()):
                            bulunan.append(os.path.relpath(os.path.join(dizin, ad), scripts).replace(os.sep, "/"))
        self.assertEqual(bulunan, ["cursor_kur.py"])
        for ad in ("ork_lib.py", "hook.py", "oturum_bakim.py"):
            with open(os.path.join(scripts, ad), encoding="utf-8", errors="replace") as f:
                metin = f.read()
            for sabit in ("HARIC_DIZIN", "HARIC_DOSYA", "HARIC_UZANTI"):
                self.assertNotRegex(metin, rf"(?m)^\s*{sabit}\s*=", f"{ad} {sabit} tanımlıyor")


# ---------------------------------------------------------------- (b) bayatlik kümesi

class BayatlikKumeTest(unittest.TestCase):
    def setUp(self):
        self.depo = tempfile.mkdtemp(prefix="ork_kume_depo_")
        self.calisan = tempfile.mkdtemp(prefix="ork_kume_calisan_")
        self.addCleanup(shutil.rmtree, self.depo, True)
        self.addCleanup(shutil.rmtree, self.calisan, True)
        self.kaynak = os.path.join(self.depo, "plugins", "orkestra")
        for kok in (self.kaynak, self.calisan):
            _yaz(os.path.join(kok, "scripts", "a.py"), b"print(1)\n")
            _yaz(os.path.join(kok, "skills", "s", "SKILL.md"), b"---\nname: s\n---\n")
            _yaz(os.path.join(kok, ".mcp.json"), b"{}")

    def _bayatlik(self):
        return L.bayatlik(calisan=self.calisan, kaynak_depo=self.depo)

    def test_kume_ayni_kopya_none(self):
        self.assertIsNone(self._bayatlik())

    def test_kume_yalniz_tests_docs_evals_farki_none(self):
        _yaz(os.path.join(self.kaynak, "tests", "test_yeni.py"), b"x")
        _yaz(os.path.join(self.kaynak, "docs", "adr", "0001.md"), b"karar")
        _yaz(os.path.join(self.kaynak, "evals", "e.json"), b"{}")
        _yaz(os.path.join(self.calisan, "tests", "eski.py"), b"y")
        _yaz(os.path.join(self.calisan, "docs", "adr", "0001.md"), b"eski karar")
        self.assertIsNone(self._bayatlik())

    def test_kume_haric_dosya_ve_onbellek_farki_none(self):
        _yaz(os.path.join(self.kaynak, "scripts", "__pycache__", "a.cpython-313.pyc"), b"\x00")
        _yaz(os.path.join(self.kaynak, "readme-for-human.md"), b"insan")
        _yaz(os.path.join(self.kaynak, "uv.lock"), b"kilit")
        self.assertIsNone(self._bayatlik())

    def test_kume_degisen_dahil_dosya_farkli_bir(self):
        _yaz(os.path.join(self.kaynak, "scripts", "a.py"), b"print(2)\n")
        b = self._bayatlik()
        self.assertIsNotNone(b)
        self.assertEqual(b["farkli"], 1)

    def test_kume_kaynakta_olup_kopyada_olmayan_sayilir(self):
        _yaz(os.path.join(self.kaynak, "scripts", "yeni.py"), b"y")
        b = self._bayatlik()
        self.assertIsNotNone(b)
        self.assertEqual(b["farkli"], 1)

    def test_kume_hedefteki_fazla_dosya_sayilmaz(self):
        _yaz(os.path.join(self.calisan, "ozel.txt"), b"kullanici dosyasi")
        _yaz(os.path.join(self.calisan, "scripts", "eski_modul.py"), b"eski")
        self.assertIsNone(self._bayatlik())

    def test_kume_hedefteki_fazla_dosya_degisen_sayisina_eklenmez(self):
        _yaz(os.path.join(self.calisan, "scripts", "eski_modul.py"), b"eski")
        _yaz(os.path.join(self.kaynak, "scripts", "a.py"), b"print(3)\n")
        self.assertEqual(self._bayatlik()["farkli"], 1)

    def test_kume_crlf_farki_yok_sayilir(self):
        _yaz(os.path.join(self.kaynak, "scripts", "a.py"), b"print(1)\r\n")
        _yaz(os.path.join(self.calisan, "skills", "s", "SKILL.md"), b"---\r\nname: s\r\n---\r\n")
        self.assertIsNone(self._bayatlik())

    def test_kume_bayatlik_yuklemi_kullanir(self):
        _yaz(os.path.join(self.kaynak, "scripts", "a.py"), b"print(9)\n")
        with mock.patch.object(cursor_kur, "kopyalanir", side_effect=lambda g: g != "scripts/a.py"):
            self.assertIsNone(self._bayatlik())

    def test_kume_farkli_sayisi_cursor_kur_fark_ile_esit(self):
        _yaz(os.path.join(self.kaynak, "scripts", "a.py"), b"print(4)\n")
        _yaz(os.path.join(self.kaynak, "scripts", "yeni.py"), b"y")
        _yaz(os.path.join(self.kaynak, "skills", "t", "SKILL.md"), b"t")
        _yaz(os.path.join(self.kaynak, "tests", "t.py"), b"t")
        _yaz(os.path.join(self.calisan, "fazla.txt"), b"f")
        eksik, degisen = cursor_kur.fark(self.kaynak, self.calisan)
        self.assertEqual(self._bayatlik()["farkli"], len(eksik) + len(degisen))
        self.assertEqual(self._bayatlik()["farkli"], 3)

    def test_kume_kaynak_yoksa_none(self):
        shutil.rmtree(self.kaynak)
        self.assertIsNone(self._bayatlik())


# ---------------------------------------------------------------- (c) alt süreç yok

class SubprocessYokTest(unittest.TestCase):
    def setUp(self):
        self.depo = tempfile.mkdtemp(prefix="ork_sp_depo_")
        self.calisan = tempfile.mkdtemp(prefix="ork_sp_calisan_")
        self.addCleanup(shutil.rmtree, self.depo, True)
        self.addCleanup(shutil.rmtree, self.calisan, True)
        kaynak = os.path.join(self.depo, "plugins", "orkestra")
        _yaz(os.path.join(kaynak, "scripts", "a.py"), b"yeni")
        _yaz(os.path.join(self.calisan, "scripts", "a.py"), b"eski")
        os.makedirs(os.path.join(self.depo, ".git"))

    def _yamalar(self):
        run = mock.patch("subprocess.run", side_effect=AssertionError("subprocess.run çağrıldı"))
        popen = mock.patch("subprocess.Popen", side_effect=AssertionError("subprocess.Popen çağrıldı"))
        kontrol = mock.patch.object(guncelle, "kontrol", side_effect=AssertionError("guncelle.kontrol çağrıldı"))
        return run, popen, kontrol

    def test_subprocess_bayatlik_alt_surec_acmaz(self):
        run, popen, kontrol = self._yamalar()
        with run as r, popen as p, kontrol as k:
            b = L.bayatlik(calisan=self.calisan, kaynak_depo=self.depo)
        self.assertEqual(b["farkli"], 1)
        r.assert_not_called()
        p.assert_not_called()
        k.assert_not_called()

    def test_subprocess_uyari_yolu_alt_surec_acmaz(self):
        run, popen, kontrol = self._yamalar()
        onb = {"bayatlik": {"farkli": 2}, "surum": {"durum": "yeni", "fark": 4}}
        with run as r, popen as p, kontrol as k:
            satirlar = hook.guncellik_satirlari(onb)
        self.assertEqual(len(satirlar), 2)
        r.assert_not_called()
        p.assert_not_called()
        k.assert_not_called()


# ---------------------------------------------------------------- (d) oturum bakımında surum adımı

class SurumAdimiTest(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_surum_")
        self.addCleanup(shutil.rmtree, self.sd, True)
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GIT_TERMINAL_PROMPT", None)

    def _damga(self):
        return os.path.join(self.sd, oturum_bakim.SURUM_DAMGA)

    def _eskit(self, saat):
        t = time.time() - saat * 3600
        os.utime(self._damga(), (t, t))

    def test_surum_son_adim(self):
        adlar = [ad for ad, _ in oturum_bakim._adimlar(self.sd, self.sd)]
        self.assertEqual(adlar[-1], "surum")
        self.assertEqual(adlar.count("surum"), 1)
        self.assertIn("bayatlik", adlar)

    def test_surum_zaman_asimi_varsayilan_30(self):
        self.assertEqual(oturum_bakim.SURUM_ZAMAN_ASIMI_SN, 30)

    def test_surum_ilk_kosu_getir_true_sonraki_getir_false(self):
        k = mock.Mock(return_value={"durum": "guncel", "fark": 0})
        with mock.patch.object(guncelle, "kontrol", k):
            oturum_bakim.surum_adimi(self.sd)
            oturum_bakim.surum_adimi(self.sd)
            oturum_bakim.surum_adimi(self.sd)
        self.assertEqual([_getir_degeri(c) for c in k.call_args_list], [True, False, False])

    def test_surum_damga_basarisiz_denemede_de_yazilir(self):
        k = mock.Mock(return_value={"durum": "hata", "neden": "GitHub'a ulaşılamadı"})
        with mock.patch.object(guncelle, "kontrol", k):
            oturum_bakim.surum_adimi(self.sd)
            self.assertTrue(os.path.isfile(self._damga()))
            oturum_bakim.surum_adimi(self.sd)
        self.assertEqual([_getir_degeri(c) for c in k.call_args_list], [True, False])

    def test_surum_bir_gun_sonra_yeniden_getir_true(self):
        k = mock.Mock(return_value={"durum": "guncel", "fark": 0})
        with mock.patch.object(guncelle, "kontrol", k):
            oturum_bakim.surum_adimi(self.sd)
            self._eskit(25)
            oturum_bakim.surum_adimi(self.sd)
        self.assertEqual([_getir_degeri(c) for c in k.call_args_list], [True, True])

    def test_surum_ayni_gun_icinde_getir_false(self):
        k = mock.Mock(return_value={"durum": "guncel", "fark": 0})
        with mock.patch.object(guncelle, "kontrol", k):
            oturum_bakim.surum_adimi(self.sd)
            self._eskit(0.5)
            oturum_bakim.surum_adimi(self.sd)
        self.assertEqual([_getir_degeri(c) for c in k.call_args_list], [True, False])

    def test_surum_kontrol_sonucunu_doner(self):
        r = {"durum": "yeni", "fark": 3, "kurulu": "abc1234", "yeni": "def5678"}
        with mock.patch.object(guncelle, "kontrol", return_value=r):
            v = oturum_bakim.surum_adimi(self.sd)
        self.assertEqual(v["durum"], "yeni")
        self.assertEqual(v["fark"], 3)

    def test_surum_git_terminal_prompt_kapali(self):
        gorulen = []
        with mock.patch.object(guncelle, "kontrol",
                               side_effect=lambda *a, **k: gorulen.append(os.environ.get("GIT_TERMINAL_PROMPT")) or {"durum": "guncel"}):
            oturum_bakim.surum_adimi(self.sd)
        self.assertEqual(gorulen, ["0"])

    def test_surum_zaman_asiminda_sessizce_atlanir(self):
        serbest = threading.Event()
        self.addCleanup(serbest.set)

        def asili(*a, **k):
            serbest.wait(10)
            return {"durum": "guncel"}

        with mock.patch.object(guncelle, "kontrol", side_effect=asili), \
                mock.patch.object(oturum_bakim, "SURUM_ZAMAN_ASIMI_SN", 0.3):
            t0 = time.monotonic()
            v = oturum_bakim.surum_adimi(self.sd)
            sure = time.monotonic() - t0
        self.assertIsNone(v)
        self.assertLess(sure, 3)

    def test_surum_zaman_asiminda_diger_adimlarin_onbellegi_yazilir(self):
        serbest = threading.Event()
        self.addCleanup(serbest.set)

        def asili(*a, **k):
            serbest.wait(10)
            return {"durum": "yeni", "fark": 1}

        adimlar = [("bayatlik", lambda: {"farkli": 2}), ("surum", lambda: oturum_bakim.surum_adimi(self.sd))]
        with mock.patch.object(guncelle, "kontrol", side_effect=asili), \
                mock.patch.object(oturum_bakim, "SURUM_ZAMAN_ASIMI_SN", 0.3), \
                mock.patch.object(oturum_bakim, "_adimlar", return_value=adimlar), \
                mock.patch.object(oturum_bakim, "_hata_yaz") as hy:
            t0 = time.monotonic()
            self.assertTrue(oturum_bakim.calistir(self.sd, self.sd))
            sure = time.monotonic() - t0
        onb = oturum_bakim.onbellek(self.sd)
        self.assertEqual(onb.get("bayatlik"), {"farkli": 2})
        self.assertNotIn("surum", onb)
        self.assertLess(sure, 3)
        hy.assert_not_called()

    def test_surum_sonucu_onbellege_yazilir(self):
        with mock.patch.object(guncelle, "kontrol", return_value={"durum": "yeni", "fark": 2}), \
                mock.patch.object(oturum_bakim, "_adimlar",
                                  return_value=[("surum", lambda: oturum_bakim.surum_adimi(self.sd))]):
            oturum_bakim.calistir(self.sd, self.sd)
        self.assertEqual(oturum_bakim.onbellek(self.sd)["surum"]["fark"], 2)


# ---------------------------------------------------------------- (e) hook uyarı satırı

class GuncellikUyariTest(unittest.TestCase):
    def test_uyari_bos_onbellek_satir_yok(self):
        self.assertEqual(hook.guncellik_satirlari({}), [])

    def test_uyari_bayatlik_dosya_farkli_ve_guncelle(self):
        s = hook.guncellik_satirlari({"bayatlik": {"farkli": 3, "kaynak": "x"}})
        self.assertEqual(len(s), 1)
        self.assertIn("3 dosya farklı", s[0])
        self.assertIn("`orkestra guncelle`", s[0])

    def test_uyari_bayatlik_none_satir_yok(self):
        self.assertEqual(hook.guncellik_satirlari({"bayatlik": None}), [])

    def test_uyari_surum_yeni_commit_sayisi_ve_github(self):
        s = hook.guncellik_satirlari({"surum": {"durum": "yeni", "fark": 7}})
        self.assertEqual(len(s), 1)
        self.assertRegex(s[0], r"(?<!\d)7(?!\d)")
        self.assertIn("GitHub", s[0])
        self.assertNotIn("dosya farklı", s[0])

    def test_uyari_surum_hata_iken_uyari_yok(self):
        self.assertEqual(hook.guncellik_satirlari({"surum": {"durum": "hata", "fark": None, "neden": "ağ yok"}}), [])

    def test_uyari_surum_guncel_iken_uyari_yok(self):
        self.assertEqual(hook.guncellik_satirlari({"surum": {"durum": "guncel", "fark": 0}}), [])

    def test_uyari_surum_bozuk_kayit_dusurmez(self):
        self.assertEqual(hook.guncellik_satirlari({"surum": "bozuk"}), [])

    def test_uyari_iki_sinyal_ayri_satir(self):
        s = hook.guncellik_satirlari({"bayatlik": {"farkli": 2}, "surum": {"durum": "yeni", "fark": 5}})
        self.assertEqual(len(s), 2)
        self.assertTrue(any("2 dosya farklı" in x for x in s))
        self.assertTrue(any("GitHub" in x and re.search(r"(?<!\d)5(?!\d)", x) for x in s))

    def test_uyari_bayatlik_varken_surum_hata_yalniz_kopya_satiri(self):
        s = hook.guncellik_satirlari({"bayatlik": {"farkli": 1}, "surum": {"durum": "hata"}})
        self.assertEqual(len(s), 1)
        self.assertNotIn("GitHub", s[0])

    def test_uyari_session_start_onbellekten_guncellik_satirlarini_kullanir(self):
        sd = tempfile.mkdtemp(prefix="ork_uyari_")
        self.addCleanup(shutil.rmtree, sd, True)
        onb = {"surum": {"durum": "yeni", "fark": 2}}
        with mock.patch.dict(os.environ, {"ORKESTRA_OTURUM_BAKIM": "1"}), \
                mock.patch.object(oturum_bakim, "onbellek", return_value=onb), \
                mock.patch.object(L, "bayatlik", side_effect=AssertionError("hook yolu bayatlik hesapladı")), \
                mock.patch.object(hook, "guncellik_satirlari", return_value=["GUNCELLIK-SATIRI"]) as gs:
            u, _ = hook._ss_uyarilar(sd, {})
        self.assertIn("GUNCELLIK-SATIRI", u)
        gs.assert_called_once()
        self.assertEqual(gs.call_args.args[0], onb)


if __name__ == "__main__":
    unittest.main()
