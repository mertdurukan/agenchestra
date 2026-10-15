"""G-069 (E1): scripts/etki.py vaat/taban/günlük izleme çekirdeği.

Sözleşme (testin tanımladığı arayüz; kaynak: 008-etki-olcumlu-onay/plan.md):
  gidisat(taban_deger, birikim_deger, birikim_ornek, yon, esik) -> 'iyi'|'kotu'|'etkisiz'|'yetersiz-veri'
    esik = {"goreli": 0.10, "min_ornek": 20}; yon = azalmali|artmali|degismemeli.
    Önce veri kontrolü: taban None/0, birikim_deger None, birikim_ornek < min_ornek -> yetersiz-veri.
    fark = (birikim - taban) / taban. |fark| < goreli -> etkisiz (degismemeli yönünde 'iyi').
    Eşik üstünde doğru yön -> iyi, ters yön -> kotu. degismemeli: eşik üstü her sapma -> kotu.
  Tarihler datetime.date. Gün = yerel takvim günü. 'bugun' verilmezse bugünün tarihi.
  Onay kaydı: "vaat" (metin, olculebilir, metrik, yon, esik, kapsam) ve "etki"
    (taban{zaman,deger,ornek}, uygulama_dogrulama{gecti,kanit}, uygulama_tarihi 'YYYY-MM-DD', gunluk[],
     izleme{durum: suruyor|kapandi|geri-alindi, baslangic, kapanis, son_gidisat, ayni_gidisat_gun},
     karar{sonuc,not,zaman}|None, durum: 'olculemez' (ölçülemeyen kayıt), soru_bekliyor: bool).
  Günlük satır: gun (1'den), tarih, gunluk_deger, gunluk_ornek, birikim_deger, birikim_ornek, fark_goreli,
    gidisat, karisik (aynı uygulama gününde uygulanan DİĞER onay kimlikleri; yoksa boş/eksik).
    gun 1 = uygulama günü; uygulama gününden ÖNCEKİ günlerin verisi hiçbir satıra girmez.
  Olay günlüğü onaylar/etki.jsonl: her satır JSON, {"zaman", "onay": <oid>, "olay": ...}. Olaylar:
    vaat-yazildi, taban-alindi, uygulama-dogrulandi, gunluk-olcum (her eklenen gün satırı için bir tane),
    gidisat-degisti, izleme-kapandi, geri-alindi.
  Örnek sayısı (kpi:ret_orani için): denetim kararı sayısı (testlerde kart başına 1 karar).
  dogru_karar_orani(sd) -> {"dogru","yanlis","belirsiz","kapatilan","oran"}; oran = dogru/(dogru+yanlis),
    yalnız kapatılmış izlemelerden; payda 0 ise None.
  liste(sd) -> vaat ya da etki alanı olan onay kayıtları (dict listesi, "id" ile).
"""
import datetime
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import onay  # noqa: E402

try:
    import etki  # noqa: E402
except ImportError:  # kırmızı aşama: modül yok
    etki = None

D0 = datetime.date(2026, 3, 10)
ESIK = {"goreli": 0.10, "min_ornek": 20}
VAAT = {"metin": "Ret oranı azalır", "olculebilir": True, "metrik": "kpi:ret_orani", "yon": "azalmali"}


def gun_z(gun: datetime.date) -> str:
    return f"{gun.isoformat()}T12:00:00+03:00"


class Temel(unittest.TestCase):
    sayac = 0

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.sd = os.path.join(self.t.name, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "gorevler"))
        os.makedirs(os.path.join(self.sd, "onaylar"))
        self.sira = 0

    def tearDown(self):
        self.t.cleanup()

    # --- veri kurucular
    def kartlar_ekle(self, gun, ret, onay_):
        """gun günü öğlen oluşturulmuş, her biri tek denetim kararlı kartlar."""
        for karar in ["ret"] * ret + ["onay"] * onay_:
            self.sira += 1
            gid = f"G-{self.sira:03d}"
            kart = {"id": gid, "baslik": "x", "sinif": "kod", "basamak": "T2", "baslangic_basamak": "T2",
                    "durum": "teslim", "olusturma": gun_z(gun),
                    "gecmis": [{"zaman": gun_z(gun), "olay": "olusturuldu", "basamak": "T2"}],
                    "isciler": [gid + "-i0"],
                    "denetimler": [{"zaman": gun_z(gun), "sira": 1, "karar": karar, "ajan": "orkestra:denetci"}]}
            for ad, v in ((gid + ".json", kart), (gid + ".denetim.json", kart["denetimler"])):
                with open(os.path.join(self.sd, "gorevler", ad), "w", encoding="utf-8") as f:
                    json.dump(v, f)

    def taban_kartlari(self, tarih=None):
        """Taban: 10 kart, 5 ret -> ret_orani 0.5 (uygulamadan 3 gün önce)."""
        self.kartlar_ekle((tarih or D0) - datetime.timedelta(days=3), 5, 5)

    def kayit(self, vaat=VAAT, uygulama=D0, taban=True, durum="uygulandi"):
        k = onay.iste(self.sd, "Soru", "Metin")
        oid = k["id"]
        if vaat is not None:
            etki.vaat_ayarla(self.sd, oid, dict(vaat))
        if taban:
            etki.taban_al(self.sd, oid, bugun=uygulama)
        self.kayit_degistir(oid, uygulama, durum)
        return oid

    def kayit_degistir(self, oid, uygulama, durum="uygulandi"):
        yol = os.path.join(self.sd, "onaylar", oid + ".json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        k["durum"] = durum
        if uygulama is not None:
            k.setdefault("etki", {})["uygulama_tarihi"] = uygulama.isoformat()
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)

    def oku(self, oid):
        with open(os.path.join(self.sd, "onaylar", oid + ".json"), encoding="utf-8") as f:
            return json.load(f)

    def olaylar(self, olay=None, oid=None):
        yol = os.path.join(self.sd, "onaylar", "etki.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            satirlar = [json.loads(s) for s in f if s.strip()]
        return [s for s in satirlar if (olay is None or s["olay"] == olay) and (oid is None or s["onay"] == oid)]

    def jsonl_ham(self):
        yol = os.path.join(self.sd, "onaylar", "etki.jsonl")
        if not os.path.exists(yol):
            return b""
        with open(yol, "rb") as f:
            return f.read()

    def gun(self, n):
        return D0 + datetime.timedelta(days=n)


class EtkiVar(unittest.TestCase):
    def test_modul_yuklenir(self):
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")


# ------------------------------------------------------------------ kriter 1: gidisat()

class GidisatTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")

    def g(self, taban, birikim, n, yon="azalmali"):
        return etki.gidisat(taban, birikim, n, yon, ESIK)

    def test_azalmali_belirgin_dusus_iyi(self):
        self.assertEqual(self.g(0.5, 0.4, 30), "iyi")

    def test_azalmali_ters_yon_kotu(self):
        self.assertEqual(self.g(0.5, 0.6, 30), "kotu")

    def test_artmali_artis_iyi_dusus_kotu(self):
        self.assertEqual(self.g(0.5, 0.6, 30, "artmali"), "iyi")
        self.assertEqual(self.g(0.5, 0.4, 30, "artmali"), "kotu")

    def test_esik_ici_etkisiz(self):
        self.assertEqual(self.g(0.5, 0.52, 30), "etkisiz")
        self.assertEqual(self.g(0.5, 0.48, 30, "artmali"), "etkisiz")

    def test_esik_siniri_iki_yani(self):
        # göreli fark 0.11 (eşiğin üstü) -> iyi; 0.09 (altı) -> etkisiz
        self.assertEqual(self.g(1.0, 0.89, 30), "iyi")
        self.assertEqual(self.g(1.0, 0.91, 30), "etkisiz")
        self.assertEqual(self.g(1.0, 1.11, 30, "artmali"), "iyi")
        self.assertEqual(self.g(1.0, 1.09, 30, "artmali"), "etkisiz")

    def test_degismemeli(self):
        self.assertEqual(self.g(0.5, 0.52, 30, "degismemeli"), "iyi")
        self.assertEqual(self.g(0.5, 0.6, 30, "degismemeli"), "kotu")
        self.assertEqual(self.g(0.5, 0.4, 30, "degismemeli"), "kotu")

    def test_min_ornek_siniri(self):
        self.assertEqual(self.g(0.5, 0.4, 19), "yetersiz-veri")
        self.assertEqual(self.g(0.5, 0.4, 20), "iyi")
        self.assertEqual(self.g(0.5, 0.4, 0), "yetersiz-veri")

    def test_az_ornekte_ters_yon_da_yetersiz(self):
        self.assertEqual(self.g(0.5, 0.9, 5), "yetersiz-veri")

    def test_taban_yok_ya_da_sifir_yetersiz(self):
        self.assertEqual(self.g(None, 0.4, 30), "yetersiz-veri")
        self.assertEqual(self.g(0, 0.4, 30), "yetersiz-veri")
        self.assertEqual(self.g(0.0, 0.0, 30), "yetersiz-veri")

    def test_birikim_degeri_yok_yetersiz(self):
        self.assertEqual(self.g(0.5, None, 30), "yetersiz-veri")

    def test_ozel_esik_kullanilir(self):
        self.assertEqual(etki.gidisat(0.5, 0.4, 5, "azalmali", {"goreli": 0.10, "min_ornek": 5}), "iyi")
        self.assertEqual(etki.gidisat(0.5, 0.4, 30, "azalmali", {"goreli": 0.50, "min_ornek": 20}), "etkisiz")


# ------------------------------------------------------------------ vaat / taban / doğrulama

class VaatTabanTest(Temel):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")

    def test_vaat_yazilir_varsayilanlarla_ve_olay_duser(self):
        oid = onay.iste(self.sd, "S", "M")["id"]
        etki.vaat_ayarla(self.sd, oid, dict(VAAT))
        v = self.oku(oid)["vaat"]
        self.assertEqual(v["metrik"], "kpi:ret_orani")
        self.assertEqual(v["yon"], "azalmali")
        self.assertEqual(v["esik"]["goreli"], 0.10)
        self.assertEqual(v["esik"]["min_ornek"], 20)
        self.assertEqual(v["kapsam"], "genel")
        self.assertEqual(len(self.olaylar("vaat-yazildi", oid)), 1)

    def test_vaat_gecersiz_yon_ve_kimlik_reddedilir(self):
        oid = onay.iste(self.sd, "S", "M")["id"]
        with self.assertRaises(ValueError):
            etki.vaat_ayarla(self.sd, oid, dict(VAAT, yon="yukari"))
        with self.assertRaises(ValueError):
            etki.vaat_ayarla(self.sd, "O-999", dict(VAAT))
        self.assertNotIn("vaat", self.oku(oid))

    def test_esik_uygulamadan_sonra_degistirilemez(self):
        oid = self.kayit()
        with self.assertRaises(ValueError):
            etki.vaat_ayarla(self.sd, oid, dict(VAAT, esik={"goreli": 0.5, "min_ornek": 1}))
        self.assertEqual(self.oku(oid)["vaat"]["esik"]["goreli"], 0.10)

    def test_taban_uygulamadan_onceki_son_7_gunden(self):
        # pencere dışı: D-8 ve uygulama günü D; içinde: D-7 ve D-1 (toplam 10 kart, 4 ret -> 0.4)
        self.kartlar_ekle(D0 - datetime.timedelta(days=8), 5, 0)
        self.kartlar_ekle(D0, 0, 5)
        self.kartlar_ekle(D0 - datetime.timedelta(days=7), 2, 3)
        self.kartlar_ekle(D0 - datetime.timedelta(days=1), 2, 3)
        oid = onay.iste(self.sd, "S", "M")["id"]
        etki.vaat_ayarla(self.sd, oid, dict(VAAT))
        etki.taban_al(self.sd, oid, bugun=D0)
        t = self.oku(oid)["etki"]["taban"]
        self.assertAlmostEqual(t["deger"], 0.4)
        self.assertEqual(t["ornek"], 10)
        self.assertTrue(t["zaman"])
        self.assertEqual(len(self.olaylar("taban-alindi", oid)), 1)

    def test_taban_donar_ikinci_cagri_degistirmez(self):
        self.taban_kartlari()
        oid = onay.iste(self.sd, "S", "M")["id"]
        etki.vaat_ayarla(self.sd, oid, dict(VAAT))
        etki.taban_al(self.sd, oid, bugun=D0)
        ilk = self.oku(oid)["etki"]["taban"]
        self.kartlar_ekle(self.gun(5), 9, 1)  # sonradan gelen veri tabanı etkilememeli
        etki.taban_al(self.sd, oid, bugun=self.gun(8))
        self.assertEqual(self.oku(oid)["etki"]["taban"], ilk)
        self.assertEqual(len(self.olaylar("taban-alindi", oid)), 1)

    def test_taban_verisi_yoksa_deger_none(self):
        oid = onay.iste(self.sd, "S", "M")["id"]
        etki.vaat_ayarla(self.sd, oid, dict(VAAT))
        etki.taban_al(self.sd, oid, bugun=D0)
        t = self.oku(oid)["etki"]["taban"]
        self.assertIsNone(t["deger"])
        self.assertEqual(t["ornek"], 0)

    def test_uygulama_dogrula_yazilir(self):
        oid = self.kayit()
        etki.uygulama_dogrula(self.sd, oid, True, "satır yok: eski panel bilgisi")
        d = self.oku(oid)["etki"]["uygulama_dogrulama"]
        self.assertIs(d["gecti"], True)
        self.assertEqual(d["kanit"], "satır yok: eski panel bilgisi")
        self.assertEqual(len(self.olaylar("uygulama-dogrulandi", oid)), 1)
        etki.uygulama_dogrula(self.sd, oid, False, "satır duruyor")
        self.assertIs(self.oku(oid)["etki"]["uygulama_dogrulama"]["gecti"], False)


# ------------------------------------------------------------------ kriter 2, 3: günlük izleme

class IzleTest(Temel):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")
        self.taban_kartlari()

    def gunluk(self, oid):
        return self.oku(oid)["etki"]["gunluk"]

    def test_sinir_gunu_yalniz_uygulama_gunu_ve_sonrasi(self):
        oid = self.kayit()  # taban donduktan sonra gelen veri
        self.kartlar_ekle(D0 - datetime.timedelta(days=1), 15, 0)  # önceki gün: hepsi ret
        self.kartlar_ekle(D0, 2, 18)                               # gün 1: 20 kart, 2 ret
        self.kartlar_ekle(self.gun(1), 4, 16)                      # gün 2: 20 kart, 4 ret
        etki.izle(self.sd, oid, bugun=self.gun(1))
        g = self.gunluk(oid)
        self.assertEqual([x["gun"] for x in g], [1, 2])
        self.assertEqual([x["tarih"] for x in g], [D0.isoformat(), self.gun(1).isoformat()])
        self.assertEqual(g[0]["gunluk_ornek"], 20)
        self.assertAlmostEqual(g[0]["gunluk_deger"], 0.1)
        self.assertEqual(g[0]["birikim_ornek"], 20)
        self.assertAlmostEqual(g[0]["birikim_deger"], 0.1)
        self.assertAlmostEqual(g[0]["fark_goreli"], (0.1 - 0.5) / 0.5)
        self.assertEqual(g[0]["gidisat"], "iyi")
        self.assertAlmostEqual(g[1]["gunluk_deger"], 0.2)
        self.assertEqual(g[1]["birikim_ornek"], 40)
        self.assertAlmostEqual(g[1]["birikim_deger"], 0.15)

    def test_bugunden_sonraki_gun_verisi_girmez(self):
        self.kartlar_ekle(D0, 2, 18)
        self.kartlar_ekle(self.gun(3), 20, 0)
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=D0)
        g = self.gunluk(oid)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["birikim_ornek"], 20)

    def test_az_ornekte_yetersiz_veri_gunluk_deger_yine_gorunur(self):
        self.kartlar_ekle(D0, 1, 9)
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=D0)
        satir = self.gunluk(oid)[0]
        self.assertEqual(satir["gidisat"], "yetersiz-veri")
        self.assertAlmostEqual(satir["gunluk_deger"], 0.1)
        self.assertEqual(satir["birikim_ornek"], 10)

    def test_izle_iki_kez_satir_eklemez(self):
        self.kartlar_ekle(D0, 2, 18)
        self.kartlar_ekle(self.gun(1), 4, 16)
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=self.gun(1))
        once = self.oku(oid)["etki"]["gunluk"]
        ham = self.jsonl_ham()
        etki.izle(self.sd, oid, bugun=self.gun(1))
        self.assertEqual(self.oku(oid)["etki"]["gunluk"], once)
        self.assertEqual(self.jsonl_ham(), ham)
        self.assertEqual(len(self.olaylar("gunluk-olcum", oid)), 2)

    def test_atlanan_gunler_geriye_donuk_doldurulur(self):
        for n in range(6):
            self.kartlar_ekle(self.gun(n), 2, 8)
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=self.gun(1))
        self.assertEqual(len(self.gunluk(oid)), 2)
        etki.izle(self.sd, oid, bugun=self.gun(5))  # 2-4. günler atlandı
        g = self.gunluk(oid)
        self.assertEqual([x["gun"] for x in g], [1, 2, 3, 4, 5, 6])
        self.assertEqual([x["tarih"] for x in g], [self.gun(n).isoformat() for n in range(6)])
        self.assertTrue(all(x["gunluk_ornek"] == 10 for x in g))
        self.assertEqual(g[5]["birikim_ornek"], 60)
        self.assertEqual(len(self.olaylar("gunluk-olcum", oid)), 6)

    def test_oid_verilmezse_tum_kayitlar_izlenir(self):
        self.kartlar_ekle(D0, 2, 18)
        a = self.kayit(uygulama=D0)
        b = self.kayit(uygulama=D0)
        etki.izle(self.sd, None, bugun=D0)
        self.assertEqual(len(self.gunluk(a)), 1)
        self.assertEqual(len(self.gunluk(b)), 1)

    def test_izleme_alani_ve_gidisat_degisti_olayi(self):
        self.kartlar_ekle(D0, 1, 9)        # gün 1: n=10 yetersiz-veri
        self.kartlar_ekle(self.gun(1), 1, 9)  # gün 2: n=20 -> 0.1 -> iyi
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=D0)
        iz = self.oku(oid)["etki"]["izleme"]
        self.assertEqual(iz["durum"], "suruyor")
        self.assertEqual(iz["baslangic"], D0.isoformat())
        self.assertEqual(iz["son_gidisat"], "yetersiz-veri")
        etki.izle(self.sd, oid, bugun=self.gun(1))
        iz = self.oku(oid)["etki"]["izleme"]
        self.assertEqual(iz["son_gidisat"], "iyi")
        self.assertEqual(iz["ayni_gidisat_gun"], 1)
        sayi = len(self.olaylar("gidisat-degisti", oid))
        self.assertGreaterEqual(sayi, 1)
        etki.izle(self.sd, oid, bugun=self.gun(1))
        self.assertEqual(len(self.olaylar("gidisat-degisti", oid)), sayi)

    def test_karisik_ayni_gunde_uygulanan_diger_kayitlar(self):
        self.kartlar_ekle(D0, 2, 18)
        a = self.kayit(uygulama=D0)
        b = self.kayit(uygulama=D0)
        c = self.kayit(uygulama=self.gun(2))
        etki.izle(self.sd, a, bugun=D0)
        etki.izle(self.sd, c, bugun=self.gun(2))
        self.assertIn(b, self.gunluk(a)[0].get("karisik") or [])
        self.assertNotIn(a, self.gunluk(a)[0].get("karisik") or [])
        self.assertNotIn(c, self.gunluk(a)[0].get("karisik") or [])
        self.assertEqual(self.gunluk(c)[0].get("karisik") or [], [])


# ------------------------------------------------------------------ kriter 4: sabit bitiş yok

class BitisTest(Temel):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")
        self.taban_kartlari()

    def test_uzun_sure_sonra_bile_izleme_surer(self):
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=self.gun(99))
        e = self.oku(oid)["etki"]
        self.assertEqual(len(e["gunluk"]), 100)
        self.assertEqual(e["izleme"]["durum"], "suruyor")
        self.assertIsNone(e["izleme"]["kapanis"])
        self.assertIsNone(e.get("karar"))

    def test_kapat_izlemeyi_durdurur_ve_karar_yazar(self):
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=self.gun(2))
        etki.kapat(self.sd, oid, "dogru-karar", "veri tutarlı")
        e = self.oku(oid)["etki"]
        self.assertEqual(e["izleme"]["durum"], "kapandi")
        self.assertTrue(e["izleme"]["kapanis"])
        self.assertEqual(e["karar"]["sonuc"], "dogru-karar")
        self.assertEqual(e["karar"]["not"], "veri tutarlı")
        self.assertEqual(len(self.olaylar("izleme-kapandi", oid)), 1)
        etki.izle(self.sd, oid, bugun=self.gun(10))
        self.assertEqual(len(self.oku(oid)["etki"]["gunluk"]), 3)

    def test_kapat_gecersiz_sonuc_reddedilir(self):
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=D0)
        with self.assertRaises(ValueError):
            etki.kapat(self.sd, oid, "belki", "x")
        self.assertEqual(self.oku(oid)["etki"]["izleme"]["durum"], "suruyor")

    def test_geri_al_izlemeyi_durdurur(self):
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=self.gun(1))
        etki.geri_al(self.sd, oid, "ret oranı yükseldi")
        e = self.oku(oid)["etki"]
        self.assertEqual(e["izleme"]["durum"], "geri-alindi")
        evs = self.olaylar("geri-alindi", oid)
        self.assertEqual(len(evs), 1)
        etki.izle(self.sd, oid, bugun=self.gun(10))
        self.assertEqual(len(self.oku(oid)["etki"]["gunluk"]), 2)


# ------------------------------------------------------------------ kriter 5: append-only

class EklemeTest(Temel):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")
        self.taban_kartlari()

    def test_mevcut_satirlar_degismez_yalniz_sona_eklenir(self):
        oid = self.kayit()
        ham1 = self.jsonl_ham()
        self.assertTrue(ham1)
        for n in range(3):
            self.kartlar_ekle(self.gun(n), 3, 7)
        etki.izle(self.sd, oid, bugun=self.gun(1))
        ham2 = self.jsonl_ham()
        self.assertTrue(ham2.startswith(ham1))
        self.assertGreater(len(ham2), len(ham1))
        etki.uygulama_dogrula(self.sd, oid, True, "kanıt")
        etki.izle(self.sd, oid, bugun=self.gun(2))
        ham3 = self.jsonl_ham()
        self.assertTrue(ham3.startswith(ham2))
        etki.kapat(self.sd, oid, "belirsiz", "n yetersiz")
        ham4 = self.jsonl_ham()
        self.assertTrue(ham4.startswith(ham3))
        self.assertGreater(len(ham4), len(ham3))
        for s in ham4.decode("utf-8").splitlines():
            o = json.loads(s)
            self.assertIn("olay", o)
            self.assertEqual(o["onay"], oid)
            self.assertTrue(o["zaman"])


# ------------------------------------------------------------------ kriter 6: kötü x3 -> soru, ölçülemez

class SoruTest(Temel):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")
        self.taban_kartlari()

    def test_uc_gun_ust_uste_kotu_soru_bekliyor(self):
        for n in range(3):
            self.kartlar_ekle(self.gun(n), 20, 0)
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=self.gun(1))
        e = self.oku(oid)["etki"]
        self.assertEqual([x["gidisat"] for x in e["gunluk"]], ["kotu", "kotu"])
        self.assertFalse(e.get("soru_bekliyor"))
        etki.izle(self.sd, oid, bugun=self.gun(2))
        e = self.oku(oid)["etki"]
        self.assertTrue(e["soru_bekliyor"] is True)
        self.assertEqual(e["izleme"]["son_gidisat"], "kotu")
        self.assertEqual(e["izleme"]["ayni_gidisat_gun"], 3)

    def test_kesilen_dizi_soru_acmaz(self):
        self.kartlar_ekle(D0, 20, 0)
        self.kartlar_ekle(self.gun(1), 20, 0)
        self.kartlar_ekle(self.gun(2), 0, 400)  # birikim 40/440 ~ 0.09 -> iyi
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=self.gun(2))
        e = self.oku(oid)["etki"]
        self.assertEqual(e["gunluk"][2]["gidisat"], "iyi")
        self.assertFalse(e.get("soru_bekliyor"))

    def test_iyi_gidisat_soru_acmaz(self):
        for n in range(4):
            self.kartlar_ekle(self.gun(n), 2, 18)
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=self.gun(3))
        self.assertFalse(self.oku(oid)["etki"].get("soru_bekliyor"))

    def test_vaatsiz_kayit_olculemez(self):
        oid = self.kayit(vaat=None, taban=False)
        self.kartlar_ekle(D0, 2, 18)
        etki.izle(self.sd, oid, bugun=self.gun(2))
        e = self.oku(oid)["etki"]
        self.assertEqual(e["durum"], "olculemez")
        self.assertFalse(e.get("gunluk"))

    def test_olculebilir_false_olculemez(self):
        oid = self.kayit(vaat=dict(VAAT, olculebilir=False, metrik=None), taban=False)
        etki.izle(self.sd, oid, bugun=self.gun(2))
        e = self.oku(oid)["etki"]
        self.assertEqual(e["durum"], "olculemez")
        self.assertFalse(e.get("gunluk"))

    def test_desteklenmeyen_metrik_olculemez(self):
        for metrik in ("betik:md_bayt", "sayac:ret_sayisi"):
            oid = self.kayit(vaat=dict(VAAT, metrik=metrik), taban=False)
            etki.izle(self.sd, oid, bugun=self.gun(2))
            e = self.oku(oid)["etki"]
            self.assertEqual(e["durum"], "olculemez", metrik)
            self.assertFalse(e.get("gunluk"))

    def test_olculebilir_kayit_olculemez_damgasi_almaz(self):
        self.kartlar_ekle(D0, 2, 18)
        oid = self.kayit()
        etki.izle(self.sd, oid, bugun=D0)
        self.assertNotEqual(self.oku(oid)["etki"].get("durum"), "olculemez")


# ------------------------------------------------------------------ liste / doğru karar oranı

class ListeOranTest(Temel):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")
        self.taban_kartlari()

    def test_liste_yalniz_vaat_ya_da_etkisi_olanlari_verir(self):
        bos = onay.iste(self.sd, "Boş", "M")["id"]
        a = self.kayit()
        ids = [x["id"] for x in etki.liste(self.sd)]
        self.assertIn(a, ids)
        self.assertNotIn(bos, ids)

    def test_dogru_karar_orani_yalniz_kapatilanlardan(self):
        self.assertIsNone(etki.dogru_karar_orani(self.sd)["oran"])
        for sonuc in ("dogru-karar", "dogru-karar", "yanlis-karar", "belirsiz"):
            oid = self.kayit()
            etki.izle(self.sd, oid, bugun=D0)
            etki.kapat(self.sd, oid, sonuc, "n")
        acik = self.kayit()  # kapatılmamış: sayılmaz
        etki.izle(self.sd, acik, bugun=D0)
        r = etki.dogru_karar_orani(self.sd)
        self.assertEqual((r["dogru"], r["yanlis"], r["belirsiz"], r["kapatilan"]), (2, 1, 1, 4))
        self.assertAlmostEqual(r["oran"], 2 / 3)


# ------------------------------------------------------------------ onay.py kancaları (kriter 6/7 köprüsü)

class OnayKancaTest(Temel):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(etki, "scripts/etki.py bulunamadı")

    def akis(self, oid):
        onay.karar_ver(self.sd, oid, "onay")
        onay.al(self.sd, oid, "oturum-1")
        return onay.uygulandi(self.sd, oid, "yapıldı")

    def test_al_vaatli_kayitta_taban_alir_uygulandi_tarih_yazar(self):
        self.taban_kartlari(datetime.date.today())
        oid = onay.iste(self.sd, "S", "M")["id"]
        etki.vaat_ayarla(self.sd, oid, dict(VAAT))
        onay.karar_ver(self.sd, oid, "onay")
        onay.al(self.sd, oid, "oturum-1")
        taban = self.oku(oid)["etki"]["taban"]
        self.assertAlmostEqual(taban["deger"], 0.5)
        k = onay.uygulandi(self.sd, oid, "yapıldı")
        self.assertEqual(k["durum"], "uygulandi")
        self.assertEqual(self.oku(oid)["etki"]["uygulama_tarihi"], datetime.date.today().isoformat())

    def test_vaatsiz_onay_uygulandi_olabilir_etki_olculemez(self):
        oid = onay.iste(self.sd, "S", "M")["id"]
        k = self.akis(oid)
        self.assertEqual(k["durum"], "uygulandi")
        etki.izle(self.sd, oid)
        self.assertEqual(self.oku(oid)["etki"]["durum"], "olculemez")

    def test_bozuk_vaat_onay_akisini_bozmaz(self):
        oid = onay.iste(self.sd, "S", "M")["id"]
        yol = os.path.join(self.sd, "onaylar", oid + ".json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        k["vaat"] = ["bozuk", 1]
        k["etki"] = "bozuk"
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)
        k = self.akis(oid)
        self.assertEqual(k["durum"], "uygulandi")


if __name__ == "__main__":
    unittest.main()
