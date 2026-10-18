"""I-067: scripts/metrikler.py `hesapla` (kpi.olcum çıktısındaki `verim` bölümü).

Elle kurulmuş iki kart ve bir iptal kartla her ölçü için bilinen sonuç:
  G-001 onaylı, 30 dk, ilk denetim onay, geçmişinde `beklemede` (60 sn sonra devam)
  G-002 onaylı, 2 sa, ilk denetim ret sonra onay, 2 işçi
  G-003 iptal; maliyeti tam maliyete girer, hiçbir orana girmez
"""
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import metrikler as M  # noqa: E402


def z(sa, dk=0, sn=0):
    return f"2026-03-10T{sa:02d}:{dk:02d}:{sn:02d}+03:00"


def kart(id_, durum, bas, bit, kararlar, isciler=1, ek=()):
    gecmis = [{"zaman": bas, "olay": "olusturuldu"}] + list(ek)
    if bit:
        gecmis.append({"zaman": bit, "olay": "teslim"})
    return {"id": id_, "durum": durum, "olusturma": bas, "gecmis": gecmis,
            "denetimler": [{"karar": k} for k in kararlar], "isciler": [f"a{i}" for i in range(isciler)]}


def satir(gorev, usd, giris=100, cikis=10, okuma=0, yazma=0, ajan="orkestra:isci-t2", model="claude-sonnet-5-5", **ek):
    return dict({"gorev": gorev, "maliyet_usd": usd, "giris": giris, "cikis": cikis, "onbellek_okuma": okuma,
                 "onbellek_yazma": yazma, "ajan": ajan, "model": model, "zaman": z(10)}, **ek)


KARTLAR = [
    kart("G-001", "onaylandi", z(9), z(9, 30), ["onay"], ek=[{"zaman": z(9, 10), "olay": "beklemede"},
                                                             {"zaman": z(9, 11), "olay": "isleniyor"}]),
    kart("G-002", "teslim", z(8), z(10), ["ret", "onay"], isciler=2),
    kart("G-003", "iptal", z(8), None, [], isciler=1),
]
SATIRLAR = [
    satir("G-001", 1.0),
    satir("G-002", 2.0, ajan="orkestra:denetci", model="claude-opus-5-5"),
    satir("G-003", 0.5),
    satir("-", 4.0, ajan="ana-ajan", sure_ms=60000, agent_id=None),
]


class MetrikTest(unittest.TestCase):
    def hesap(self, **kw):
        a = dict(tum_kartlar=KARTLAR, satirlar=SATIRLAR, zaman_satirlari=[], onay_bekleme_sn=[], saat=4.0)
        a.update(kw)
        return M.hesapla(**a)

    def test_basari_orani_iptal_disarida(self):
        v = self.hesap()["basari_orani"]
        self.assertEqual((v["pay"], v["payda"], v["deger"]), (2, 2, 1.0))

    def test_tam_maliyet_basarisiz_denemeler_dahil(self):
        v = self.hesap()["tam_maliyet_usd"]
        self.assertEqual(v["pay"], 3.5)       # 1.0 + 2.0 + iptal kartın 0.5; ana ajan (4.0) dahil değil
        self.assertEqual(v["deger"], 1.75)    # / 2 onaylı kart

    def test_tam_token(self):
        v = self.hesap()["tam_token"]
        self.assertEqual((v["pay"], v["payda"]), (330, 2))   # 3 kart x (100 + 10)

    def test_gecikme_p50_p95(self):
        g = self.hesap()["gecikme"]
        self.assertEqual((g["p50_sn"], g["p95_sn"], g["n"]), ((1800 + 7200) / 2, 7200, 2))

    def test_goodput_esik_icindekiler(self):
        v = self.hesap(esik_sn=3600)["goodput_saat"]
        self.assertEqual((v["pay"], v["deger"]), (1, 0.25))   # yalnız G-001 (30 dk) eşik içinde; 1 kart / 4 saat
        v = self.hesap(esik_sn=8000)["goodput_saat"]
        self.assertEqual((v["pay"], v["deger"]), (2, 0.5))

    def test_goodput_pencere_sifir_none(self):
        self.assertIsNone(self.hesap(saat=0)["goodput_saat"]["deger"])

    def test_ilk_deneme(self):
        v = self.hesap()["ilk_deneme"]
        self.assertEqual((v["pay"], v["payda"], v["deger"]), (1, 2, 0.5))

    def test_insan_mudahale_oran_ve_sure(self):
        v = self.hesap()["insan_mudahale"]
        self.assertEqual((v["pay"], v["payda"]), (1, 2))
        self.assertEqual(v["sure_sn"]["medyan"], 60.0)   # beklemede 09:10 -> sonraki olay 09:11

    def test_cagri_ve_retry(self):
        c = self.hesap(zaman_satirlari=[{"tur": "arac", "sure_ms": 1000}, {"tur": "tur"}])["cagri"]
        self.assertEqual(c["arac_cagrisi"], 1)
        self.assertEqual(c["isci_cagrisi_kart"]["pay"], 3)
        self.assertEqual(c["ek_isci_cagrisi"], 1)

    def test_kirilim_toplamlari_defter_toplamina_esit(self):
        v = self.hesap()
        defter = sum(r["maliyet_usd"] for r in SATIRLAR)
        for anahtar in ("model_kirilim", "rol_kirilim"):
            top = sum(e["usd"]["toplam"] for e in v[anahtar].values())
            self.assertAlmostEqual(top, defter, delta=0.05)  # kalem toplamı liste fiyatından türetilir
            self.assertEqual(sum(e["satir"] for e in v[anahtar].values()), len(SATIRLAR))

    def test_sure_kirilim_duvar_saati_paralel_toplamaz(self):
        paralel = [satir("G-001", 1, sure_ms=600000, agent_id="a", zaman=z(10, 10)),
                   satir("G-002", 1, sure_ms=600000, agent_id="b", zaman=z(10, 10))]
        k = self.hesap(satirlar=SATIRLAR + paralel, zaman_satirlari=[{"tur": "arac", "sure_ms": 2500}],
                       onay_bekleme_sn=[30])["sure_kirilim"]
        self.assertEqual(k["isci_toplam_sn"], 1200.0)
        self.assertEqual(k["isci_duvar_sn"], 600.0)
        self.assertEqual(k["orkestrasyon_sn"], 60.0)
        self.assertEqual(k["arac_sn"], 2.5)
        self.assertEqual(k["insan_bekleme_sn"], 90.0)    # 30 onay bekleme + 60 müdahale

    def test_onbellek_isabet(self):
        v = self.hesap(satirlar=[satir("G-001", 1, giris=100, okuma=300, yazma=100)])["onbellek_isabet"]
        self.assertEqual((v["pay"], v["payda"], v["deger"]), (300, 500, 0.6))

    def test_yukseltme_orani(self):
        kartlar = [dict(KARTLAR[0], baslangic_basamak="T1", basamak="T2"), KARTLAR[1]]
        v = self.hesap(tum_kartlar=kartlar)["yukseltme"]
        self.assertEqual((v["pay"], v["payda"], v["deger"]), (1, 2, 0.5))
        olayli = dict(KARTLAR[1], gecmis=KARTLAR[1]["gecmis"] + [{"zaman": z(9), "olay": "yukseltme"}])
        self.assertEqual(self.hesap(tum_kartlar=[olayli])["yukseltme"]["pay"], 1)

    def test_bos_veri_none(self):
        v = M.hesapla([], [], [], [], 0.0)
        self.assertIsNone(v["basari_orani"]["deger"])
        self.assertIsNone(v["gecikme"]["p50_sn"])
        self.assertIsNone(v["tam_maliyet_usd"]["deger"])

    def test_birlesim_ic_ice_ve_bitisik(self):
        import datetime
        t = datetime.datetime(2026, 3, 10, 10, tzinfo=datetime.timezone.utc)
        d = lambda a, b: (t + datetime.timedelta(seconds=a), t + datetime.timedelta(seconds=b))  # noqa: E731
        self.assertEqual(M._birlesim_sn([d(0, 100), d(10, 50), d(90, 150), d(200, 210)]), 160.0)


if __name__ == "__main__":
    unittest.main()
