"""Perspektif zaman ozeti (K8-K10): sentetik zaman.jsonl, gunluk.jsonl, isler.json ile gecici klasorde.
python -m pytest tests/test_perspektif_zaman.py
"""
import datetime
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import perspektif_zaman as Z  # noqa: E402

BIT = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.timezone.utc)


def iso(d):
    return d.isoformat()


class ZamanOrtam(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_pzaman_")
        self.zaman, self.gunluk, self.isler = [], [], {}

    def tur(self, bit, sure_sn, tur="ana", oturum="o1", is_="I-1"):
        self.zaman.append({"v": 1, "zaman": iso(bit), "oturum": oturum, "is": is_, "tur": tur,
                           "sure_ms": int(sure_sn * 1000)})

    def toplu(self, gun_once, sureler, **kw):
        for i, s in enumerate(sureler):
            self.tur(BIT - datetime.timedelta(days=gun_once, minutes=i), s, **kw)

    def yaz(self):
        with open(os.path.join(self.sd, "zaman.jsonl"), "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(o) + "\n" for o in self.zaman))
        with open(os.path.join(self.sd, "gunluk.jsonl"), "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(o) + "\n" for o in self.gunluk))
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump({"sayac": len(self.isler), "isler": self.isler}, f)

    def is_ekle(self, iid, guncelleme, durum="acik"):
        k = os.path.join(self.sd, "is_" + iid)
        os.makedirs(k, exist_ok=True)
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": iid, "guncelleme": iso(guncelleme)}, f)
        self.isler[iid] = {"klasor": k, "durum": durum, "olusturma": iso(guncelleme)}

    def ozet(self):
        self.yaz()
        return Z.ozet(self.sd, BIT - datetime.timedelta(days=14), BIT)

    def kurallar(self, r, kural):
        return [a for a in r["anomali"] if a["kural"] == kural]


class Yuzdelik(ZamanOrtam):
    def test_p95_nearest_rank(self):
        v = list(range(1, 101))
        self.assertEqual(Z.p_nr(v, 95), 95)
        self.assertEqual(Z.p_nr(v, 50), 50)
        self.assertEqual(Z.p_nr([10, 20, 30], 95), 30)
        self.assertEqual(Z.p_nr([7], 95), 7)
        self.assertIsNone(Z.p_nr([], 95))

    def test_ozet_p95_olcum(self):
        self.toplu(1, list(range(1, 101)))
        r = self.ozet()
        self.assertEqual(r["olcum"]["ana_tur"], {"adet": 100, "p50": 50, "p90": 90, "p95": 95})


class K8UzunTur(ZamanOrtam):
    def test_pozitif_pay_ustu(self):
        self.toplu(1, [60] * 30 + [3600] * 10)  # pay 10/40 = 0.25 > 0.10, taban esik 1800
        r = self.ozet()
        k8 = self.kurallar(r, "K8")
        self.assertEqual(len(k8), 1)
        self.assertEqual(k8[0]["n"], 40)
        self.assertEqual(k8[0]["pay"], 0.25)
        self.assertEqual(k8[0]["beklenen_pay"], 0.05)
        self.assertEqual(r["esik"]["uzun_tur_kaynak"], "taban")
        self.assertEqual(len(r["olcum"]["uzun_turlar"]), 10)

    def test_negatif_pay_altinda(self):
        self.toplu(1, [60] * 38 + [3600] * 2)  # pay 0.05
        self.assertEqual(self.kurallar(self.ozet(), "K8"), [])

    def test_sinir_tam_yuzde_on_susar(self):
        self.toplu(1, [60] * 36 + [3600] * 4)  # pay tam 0.10, buyuktur degil
        self.assertEqual(self.kurallar(self.ozet(), "K8"), [])

    def test_n_30_altinda_susar(self):
        self.toplu(1, [3600] * 20)  # pay 1.0 ama n=20
        r = self.ozet()
        self.assertEqual(self.kurallar(r, "K8"), [])
        self.assertEqual(r["olcum"]["ana_tur"]["adet"], 20)


class Esik(ZamanOrtam):
    def test_onceki_pencere_p95_esik(self):
        self.toplu(20, list(range(1, 101)))  # onceki pencere: 100 ornek, p95=95
        self.toplu(1, [60] * 40)
        r = self.ozet()
        self.assertEqual(r["esik"]["uzun_tur_sn"], 95)
        self.assertEqual(r["esik"]["uzun_tur_kaynak"], "onceki_pencere_p95")

    def test_ornek_30_altinda_taban(self):
        self.toplu(20, [10] * 29)  # onceki pencerede 29 ornek
        self.toplu(1, [60] * 40)
        r = self.ozet()
        self.assertEqual(r["esik"]["uzun_tur_sn"], 1800)
        self.assertEqual(r["esik"]["uzun_tur_kaynak"], "taban")


class K9Oturum(ZamanOrtam):
    def oturumlar(self, uzun, kisa):
        for i in range(uzun + kisa):
            sure = 20000 if i < uzun else 600
            self.tur(BIT - datetime.timedelta(days=2, minutes=i), sure, oturum="s%d" % i)

    def test_pozitif(self):
        self.oturumlar(uzun=8, kisa=32)  # 8/40 = 0.20 > 0.10, taban 14400
        k9 = self.kurallar(self.ozet(), "K9")
        self.assertEqual(len(k9), 1)
        self.assertEqual(k9[0]["pay"], 0.2)
        self.assertEqual(k9[0]["n"], 40)

    def test_negatif_pay_altinda(self):
        self.oturumlar(uzun=2, kisa=38)  # 0.05
        self.assertEqual(self.kurallar(self.ozet(), "K9"), [])

    def test_n_az_susar(self):
        self.oturumlar(uzun=20, kisa=0)
        self.assertEqual(self.kurallar(self.ozet(), "K9"), [])


class K10Surunme(ZamanOrtam):
    def test_pozitif_ve_negatif(self):
        self.is_ekle("I-10", BIT - datetime.timedelta(days=8))
        self.is_ekle("I-11", BIT - datetime.timedelta(days=2))
        self.is_ekle("I-12", BIT - datetime.timedelta(days=30), durum="kapandi")
        r = self.ozet()
        self.assertEqual([a["hedef"] for a in self.kurallar(r, "K10")], ["I-10"])
        self.assertEqual(r["olcum"]["is"]["acik"], 2)
        self.assertEqual(r["olcum"]["is"]["surunen_7gun"], 1)

    def test_tam_yedi_gun(self):
        self.is_ekle("I-20", BIT - datetime.timedelta(days=7))
        self.assertEqual(len(self.kurallar(self.ozet(), "K10")), 1)


class PencereRaporu(ZamanOrtam):
    def test_iki_pencere_pay_ve_anomali(self):
        self.toplu(1, [60] * 30 + [3600] * 10)  # son pencere: pay 0.25
        self.toplu(15, [60] * 40)  # onceki pencere: temiz
        self.yaz()
        rap = Z.pencere_raporu(self.sd, 14, 2, simdi=BIT)
        self.assertEqual(len(rap), 2)
        self.assertEqual(rap[0]["K8"]["pay"], 0.25)
        self.assertEqual(rap[0]["K8"]["anomali"], 1)
        self.assertEqual(rap[1]["K8"]["pay"], 0.0)
        self.assertEqual(rap[1]["K8"]["anomali"], 0)
        self.assertEqual(rap[1]["K8"]["beklenen_pay"], 0.05)
        self.assertEqual(rap[1]["K8"]["n"], 40)


class Gunluk(ZamanOrtam):
    def test_oturum_gunluk_kaydini_sayar(self):
        bit = BIT - datetime.timedelta(days=1)
        self.tur(bit, 60, oturum="uzun")
        self.gunluk.append({"zaman": iso(bit + datetime.timedelta(hours=6)), "oturum": "uzun", "tur": "istek"})
        self.yaz()
        r = Z.ozet(self.sd, BIT - datetime.timedelta(days=14), BIT)
        self.assertEqual(r["olcum"]["oturum"]["adet"], 1)
        self.assertGreaterEqual(r["olcum"]["oturum"]["p50"], 6 * 3600)


if __name__ == "__main__":
    unittest.main()
