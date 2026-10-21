"""I-137 P2: panelin pencere seçimine bağlı sunucu alanları (pencere başına usd/token) defter toplamıyla tutar (K-002)."""
import datetime
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import analitik as A  # noqa: E402
import is_kaydi as IK  # noqa: E402
import ork_lib as L  # noqa: E402
import ozet as O  # noqa: E402
import panel  # noqa: E402

BUGUN = datetime.date.today()
PENCERELER = L.PENCERELER


def zaman(gun_once: int, saat: int = 12) -> str:
    d = datetime.datetime.combine(BUGUN - datetime.timedelta(days=gun_once), datetime.time(saat, 0)).astimezone()
    return d.isoformat(timespec="seconds")


def satir(gun_once, usd, tok, gorev="G-1", saat=12, **ek):
    return {"zaman": zaman(gun_once, saat), "maliyet_usd": usd, "giris": tok, "cikis": 0, "onbellek_okuma": 0,
            "onbellek_yazma": 0, "gorev": gorev, "model": "claude-sonnet-5-5", "surec": "is", "ajan": "orkestra:isci-t2", **ek}


KAYITLAR = [satir(0, 1.0, 100, saat=9), satir(1, 2.0, 200), satir(2, 4.0, 400, gorev="G-2"), satir(5, 8.0, 800),
            satir(25, 16.0, 1600, gorev="G-2"), satir(70, 32.0, 3200)]


def ay_icinde(gun_once):
    return (BUGUN - datetime.timedelta(days=gun_once)).month == BUGUN.month


class PencereToplamlari(unittest.TestCase):
    def test_pencere_toplamlari_takvim_gunu(self):
        t = L.pencere_toplamlari(KAYITLAR, BUGUN)
        self.assertEqual(t["bugun"], {"usd": 1.0, "token": 100})
        self.assertEqual(t["son_3_gun"]["usd"], 7.0)
        self.assertEqual(t["son_7_gun"]["usd"], 15.0)
        self.assertEqual(t["tum_zaman"]["usd"], 63.0)
        self.assertEqual(t["tum_zaman"]["token"], 6300)
        bu_ay = sum(r["maliyet_usd"] for r, g in zip(KAYITLAR, (0, 1, 2, 5, 25, 70)) if ay_icinde(g))
        self.assertAlmostEqual(t["bu_ay"]["usd"], bu_ay)

    def test_anahtarli_toplam_kart_basina(self):
        t = L.pencere_toplamlari(KAYITLAR, BUGUN, lambda r: r.get("gorev"))
        self.assertEqual(set(t), {"G-1", "G-2"})
        self.assertEqual(t["G-2"]["son_3_gun"]["usd"], 4.0)
        self.assertEqual(t["G-2"]["tum_zaman"]["usd"], 20.0)
        for w in PENCERELER:
            self.assertAlmostEqual(sum(v[w]["usd"] for v in t.values()), L.pencere_toplamlari(KAYITLAR, BUGUN)[w]["usd"])

    def test_onceki_aralik_ayni_uzunlukta(self):
        for w in ("bugun", "son_3_gun", "son_7_gun"):
            bas, bit = L.onceki_aralik(w, BUGUN)
            self.assertEqual((bit - bas).days + 1, L.pencere_gun_sayisi(w, BUGUN))
        self.assertIsNone(L.onceki_aralik("tum_zaman", BUGUN))
        self.assertIsNone(L.pencere_gun_sayisi("tum_zaman", BUGUN))


class OzetPencere(unittest.TestCase):
    def test_kirilim_usd_ve_token_pencere_toplamiyla_ayni(self):
        k = O._pencere_kirilimlari(KAYITLAR, BUGUN)
        t = L.pencere_toplamlari(KAYITLAR, BUGUN)
        for w in PENCERELER:
            self.assertAlmostEqual(k[w]["usd"], t[w]["usd"], places=3)
            self.assertEqual(k[w]["token"], t[w]["token"])
        self.assertEqual(k["son_3_gun"]["gun"], 3)
        self.assertEqual(k["bugun"]["onceki"]["usd"], 2.0)   # dün
        self.assertEqual(k["son_3_gun"]["onceki"]["usd"], 8.0)   # önceki 3 gün = bugün-5..bugün-3: yalnız 5 gün önceki satır
        self.assertIsNone(k["tum_zaman"]["onceki"])


class AnalitikPencere(unittest.TestCase):
    def test_saatlik_toplam_bugunku_toplam(self):
        tr = A._trend(KAYITLAR, BUGUN)
        self.assertEqual(len(tr["saatlik"]), 24)
        self.assertAlmostEqual(sum(h["usd"] for h in tr["saatlik"]), 1.0)
        self.assertEqual(sum(h["token"] for h in tr["saatlik"]), 100)
        self.assertEqual(tr["saatlik"][9]["usd"], 1.0)

    def test_pencereli_kart_sayilari_ve_en_pahali(self):
        kartlar = [{"id": "G-1", "durum": "teslim", "olusturma": zaman(0), "basamak": "T2", "denetimler": [], "gecmis": []},
                   {"id": "G-2", "durum": "teslim", "olusturma": zaman(25), "basamak": "T2", "denetimler": [], "gecmis": []}]
        with mock.patch.object(L, "kart_durumu_hesapla", lambda k: k["durum"]):
            p = A._pencereli(kartlar, KAYITLAR, [{"id": "G-1", "olusturma": zaman(0), "toplam_dk": 10, "kuyruk_dk": 1, "is_dk": 1,
                                                   "denetim_bekleme_dk": 1, "denetim_calisma_dk": 1, "denetim_toplam_dk": 2}], BUGUN)
        self.assertEqual(p["bugun"]["kart_sayisi"], 1)
        self.assertEqual(p["tum_zaman"]["kart_sayisi"], 2)
        self.assertEqual(p["bugun"]["en_pahali"], [["G-1", 1.0]])
        self.assertEqual(p["son_3_gun"]["en_pahali"], [["G-2", 4.0], ["G-1", 3.0]])   # sıra pencerede kalan harcamaya göre
        self.assertEqual(p["tum_zaman"]["en_pahali_token"][0], ["G-1", 4300])
        self.assertEqual(p["bugun"]["birim"]["teslim_kart"], 1)
        self.assertEqual(p["bugun"]["akis_ozet"]["kart"], 1)
        self.assertEqual(p["son_3_gun"]["akis_ozet"]["kart"], 1)

    def test_akis_satirinda_penceresi_listesi(self):
        kartlar = [{"id": "G-1", "durum": "teslim", "olusturma": zaman(0), "basamak": "T2", "denetimler": [], "gecmis": []},
                   {"id": "G-2", "durum": "teslim", "olusturma": zaman(25), "basamak": "T2", "denetimler": [], "gecmis": []}]
        with mock.patch.object(L, "maliyet_kayitlari", lambda sd: KAYITLAR), mock.patch.object(L, "kartlar", lambda sd, derin=True: kartlar), \
                mock.patch.object(L, "sohbetler", lambda *a, **k: []), mock.patch.object(L, "kart_durumu_hesapla", lambda k: k["durum"]):
            a = A.olustur("x", "x")
        satirlar = {r["id"]: r for r in a["akis"]["kartlar"]}
        self.assertEqual(satirlar["G-1"]["penceresi"], list(PENCERELER))
        self.assertEqual(satirlar["G-2"]["penceresi"], ["bu_ay", "tum_zaman"] if ay_icinde(25) else ["tum_zaman"])


class IsKaydiPencere(unittest.TestCase):
    def test_is_ve_kart_pencere_toplamlari_defterle_tutar(self):
        kartlar = [{"id": "G-1", "is": "I-1"}, {"id": "G-2", "is": "I-1"}]
        with mock.patch.object(L, "maliyet_kayitlari", lambda sd: KAYITLAR):
            ip = IK.is_pencere_toplamlari("x", kartlar, BUGUN)
            kp = IK.kart_pencere_toplamlari("x", BUGUN)
            usd, _ = IK.is_usd_ve_harcama_son("x", kartlar)
        self.assertAlmostEqual(ip["I-1"]["tum_zaman"]["usd"], usd["I-1"])
        for w in PENCERELER:
            self.assertAlmostEqual(ip["I-1"][w]["usd"], kp["G-1"][w]["usd"] + kp["G-2"][w]["usd"])


class IslerJson(unittest.TestCase):
    def test_isler_json_pencere_alani_tum_zaman_usd_ile_ayni(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        alan = {"id": "alan-x", "ad": "proje", "yol": t.name, "orkestra": True, "sohbet": 1, "son": "x"}
        kartlar = [{"id": "G-1", "is": "I-1", "durum": "teslim", "baslik": "a", "olusturma": zaman(3)},
                   {"id": "G-3", "durum": "isleniyor", "baslik": "kartsız", "olusturma": zaman(1)}]
        kayit = KAYITLAR + [satir(0, 0.5, 50, gorev="G-3")]
        iss = [{"id": "I-1", "baslik": "iş bir", "durum": "acik", "klasor": ""}]
        with mock.patch.object(L, "calisma_alanlari", lambda: [alan]), mock.patch.object(L, "maliyet_kayitlari", lambda sd: kayit), \
                mock.patch.object(L, "kartlar", lambda sd, derin=True: kartlar), mock.patch.object(IK, "is_liste", lambda sd: iss), \
                mock.patch.object(IK, "sifirlama_zamani", lambda sd: ""):
            j = panel._isler_json("alan-x")
        i = j["isler"][0]
        self.assertAlmostEqual(i["pencere"]["tum_zaman"]["usd"], i["usd"])
        self.assertEqual(i["pencere"]["bugun"]["usd"], 1.0)
        self.assertEqual(j["kartsiz"]["acik"][0]["pencere"]["bugun"], {"usd": 0.5, "token": 50})
        self.assertEqual(j["kartsiz"]["acik"][0]["pencere"]["tum_zaman"]["usd"], j["kartsiz"]["acik"][0]["usd"])


if __name__ == "__main__":
    unittest.main()
