"""I-224 P10: scripts/ret_olcum.py (Garwood üst sınırı, asgari gözlem, önce/sonra kararı) ve `orkestra hata ozet`."""
import datetime
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(AD, "..", "scripts"))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, AD)

import ret_nedeni as RN  # noqa: E402
import ret_olcum as RO  # noqa: E402
import ic_kos  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))
T0 = datetime.datetime(2026, 10, 22, 0, 0, tzinfo=TZ)
SINIR = datetime.datetime(2026, 10, 25, 0, 0, tzinfo=TZ)

K003 = "Orkestra (K-003): belge bağlantı satırı eksik"
K005 = "Orkestra (K-005): biçim ihlali"


def z(t0, i, adim_dk=1):
    return (t0 + datetime.timedelta(minutes=adim_dk * i)).isoformat(timespec="seconds")


def turlar(t0, n):
    return [{"zaman": z(t0, i), "tur": "ana"} for i in range(n)]


def red(t0, i, ileti, **ek):
    return {"kaynak": "davranis", "tur": "hook-red", "ileti": ileti, "zaman": z(t0, i), "sinif": "davranis", **ek}


def yaz(sd, ad, satirlar):
    with open(os.path.join(sd, ad), "w", encoding="utf-8") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


class Istatistik(unittest.TestCase):
    def test_garwood_bilinen_degerler(self):
        # chi2.ppf(0.95, 2(x+1))/2: 0 → 2.9957, 1 → 4.7439, 34 → 45.2656 (chi2.ppf(0.95,70)=90.531)
        self.assertAlmostEqual(RO.garwood_ust(0), 2.9957, places=3)
        self.assertAlmostEqual(RO.garwood_ust(1), 4.7439, places=3)
        self.assertAlmostEqual(RO.garwood_ust(34), 45.2656, places=2)
        self.assertGreater(RO.garwood_ust(2000), 2000)   # büyük x'te taşma yok

    def test_asgari_plan_tablosunu_uretir(self):
        for ad, (oran, beklenen) in RO.ASGARI_PLAN.items():
            self.assertEqual(RO.asgari(oran), beklenen, ad)
        self.assertIsNone(RO.asgari(0))

    def test_eski_satirdan_sinif_turetme(self):
        self.assertEqual(RO.sinif_turet({"ileti": K003}), "R1")
        self.assertEqual(RO.sinif_turet({"ileti": "iş onay bekliyor (P-016): ..."}), "R6")
        self.assertEqual(RO.sinif_turet({"ileti": "bu oturum bir işe bağlı değil; bağsız oturumda"}), "R6")
        self.assertEqual(RO.sinif_turet({"ileti": "git push (zorla)"}), RN.SINIFLANMAMIS)
        # P1 sonrası alanlar önceliklidir
        self.assertEqual(RO.sinif_turet({"ileti": K003, "kapi": "P-010"}), "R8")
        self.assertEqual(RO.sinif_turet({"ileti": K003, "ret_sinif": "R4"}), "R4")


class TekPencere(unittest.TestCase):
    def test_k1_dokuz_sinif_oran_ve_garwood_satiri(self):
        g = {"zaman": turlar(T0, 200),
             "hatalar": [red(T0, 1, K005), red(T0, 2, K005), red(T0, 3, "x", kapi="P-035", ret_sinif="R4"),
                         red(T0, 4, "git push (zorla)")],
             "denetimler": [{"zaman": z(T0, 5), "karar": "ret", "neden": "kanit-yok"},
                            {"zaman": z(T0, 6), "karar": "onay"}],
             "gunluk": []}
        o = RO.ozet(g)
        satir = {r["ad"]: r for r in o["siniflar"]}
        self.assertEqual(list(satir), [f"R{i}" for i in range(1, 10)] + [RN.SINIFLANMAMIS, RO.TOPLAM])
        for ad, r in satir.items():
            self.assertIsNotNone(r["oran_100"], ad)
            self.assertIsNotNone(r["ust_100"], ad)
            self.assertGreater(r["ust_100"], r["oran_100"], ad)
        self.assertEqual((satir["R1"]["ret"], satir["R1"]["payda"], satir["R1"]["oran_100"]), (2, 200, 1.0))
        self.assertAlmostEqual(satir["R1"]["ust_100"], 100 * RO.garwood_ust(2) / 200, places=2)
        self.assertEqual(satir["R2"]["ust_100"], round(100 * 2.9957 / 200, 2))   # 0 olay da satır alır
        self.assertEqual((satir["R5"]["ret"], satir["R5"]["payda"], satir["R5"]["birim"]), (1, 2, "karar"))
        self.assertEqual(satir[RN.SINIFLANMAMIS]["ret"], 1)
        self.assertEqual(satir[RO.TOPLAM]["ret"], 4)
        self.assertTrue(any(s.startswith("R9") for s in RO.metin(o)))

    def test_davranis_ihlal_ve_engelleyen_ayri(self):
        gun = [{"zaman": z(T0, 1), "tur": "kural_ihlal", "kural": "kimlik_once_bak", "mod": "block"},
               {"zaman": z(T0, 2), "tur": "kural_ihlal", "kural": "kimlik_once_bak", "mod": "golge"},
               {"zaman": z(T0, 3), "tur": "kapi_golge", "kapi": "cikti_butce"},
               {"zaman": z(T0, 4), "tur": "kural_ihlal", "kural": "konu_disi_oneri"},
               {"zaman": z(T0, 5), "tur": "kural_ihlal", "kural": "secim_ekrani", "mod": "golge"},
               {"zaman": z(T0, 6), "tur": "kural_ihlal", "kural": "kapanis_atlandi"}]
        o = RO.ozet({"zaman": turlar(T0, 100), "hatalar": [], "denetimler": [], "gunluk": gun})
        d = {r["ad"]: (r["ihlal"], r["engelleyen"]) for r in o["davranislar"]}
        self.assertEqual(d, {"kimlik": (2, 1), "butce": (1, 0), "konu_disi": (1, 0), "secim": (1, 0), "kapanis": (1, 1)})


class Karsilastirma(unittest.TestCase):
    def adr0040(self, sonra_tur):
        """ADR-0040 örneği: K-003 öncesi 34 ret / 852 tur, sonrası 0 ret."""
        hatalar = [red(T0, i * 10, K003) for i in range(34)] + [red(T0, i * 10 + 5, K005) for i in range(74)]
        return {"zaman": turlar(T0, 852) + turlar(SINIR, sonra_tur), "hatalar": hatalar, "denetimler": [], "gunluk": []}

    def test_k2_adr0040_etki_var(self):
        o = RO.ozet(self.adr0040(400), baslangic="2026-10-22T00:00:00+03:00", sonrasi=SINIR.isoformat())
        self.assertEqual((o["pencere"]["oncesi_tur"], o["pencere"]["sonrasi_tur"]), (852, 400))
        k = {r["ad"]: r for r in o["kapilar"]}["kapi:K-003"]
        self.assertEqual((k["oncesi"]["ret"], k["sonrasi"]["ret"]), (34, 0))
        self.assertLessEqual(k["asgari"], 400)
        self.assertEqual(k["karar"], "etki var")
        r1 = {r["ad"]: r for r in o["siniflar"]}["R1"]   # K-003 + K-005 = 108 → 0
        self.assertEqual(r1["karar"], "etki var")

    def test_k3_asgari_altinda_yetersiz_ornek(self):
        o = RO.ozet(self.adr0040(50), baslangic="2026-10-22T00:00:00+03:00", sonrasi=SINIR.isoformat())
        k = {r["ad"]: r for r in o["kapilar"]}["kapi:K-003"]
        self.assertGreater(k["asgari"], 50)
        self.assertEqual(k["karar"], "yetersiz örnek")
        den = {r["ad"]: r for r in o["kapilar"]}["denetci_kb_ky"]
        self.assertEqual(den["karar"], "taban yok")

    def test_etki_yok(self):
        g = self.adr0040(852)
        g["hatalar"] += [red(SINIR, i * 20, K003) for i in range(34)]   # sonrası aynı oran
        o = RO.ozet(g, baslangic="2026-10-22T00:00:00+03:00", sonrasi=SINIR.isoformat())
        self.assertEqual({r["ad"]: r for r in o["kapilar"]}["kapi:K-003"]["karar"], "etki yok")

    def test_denetci_150_karar_asgarisi(self):
        den = [{"zaman": z(T0, i), "karar": "ret" if i < 15 else "onay", "neden": "kanit-yok"} for i in range(241)]
        den += [{"zaman": z(SINIR, i), "karar": "onay"} for i in range(149)]
        o = RO.ozet({"zaman": [], "hatalar": [], "gunluk": [], "denetimler": den}, sonrasi=SINIR.isoformat())
        r = {r["ad"]: r for r in o["kapilar"]}["denetci_kb_ky"]
        self.assertEqual((r["asgari"], r["karar"]), (150, "yetersiz örnek"))
        den.append({"zaman": z(SINIR, 200), "karar": "onay"})
        o = RO.ozet({"zaman": [], "hatalar": [], "gunluk": [], "denetimler": den}, sonrasi=SINIR.isoformat())
        self.assertEqual({r["ad"]: r for r in o["kapilar"]}["denetci_kb_ky"]["karar"], "etki var")


class UretimEnjeksiyonu(unittest.TestCase):
    """ADR-0111: `uretim_enjekte` günlük kayıtları belge türü başına sayılır; ön/son penceresine göre ayrılır."""

    def test_enjeksiyon_belge_turu_ve_pencere(self):
        gun = [{"zaman": z(T0, 1), "tur": "uretim_enjekte", "belge": "plan"},
               {"zaman": z(SINIR, 1), "tur": "uretim_enjekte", "belge": "plan"},
               {"zaman": z(SINIR, 2), "tur": "uretim_enjekte", "belge": "todo"},
               {"zaman": z(SINIR, 3), "tur": "kural_ihlal", "kural": "kimlik_once_bak"}]
        girdi = {"zaman": turlar(T0, 10) + turlar(SINIR, 10), "hatalar": [], "denetimler": [], "gunluk": gun}
        o = RO.ozet(girdi, baslangic="2026-10-22T00:00:00+03:00", sonrasi=SINIR.isoformat())
        self.assertEqual(o["enjeksiyon"], {"oncesi": {"plan": 1}, "sonrasi": {"plan": 1, "todo": 1}})
        self.assertTrue(any("üretim anı enjeksiyonu" in s for s in RO.metin(o)))
        t = RO.ozet(girdi)
        self.assertEqual(t["enjeksiyon"], {"plan": 2, "todo": 1})

    def test_enjeksiyon_yoksa_bos(self):
        o = RO.ozet({"zaman": turlar(T0, 5), "hatalar": [], "denetimler": [], "gunluk": []})
        self.assertEqual(o["enjeksiyon"], {})


class Komut(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.proje = self.t.name
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)

    def kos(self, *a):
        return ic_kos.kos([os.path.join(SCRIPTS, "orkestra.py"), *a], cwd=self.proje)

    def test_ozet_json_ve_metin_salt_okur(self):
        yaz(self.sd, "zaman.jsonl", turlar(T0, 100) + [{"zaman": z(T0, 1), "tur": "alt"}])
        yaz(self.sd, "hata.jsonl", [red(T0, 1, K005), {"kaynak": "cli", "tur": "CliHata", "ileti": "m", "zaman": z(T0, 2)}])
        yaz(self.sd, "gunluk.jsonl", [{"zaman": z(T0, 3), "tur": "kural_ihlal", "kural": "kapanis_atlandi"}])
        once = sorted(os.listdir(self.sd))
        r = self.kos("hata", "ozet", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout)
        s = {x["ad"]: x for x in o["siniflar"]}
        self.assertEqual((s["R1"]["ret"], s["R1"]["payda"], s[RO.TOPLAM]["ret"]), (1, 100, 1))
        r = self.kos("hata", "ozet", "--baslangic", "2026-10-22T00:00:00+03:00", "--sonrasi", "2026-10-22T00:50:00+03:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("R1", r.stdout)
        self.assertIn("yetersiz örnek", r.stdout)
        r = self.kos("hata", "en-cok", "--gun", "0")   # mevcut alt komut bozulmadı
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(os.listdir(self.sd)), once)


if __name__ == "__main__":
    unittest.main()


class EszamanliKol(unittest.TestCase):
    def test_oturumlar_kola_ayrilir_ve_ret_kola_yazilir(self):
        import ret_olcum as R
        z = "2026-10-31T10:00:00Z"
        gun = [{"zaman": z, "tur": "uretim_enjekte", "oturum": "a", "belge": "plan"},
               {"zaman": z, "tur": "uretim_kontrol", "oturum": "b", "belge": "plan"},
               {"zaman": z, "tur": "uretim_kontrol", "oturum": "c", "belge": "plan"},
               {"zaman": z, "tur": "kapi_ret", "oturum": "b", "kapi": "K-005"},
               {"zaman": z, "tur": "kapi_ret", "oturum": "c", "kapi": "K-005"},
               {"zaman": z, "tur": "kapi_ret", "oturum": "z", "kapi": "K-005"}]  # kolsuz oturum sayılmaz
        k = R.kol_say(gun)
        self.assertEqual((k["enjeksiyon"]["oturum"], k["enjeksiyon"]["ret"]), (1, 0))
        self.assertEqual((k["kontrol"]["oturum"], k["kontrol"]["ret"]), (2, 2))

    def test_kontrol_yokken_metin_tek_kollu_der(self):
        import ret_olcum as R
        o = R.ozet({"gunluk": [], "zaman": [], "hatalar": [], "denetimler": []})
        self.assertTrue(any("kontrol kolu: yok" in s for s in R.metin(o)))
