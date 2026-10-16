"""'Son N gün' pencereleri bilgisayarın yerel takvim gününe göre kesilir (kayan 24 saat değil).

Kabul kriterleri:
  K1  gun_baslangici(1): bugünün yerel 00:00'ı; gece yarısından 5 dk sonra da aynı günün 00:00'ı.
  K2  gun_baslangici(3): iki gün önceki 00:00; kesirli gün (0,5) kayan pencere olarak kalır.
  K3  Pencere aritmetiği: dün 20:00 'bugün' penceresine girmez, bugün 01:00 girer (kayan 24 saat dün 20:00'ı alırdı).
  K4  maliyet ozet'in bugün tutarı: +03:00 ve Z damgalı satırlar yerel güne göre toplanır.
"""
import datetime
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import analitik  # noqa: E402
import ork_lib as L  # noqa: E402

YEREL = datetime.datetime.now().astimezone().tzinfo


def an(y, a, g, s=0, d=0):
    return datetime.datetime(y, a, g, s, d, tzinfo=YEREL)


class GunSinir(unittest.TestCase):
    def test_k1_bugun(self):
        self.assertEqual(L.gun_baslangici(1, an(2026, 10, 16, 9, 3)), an(2026, 10, 16))
        self.assertEqual(L.gun_baslangici(1, an(2026, 10, 16, 0, 5)), an(2026, 10, 16))
        self.assertEqual(L.gun_baslangici(1, an(2026, 10, 15, 23, 59)), an(2026, 10, 15))

    def test_k2_cok_gun_ve_kesirli(self):
        self.assertEqual(L.gun_baslangici(3, an(2026, 10, 16, 9, 3)), an(2026, 10, 14))
        self.assertEqual(L.gun_baslangici(0.5, an(2026, 10, 16, 12)), an(2026, 10, 16, 0))

    def test_k3_pencere_aritmetigi(self):
        simdi = an(2026, 10, 16, 9, 3)
        self.assertEqual(L.gun_baslangici(1, simdi), an(2026, 10, 16))
        dun, bugun = an(2026, 10, 15, 20), an(2026, 10, 16, 1)
        self.assertLess(dun, L.gun_baslangici(1, simdi))
        self.assertGreaterEqual(bugun, L.gun_baslangici(1, simdi))
        self.assertGreater(dun, simdi - datetime.timedelta(days=1))  # eski kayan pencere dünü içerirdi

    def test_k4_bugun_usd_yerel_gun(self):
        bugun = datetime.date.today()
        yerel = datetime.datetime.combine(bugun, datetime.time(0, 30), tzinfo=YEREL)
        dun = yerel - datetime.timedelta(minutes=40)
        kay = [{"zaman": yerel.isoformat(), "maliyet_usd": 1.0},
               {"zaman": yerel.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "maliyet_usd": 2.0},
               {"zaman": dun.isoformat(), "maliyet_usd": 4.0}]
        self.assertAlmostEqual(analitik.bugun_usd(kay), 3.0)


if __name__ == "__main__":
    unittest.main()
