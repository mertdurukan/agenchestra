"""İşlem içi önbellekler: ork_lib.kartlar() ve ork_lib.fiyat_tablosu().
`py -3.13 -m pytest plugins/orkestra/tests/test_onbellek.py -q`

1) kartlar(): dosya değişince (mtime_ns/boyut) yeni içerik görünür; silinen kart düşer.
2) kartlar(): dönen kart değiştirilirse önbellek bozulmaz (her çağrıda bağımsız kopya).
3) kartlar(): bozuk kart önbellekte kalsa da düzeldiğinde görünür.
4) fiyat_tablosu(): dosya değişmedikçe aynı nesne, değişince yeniden okunur.
"""
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


def _yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(veri if isinstance(veri, str) else json.dumps(veri))


class KartOnbellegi(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_onbellek_sd_")
        self.yol = os.path.join(self.sd, "gorevler", "G-001.json")

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def test_dosya_degisince_yeni_icerik_gorunur(self):
        _yaz(self.yol, {"id": "G-001", "baslik": "eski"})
        self.assertEqual(L.kartlar(self.sd)[0]["baslik"], "eski")
        _yaz(self.yol, {"id": "G-001", "baslik": "yeni baslik daha uzun"})
        self.assertEqual(L.kartlar(self.sd)[0]["baslik"], "yeni baslik daha uzun")

    def test_silinen_kart_duser(self):
        _yaz(self.yol, {"id": "G-001"})
        self.assertEqual(len(L.kartlar(self.sd)), 1)
        os.remove(self.yol)
        self.assertEqual(L.kartlar(self.sd), [])

    def test_donen_kart_degistirilirse_onbellek_bozulmaz(self):
        _yaz(self.yol, {"id": "G-001", "baslik": "temiz", "liste": [1]})
        k = L.kartlar(self.sd)[0]
        k["baslik"] = "bozuldu"
        k["liste"].append(2)
        yine = L.kartlar(self.sd)[0]
        self.assertEqual(yine["baslik"], "temiz")
        self.assertEqual(yine["liste"], [1])

    def test_bozuk_kart_duzelince_gorunur(self):
        _yaz(self.yol, "{bozuk")
        self.assertEqual(L.kartlar(self.sd), [])
        self.assertEqual(L.kartlar(self.sd), [])  # önbellekten, yine atlanır
        _yaz(self.yol, {"id": "G-001", "baslik": "düzeldi"})
        self.assertEqual([k["id"] for k in L.kartlar(self.sd)], ["G-001"])


class FiyatOnbellegi(unittest.TestCase):
    def test_degismedikce_ayni_nesne(self):
        self.assertIs(L.fiyat_tablosu(), L.fiyat_tablosu())

    def test_dosya_degisince_yeniden_okunur(self):
        kok = tempfile.mkdtemp(prefix="ork_fiyat_")
        try:
            yol = os.path.join(kok, "bin", "fiyat.json")
            _yaz(yol, {"varsayilan": "a", "modeller": {"a": {"x": 1}}})
            with mock.patch.object(L, "PLUGIN_ROOT", kok):
                self.assertEqual(L.fiyat_tablosu()["modeller"]["a"]["x"], 1)
                _yaz(yol, {"varsayilan": "a", "modeller": {"a": {"x": 22}}})
                L._FIYAT_ONBELLEK["kontrol"] = 0.0  # fiyat_tablosu dosyaya 1 sn'de bir bakar; süreyi doldurmuş say
                self.assertEqual(L.fiyat_tablosu()["modeller"]["a"]["x"], 22)
        finally:
            shutil.rmtree(kok, ignore_errors=True)


# ============================================================================================================
# I-309 P5: test sonucu önbelleği ve tek uçuş (scripts/test_onbellek.py, test_paralel.py bağlaması).
# K1: aynı girdiyle ikinci çağrı yeni test süreci açmaz, çıktıda "önbellekten" satırı.
# K2: kaynak dosya (test klasöründeki yardımcı modül ya da özetlenen kökteki kod/ayar) değişince isabet yok;
#     yalnız mtime değişince anahtar aynı.
# K3: düşen koşu önbelleğe alınmaz.
# K4: eşzamanlı iki aynı-anahtarlı istek tek test süreci doğurur.
# Test süreci sayısı, test fonksiyonunun her koşuşta bir satır eklediği sayaç dosyasıyla ölçülür (özetlenen ağaçların
# dışında; yolu önek dışı ortam değişkeniyle verilir, anahtara girmez). Modül, test_paralel'in yükleyicisiyle alınır
# (bu test dosyası da `test_onbellek` adını taşıdığı için düz import çakışırdı).
import subprocess  # noqa: E402
import time  # noqa: E402

import kaynak_kira  # noqa: E402
import test_paralel  # noqa: E402

T = test_paralel.test_onbellek
KOSUCU = os.path.join(C.KOK, "scripts", "test_paralel.py")

ORNEK_TEST = """import os, time
import yardimci

def test_say():
    with open(os.environ["ONBELLEK_SAYAC"], "a", encoding="utf-8") as f:
        f.write("x\\n")
    time.sleep(float(os.environ.get("ONBELLEK_UYKU") or 0))
    assert os.environ.get("ONBELLEK_DUS") != "1"
    assert yardimci.DEGER == 1
"""


class _OnbellekTemel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_test_onbellek_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tdir = os.path.join(self.tmp, "t")
        self.src = os.path.join(self.tmp, "src")
        _yaz(os.path.join(self.tdir, "test_ornek.py"), ORNEK_TEST)
        _yaz(os.path.join(self.tdir, "yardimci.py"), "DEGER = 1\n")
        _yaz(os.path.join(self.src, "scripts", "kod.py"), "A = 1\n")
        _yaz(os.path.join(self.src, "ayarlar", "ayar.json"), '{"x": 1}\n')
        self.sayac = os.path.join(self.tmp, "sayac.txt")
        self.kira = os.path.join(self.tmp, "kira")
        self.ayar = os.path.join(self.tmp, "kaynak_kira.json")
        self.onbellek(True)

    def onbellek(self, deger):
        _yaz(self.ayar, {"mod": "golge", "onbellek": deger, "yoklama_s": 0.05})

    def env(self, **ek):
        e = {k: v for k, v in os.environ.items()
             if k not in (T.ATALAR_ENV, kaynak_kira.SAHIP_ENV, T.KAPAT_ENV, "ONBELLEK_DUS", "ONBELLEK_UYKU")}
        e.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", ORKESTRA_KAYNAK_KIRA_DIZINI=self.kira,
                 ORKESTRA_KAYNAK_KIRA_AYAR=self.ayar, ONBELLEK_SAYAC=self.sayac)
        e[T.KOKLER_ENV] = self.src
        e.update(ek)
        return e

    def baslat(self, *args, **ek):
        return subprocess.Popen([sys.executable, KOSUCU, "-n", "1", *args, self.tdir], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                env=self.env(**ek), cwd=self.tmp)

    def kos(self, *args, **ek):
        p = self.baslat(*args, **ek)
        cikti = p.communicate(timeout=180)[0]
        return p.returncode, cikti

    def surec_sayisi(self):
        try:
            with open(self.sayac, encoding="utf-8") as f:
                return len(f.read().splitlines())
        except OSError:
            return 0


class K1OnbellekIsabeti(_OnbellekTemel):
    def test_ikinci_cagri_yeni_surec_acmaz_onbellekten_doner(self):
        k1, c1 = self.kos()
        self.assertEqual(k1, 0, c1)
        self.assertNotIn("önbellekten", c1)
        self.assertEqual(self.surec_sayisi(), 1)
        k2, c2 = self.kos()
        self.assertEqual(k2, 0, c2)
        self.assertEqual(self.surec_sayisi(), 1, "ikinci çağrı test süreci açtı:\n" + c2)
        self.assertRegex(c2, r"(?m)^önbellekten: [0-9a-f]{12} ")
        self.assertIn("1 passed", c2)  # kayıtlı rapor da döner

    def test_farkli_arguman_isabet_etmez(self):
        self.assertEqual(self.kos()[0], 0)
        kod, c = self.kos("--zaman-asimi", "77")
        self.assertEqual(kod, 0, c)
        self.assertNotIn("önbellekten", c)
        self.assertEqual(self.surec_sayisi(), 2)


class K2OnbellekBayatlik(_OnbellekTemel):
    def test_test_klasorundeki_kaynak_degisince_isabet_etmez(self):
        self.assertEqual(self.kos()[0], 0)
        _yaz(os.path.join(self.tdir, "yardimci.py"), "DEGER = 1  # değişti\n")
        kod, c = self.kos()
        self.assertEqual(kod, 0, c)
        self.assertNotIn("önbellekten", c)
        self.assertEqual(self.surec_sayisi(), 2)

    def test_ozetlenen_kokteki_kod_ayar_ve_yeni_dosya_isabeti_bozar(self):
        self.assertEqual(self.kos()[0], 0)
        _yaz(os.path.join(self.src, "scripts", "kod.py"), "A = 2\n")
        self.assertNotIn("önbellekten", self.kos()[1])
        _yaz(os.path.join(self.src, "ayarlar", "ayar.json"), '{"x": 2}\n')
        self.assertNotIn("önbellekten", self.kos()[1])
        _yaz(os.path.join(self.src, "scripts", "yeni.py"), "")
        self.assertNotIn("önbellekten", self.kos()[1])
        self.assertEqual(self.surec_sayisi(), 4)

    def test_anahtar_icerige_bagli_mtimea_degil(self):
        dosyalar = [os.path.join(self.tdir, "test_ornek.py")]
        a1, _ = T.anahtar(dosyalar, {"n": 1}, [self.src])
        yol = os.path.join(self.src, "ayarlar", "ayar.json")
        os.utime(yol, (time.time() + 500, time.time() + 500))
        self.assertEqual(a1, T.anahtar(dosyalar, {"n": 1}, [self.src])[0], "yalnız mtime değişti")
        _yaz(os.path.join(self.src, "__pycache__", "x.pyc"), "artik")
        self.assertEqual(a1, T.anahtar(dosyalar, {"n": 1}, [self.src])[0], "çalışma artığı anahtara girmez")
        _yaz(yol, '{"x": 3}\n')
        a2 = T.anahtar(dosyalar, {"n": 1}, [self.src])[0]
        self.assertNotEqual(a1, a2)
        self.assertNotEqual(a2, T.anahtar(dosyalar, {"n": 2}, [self.src])[0], "argüman anahtara girer")
        with mock.patch.dict(os.environ, {"ORKESTRA_HERHANGI_KAPI": "0"}):
            self.assertNotEqual(a2, T.anahtar(dosyalar, {"n": 1}, [self.src])[0], "kapı bayrağı anahtara girer")

    def test_varsayilan_kok_eklentinin_tamami(self):
        with mock.patch.dict(os.environ, {T.KOKLER_ENV: ""}):
            self.assertEqual(T.kokler(), [T.EKLENTI_KOKU])
        for alt in ("scripts", "tests", "ayarlar", "hooks", "kurallar"):
            self.assertNotIn(alt, T.DISLA_DIZIN)
        self.assertTrue(all(os.path.isdir(os.path.join(T.EKLENTI_KOKU, a)) for a in ("scripts", "tests", "ayarlar")))


class K3OnbellekDusen(_OnbellekTemel):
    def test_dusen_kosu_onbellege_alinmaz(self):
        _yaz(os.path.join(self.tdir, "yardimci.py"), "DEGER = 2\n")
        k1, c1 = self.kos()
        self.assertEqual(k1, 1, c1)
        k2, c2 = self.kos()
        self.assertEqual(k2, 1, c2)
        self.assertNotIn("önbellekten", c2)
        self.assertEqual(self.surec_sayisi(), 2)
        d = os.path.join(self.kira, "onbellek")
        ana = [x for x in os.listdir(d) if x.endswith(".json") and x.count(".") == 1] if os.path.isdir(d) else []
        self.assertEqual(ana, [], "düşen sonuç önbellek kaydı yazdı")


class K4TekUcus(_OnbellekTemel):
    def test_eszamanli_iki_istek_tek_surec(self):
        ps = [self.baslat(ONBELLEK_UYKU="4") for _ in range(2)]
        ciktilar = [p.communicate(timeout=180)[0] for p in ps]
        hepsi = "\n---\n".join(ciktilar)
        self.assertEqual([p.returncode for p in ps], [0, 0], hepsi)
        self.assertEqual(self.surec_sayisi(), 1, hepsi)
        self.assertEqual(sum("önbellekten (tek uçuş)" in c for c in ciktilar), 1, hepsi)

    def test_bekleyen_dusen_liderin_sonucunu_alir_ve_saklanmaz(self):
        _yaz(os.path.join(self.tdir, "yardimci.py"), "DEGER = 2\n")
        ps = [self.baslat(ONBELLEK_UYKU="4") for _ in range(2)]
        ciktilar = [p.communicate(timeout=180)[0] for p in ps]
        hepsi = "\n---\n".join(ciktilar)
        self.assertEqual([p.returncode for p in ps], [1, 1], hepsi)
        self.assertEqual(self.surec_sayisi(), 1, hepsi)
        self.assertEqual(sum("tek uçuş: süren aynı koşunun sonucu döndü" in c for c in ciktilar), 1, hepsi)
        self.assertNotIn("önbellekten", self.kos()[1])
        self.assertEqual(self.surec_sayisi(), 2)


class OnbellekModlari(_OnbellekTemel):
    def test_golge_isabeti_yazar_yine_kosar_ve_bayati_yakalar(self):
        self.onbellek("golge")
        self.assertEqual(self.kos()[0], 0)
        kod, c = self.kos()
        self.assertEqual(kod, 0, c)
        self.assertIn("isabet olurdu", c)
        self.assertNotRegex(c, r"(?m)^önbellekten")
        self.assertEqual(self.surec_sayisi(), 2)
        kod, c = self.kos(ONBELLEK_DUS="1")  # anahtarın görmediği girdi: gölge bayat isabeti ölçer
        self.assertEqual(kod, 1, c)
        self.assertIn("BAYAT isabet", c)

    def test_kapali_iken_eski_davranis(self):
        self.onbellek(False)
        self.assertEqual(self.kos()[0], 0)
        kod, c = self.kos()
        self.assertEqual(kod, 0, c)
        self.assertNotIn("önbellek", c)
        self.assertEqual(self.surec_sayisi(), 2)
        self.assertFalse(os.path.isdir(os.path.join(self.kira, "onbellek")))

    def test_ortam_degiskeni_kapatir(self):
        self.assertEqual(self.kos(**{T.KAPAT_ENV: "0"})[0], 0)
        self.assertNotIn("önbellekten", self.kos(**{T.KAPAT_ENV: "0"})[1])
        self.assertEqual(self.surec_sayisi(), 2)


if __name__ == "__main__":
    unittest.main()
