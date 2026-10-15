"""ic_kos.kos süreç içi yolunun iş parçacığı güvenliği (G-128): eşzamanlı çağrılar birbirinin argv/ortam/cwd'sini ezmez."""
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402

# Sahte orkestra.py: argv/ortam/cwd'yi okur, bekler (diğer iş parçacığına ezme fırsatı verir), yeniden okur.
SAHTE = '''import os, sys, time
def main():
    a, e, c = list(sys.argv), os.environ.get("ESZ_ETIKET"), os.getcwd()
    time.sleep(0.02)
    b, f, d = list(sys.argv), os.environ.get("ESZ_ETIKET"), os.getcwd()
    print("TUTARLI" if (a == b and e == f and c == d and a[1] == e) else "KARISTI %r %r %r" % (a, b, e))
'''


class IcKosEszamanli(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.betik = os.path.join(self._t.name, "orkestra.py")
        with open(self.betik, "w", encoding="utf-8") as f:
            f.write(SAHTE)

    def _is(self, etiket, n, sonuc):
        for i in range(n):
            ad = f"{etiket}{i}"
            r = ic_kos.kos([self.betik, ad], cwd=self._t.name, env=dict(os.environ, ESZ_ETIKET=ad))
            sonuc.append((ad, r.returncode, r.stdout.strip(), r.stderr))

    def test_dort_is_parcacigi_argv_ortam_karismaz(self):
        sonuc = []
        ts = [threading.Thread(target=self._is, args=(p, 15, sonuc)) for p in "abcd"]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(sonuc), 60)
        self.assertEqual(len({s[0] for s in sonuc}), 60)
        for ad, kod, cikti, hata in sonuc:
            self.assertEqual((kod, cikti), (0, "TUTARLI"), f"{ad}: {cikti} {hata}")

    def test_kilit_modul_duzeyinde_ve_yeniden_girilebilir(self):
        self.assertTrue(hasattr(ic_kos._KILIT, "acquire"))
        with ic_kos._KILIT:  # RLock: aynı iş parçacığı içinden iç içe çağrı kilitlenmez
            r = ic_kos.kos([self.betik, "x"], cwd=self._t.name, env=dict(os.environ, ESZ_ETIKET="x"))
        self.assertEqual(r.stdout.strip(), "TUTARLI")

    def test_alt_surec_yolu_kilitsiz(self):
        # Betik orkestra.py/hook.py değil -> alt süreç; kilit tutulurken başka iş parçacığı yine de koşabilmeli.
        sonuc = []
        with ic_kos._KILIT:
            t = threading.Thread(target=lambda: sonuc.append(ic_kos.kos(["-c", "print(7)"])))
            t.start()
            t.join(30)
        self.assertFalse(t.is_alive())
        self.assertEqual(sonuc[0].stdout.strip(), "7")


if __name__ == "__main__":
    unittest.main()
