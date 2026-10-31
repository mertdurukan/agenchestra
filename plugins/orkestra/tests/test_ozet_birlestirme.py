"""I-309 P3 (C6): ozet.yaz single-flight. Kilidi bekleyen, bu çağrıdan sonra başlamış bir hesaplamanın yazdığı
ozet.json'u bulursa yeniden hesaplamaz; çağrıdan önce başlamış hesabın (bayat) çıktısını ise kabul etmez.
`PYTHONUTF8=1 python -m pytest plugins/orkestra/tests/test_ozet_birlestirme.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = os.path.join(KOK, "scripts")
sys.path.insert(0, SCR)
import ork_lib as L  # noqa: E402
import ozet  # noqa: E402

N_SUREC = 8
TEKRAR = 20

# Çocuk süreç: gerçek olustur'u sayarak sarar, N süreç hazır olana kadar bekler (dosya bariyeri), sonra yaz çağırır.
COCUK = r'''
import json, os, sys, time
scr, sd, proje, bariyer, n, kayit = sys.argv[1:7]
sys.path.insert(0, scr)
import ozet
gercek = ozet.olustur
def sayan(*a, **k):
    with open(kayit, "a", encoding="utf-8") as f:
        f.write("olustur\n")
    return gercek(*a, **k)
ozet.olustur = sayan
open(os.path.join(bariyer, str(os.getpid())), "w").close()
son = time.time() + 60
while len(os.listdir(bariyer)) < int(n) and time.time() < son:
    time.sleep(0.002)
r = ozet.yaz(sd, proje)
with open(kayit + ".yaz", "a", encoding="utf-8") as f:
    f.write(("ok" if isinstance(r, dict) else "bos") + "\n")
'''


def _satir(yol):
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        return f.read().splitlines()


class EszamanliYaz(unittest.TestCase):
    """K1: soğuk durum dizini, 20 tekrar x 8 eşzamanlı süreç."""

    def test_eszamanli_yaz_tek_hesaplama_zaman_asimi_yok(self):
        for tekrar in range(TEKRAR):
            kok = tempfile.mkdtemp(prefix="ork_c6_")
            try:
                sd = os.path.join(kok, "durum")      # soğuk: ozet.json, .uretim, .lock, .sira yok
                proje = os.path.join(kok, "proje")
                bariyer = os.path.join(kok, "bariyer")
                for d in (sd, proje, bariyer):
                    os.makedirs(d)
                kayit = os.path.join(kok, "kayit.txt")
                env = dict(os.environ, PYTHONUTF8="1")
                ps = [subprocess.Popen([sys.executable, "-c", COCUK, SCR, sd, proje, bariyer, str(N_SUREC), kayit],
                                       env=env) for _ in range(N_SUREC)]
                for p in ps:
                    self.assertEqual(p.wait(120), 0)
                olustur = len(_satir(kayit))
                zaman_asimi = len(_satir(os.path.join(sd, "ozet.json.zaman_asimi.log")))
                with self.subTest(tekrar=tekrar):
                    self.assertEqual(zaman_asimi, 0)
                    self.assertGreaterEqual(olustur, 1)
                    self.assertLess(olustur, N_SUREC)
                    self.assertEqual(_satir(kayit + ".yaz"), ["ok"] * N_SUREC)
                    with open(os.path.join(sd, "ozet.json"), encoding="utf-8") as f:
                        self.assertTrue(json.load(f)["orkestra"])
            finally:
                shutil.rmtree(kok, ignore_errors=True)


class Tazelik(unittest.TestCase):
    """K2: bayat anlık görüntü yazılmaz; taze olan yeniden kullanılır."""

    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_c6t_")
        self.sd = os.path.join(self.kok, "durum")
        self.proje = os.path.join(self.kok, "proje")
        os.makedirs(self.sd)
        os.makedirs(self.proje)
        self.durum = os.path.join(self.sd, "deger.txt")   # "durum": olustur'un okuduğu tek değer
        self._deger(0)
        self.cagri = 0
        self.basladi = threading.Event()
        self.birak = threading.Event()
        self.birak.set()

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def _deger(self, v):
        with open(self.durum, "w", encoding="utf-8") as f:
            f.write(str(v))

    def _olustur(self, sd, proje):
        self.cagri += 1
        with open(self.durum, encoding="utf-8") as f:
            v = int(f.read())
        self.basladi.set()
        self.birak.wait(10)     # hesaplama "uzun sürüyor": durum okundu, yazım henüz yok
        return {"deger": v, "proje": proje}

    def _dosya(self):
        with open(os.path.join(self.sd, "ozet.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_cagridan_once_baslayan_hesap_bayat_sayilir(self):
        # A hesaplamaya başlar (değer 0 okundu), sonra durum değişir ve B çağrılır; A, B başladıktan sonra yazar.
        # B, A'nın yazdığını (mtime B'den yeni olsa da) kabul etmemeli: yeniden hesaplar, son dosya değer 1 taşır.
        self.birak.clear()
        sonuc = {}
        with mock.patch.object(ozet, "olustur", side_effect=self._olustur):
            a = threading.Thread(target=lambda: sonuc.setdefault("a", ozet.yaz(self.sd, self.proje)))
            a.start()
            self.assertTrue(self.basladi.wait(10))
            self._deger(1)
            b = threading.Thread(target=lambda: sonuc.setdefault("b", ozet.yaz(self.sd, self.proje)))
            b.start()
            time.sleep(0.3)    # B kilit beklemesine girsin (bas_ns, A'nın hesap başlangıcından sonra)
            self.birak.set()
            a.join(10)
            b.join(10)
        self.assertEqual(sonuc["a"]["deger"], 0)
        self.assertEqual(sonuc["b"]["deger"], 1)
        self.assertEqual(self.cagri, 2)
        self.assertEqual(self._dosya()["deger"], 1)

    def test_ardisik_cagri_degisikligi_yansitir(self):
        with mock.patch.object(ozet, "olustur", side_effect=self._olustur):
            self.assertEqual(ozet.yaz(self.sd, self.proje)["deger"], 0)
            self._deger(1)
            self.assertEqual(ozet.yaz(self.sd, self.proje)["deger"], 1)
        self.assertEqual(self.cagri, 2)
        self.assertEqual(self._dosya()["deger"], 1)

    def test_bekleyenler_sonra_baslayan_hesabi_paylasir(self):
        # Kilit doluyken iki çağrı birikir; ilk alan hesaplar (başlangıcı ikisinden de sonra), ikincisi onu kullanır.
        sonuc = []
        with mock.patch.object(ozet, "olustur", side_effect=self._olustur):
            with L.kilit(os.path.join(self.sd, "ozet.json")):
                ts = [threading.Thread(target=lambda: sonuc.append(ozet.yaz(self.sd, self.proje))) for _ in range(2)]
                for t in ts:
                    t.start()
                time.sleep(0.3)
            for t in ts:
                t.join(10)
        self.assertEqual(self.cagri, 1)
        self.assertEqual([r["deger"] for r in sonuc], [0, 0])

    def test_farkli_proje_ya_da_dis_degisiklik_yeniden_hesaplar(self):
        yol = os.path.join(self.sd, "ozet.json")
        with mock.patch.object(ozet, "olustur", side_effect=self._olustur):
            ozet.yaz(self.sd, self.proje)
            bas = time.time_ns() - 10**12        # eşik geçmişte: yalnız damga eşleşmesi sınanır
            self.assertIsNotNone(ozet._taze_ozet(yol, self.proje, bas))
            self.assertIsNone(ozet._taze_ozet(yol, os.path.join(self.kok, "baska"), bas))
            L.atomik_yaz(yol, json.dumps({"deger": 99, "elle": True}))   # damgasız dış yazım
            self.assertIsNone(ozet._taze_ozet(yol, self.proje, bas))
            self.assertIsNone(ozet._taze_ozet(yol, self.proje, time.time_ns()))


if __name__ == "__main__":
    unittest.main()
