"""G-074: ret kaydına kriter kimlikleri (kriter_ids) ve tekrar eden kriter işareti (tekrar_kriter) — gölge ölçüm.
`py -3.13 -m pytest plugins/orkestra/tests/test_ret_kriter.py -q -p no:cacheprovider`

K1 ork_lib.ret_kriterleri(gerekce) saf fonksiyon (gerçek gerekçelerden kısaltılmış örnekler).
K2 cmd_kart_denetim ret kaydına kriter_ids + tekrar_kriter; onay kaydında yok.
K3 mevcut davranış korunur (neden zorunluluğu, maskeleme, .denetim.json). Yeşil kapı engeli test_test_kapisi/test_cekirdek'te.
K4 alansız eski kartlarla uyum.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cekirdek as C  # noqa: E402

sys.path.insert(0, os.path.dirname(C.CLI))
import ork_lib as L  # noqa: E402

# Gerçek gerekçelerden (G-026, G-029, G-045, G-057 x2, G-015) kısaltılmış alıntılar; sır içermez.
G026 = ("K1 KARŞILANDI: 7 KPI (K09-K15) için tanım, pay/payda+uygunluk, mevcut kaynak dolu. "
        "K2 KARŞILANMADI (kısmen): orkestra.py:122-124 doğrulandı; sayılar anlık görüntüyle tutuyor. "
        "ANCAK K15 iddiası ters: ork_lib.py:1210-1232 tur satırlarını değil hook satırlarını atar. "
        "K3 KARŞILANDI: 1.4 tablosu ve 1.5 yazılı. K4 KARŞILANDI: sır/çalışan adı yok.")
G029 = ("K1 KARŞILANDI: yeniden koşu 21 kayıt, CSV'de 21 satır. K2 KARŞILANDI: 82 kaydın 82'si CSV'de. "
        "K3 KARŞILANDI: Counter 15/6/0. K4 KARŞILANMADI: dosya:satır atıfları doğru. Ancak KD1 başlığı '18 yorum yanlış' diyor. "
        "K5 KARŞILANDI: en uzun alıntı 70 karakter.")
G045 = ("K1 KARŞILANDI: yeni_kume 200 tekil id. K2 KARŞILANDI: 7 skorun değerleri yeniden hesaplandı. "
        "K3 KARŞILANDI: CSV'de karar dolu. K4 KARŞILANMADI: KH-1..KH-5 doğru. Ancak hazırlık kararı çelişiyor. "
        "K5 KARŞILANDI: GetOnlySession GET 251+10.")
G057_8 = ("kriter 1,2,5: KARŞILANDI (test_paralel.py incelendi; 16/16 geçti). kriter 3: KARŞILANDI izole koşuda, "
          "ancak tam paket yükünde 3 sn testi düşüyor. kriter 4: KARŞILANMADI — sonuç eşitliği yok: seri 945 geçti/0 düşen")
G057_9 = ("k1-3,5 KARŞILANDI (16/16 yeşil, hash kilitle aynı); k4 KANITSIZ: raporda yalnız seri/paralel süre var; "
          "en yavaş 5 dosya yok")
G015 = ("K1-K3,K7,K8: KARŞILANDI — kilitli testler ve tam paket 533 passed. K4/K5: KARŞILANMADI — gerçek pytest "
        "çıktısında SUBFAILED düşüşü yakalanmıyor. K2/K6: KISMEN — _TOPLAMA_RE satır başına bağlı değil. "
        "on_kontrol: KARŞILANDI — regex ve sonuç aynı.")


class SafFonksiyon(unittest.TestCase):
    def test_gercek_gerekceler(self):
        vakalar = [(G026, ["K2"]), (G029, ["K4"]), (G045, ["K4"]), (G057_8, ["K4"]), (G057_9, ["K4"]),
                   (G015, ["K2", "K4", "K5", "K6"])]
        for metin, beklenen in vakalar:
            with self.subTest(metin=metin[:30]):
                self.assertEqual(L.ret_kriterleri(metin), beklenen)

    def test_karsilandi_listeye_girmez(self):
        self.assertEqual(L.ret_kriterleri("K1-K3 KARŞILANDI. K4 KANITSIZ."), ["K4"])
        self.assertEqual(L.ret_kriterleri("K1 KARŞILANDI, K2 KARŞILANDI"), [])

    def test_bicimler(self):
        self.assertEqual(L.ret_kriterleri("K1-K3: KARŞILANMADI"), ["K1", "K2", "K3"])
        self.assertEqual(L.ret_kriterleri("K1,K2,K4: KARŞILANMADI"), ["K1", "K2", "K4"])
        self.assertEqual(L.ret_kriterleri("K1, K2: KISMEN"), ["K1", "K2"])
        self.assertEqual(L.ret_kriterleri("kriter 3: KARŞILANMADI"), ["K3"])
        self.assertEqual(L.ret_kriterleri("kriter 1,2: KANITSIZ"), ["K1", "K2"])

    def test_ascii_ve_buyuk_kucuk_harf(self):
        self.assertEqual(L.ret_kriterleri("K2 KARSILANMADI"), ["K2"])
        self.assertEqual(L.ret_kriterleri("K1 karsilanmadi; k3 kanitsiz"), ["K1", "K3"])
        self.assertEqual(L.ret_kriterleri("K5 Kismen"), ["K5"])
        self.assertEqual(L.ret_kriterleri("K4 karşılanmadı"), ["K4"])

    def test_sirali_ve_tekil(self):
        self.assertEqual(L.ret_kriterleri("K10 KANITSIZ. K2 KARŞILANMADI. K2 KISMEN. K1 KANITSIZ"), ["K1", "K2", "K10"])

    def test_ayristirilamayan_bos_liste(self):
        for metin in ("", "x", "genel olarak yetersiz", "KARŞILANMADI", "Kriterler ok", None):
            with self.subTest(metin=metin):
                self.assertEqual(L.ret_kriterleri(metin), [])

    def test_donus_listedir_ve_saf(self):
        r = L.ret_kriterleri("K1 KANITSIZ")
        self.assertIsInstance(r, list)
        self.assertEqual(L.ret_kriterleri("K1 KANITSIZ"), r)


class Cli(unittest.TestCase):
    setUp = C.Cekirdek.setUp
    tearDown = C.Cekirdek.tearDown
    cli = C.Cekirdek.cli
    kart = C.Cekirdek.kart

    def bitir(self, g):
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md",
                     ajan_id="w1", ajan_tipi="orkestra:isci-t1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def den(self, g, karar, gerekce, neden="kanit-yok", did="d1"):
        a = ["kart", "denetim", g, "--karar", karar, "--gerekce", gerekce]
        if karar == "ret":
            a += ["--neden", neden]
        return self.cli(*a, ajan_id=did, ajan_tipi="orkestra:denetci")

    def yol(self, g, ek=".json"):
        return os.path.join(self.sd, "gorevler", g + ek)

    def kart_json(self, g):
        with open(self.yol(g), encoding="utf-8") as f:
            return json.load(f)

    def tur(self, g, karar, gerekce, **kw):
        self.bitir(g)
        r = self.den(g, karar, gerekce, **kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.kart_json(g)["denetimler"][-1]

    def test_ilk_ret_kriter_ids_ve_bos_tekrar(self):
        g = self.kart()
        d = self.tur(g, "ret", "K1 KARŞILANDI. K2 KARŞILANMADI. K3 KANITSIZ.")
        self.assertEqual(d["kriter_ids"], ["K2", "K3"])
        self.assertEqual(d["tekrar_kriter"], [])

    def test_ikinci_ret_kesisim(self):
        g = self.kart()
        self.tur(g, "ret", "K1 KARŞILANMADI. K2 KARŞILANMADI. K4 KANITSIZ.")
        d = self.tur(g, "ret", "K2 KISMEN. K3 KARŞILANMADI. K4 KARŞILANMADI. K1 KARŞILANDI.")
        self.assertEqual(d["kriter_ids"], ["K2", "K3", "K4"])
        self.assertEqual(d["tekrar_kriter"], ["K2", "K4"])

    def test_kesisim_yok_bos(self):
        g = self.kart()
        self.tur(g, "ret", "K1 KARŞILANMADI.")
        d = self.tur(g, "ret", "K2 KARŞILANMADI.")
        self.assertEqual(d["tekrar_kriter"], [])

    def test_ayristirilamayan_ret_bos_alanlar_ve_basarili(self):
        g = self.kart()
        d = self.tur(g, "ret", "genel olarak yetersiz")
        self.assertEqual(d["kriter_ids"], [])
        self.assertEqual(d["tekrar_kriter"], [])

    def test_onay_kaydinda_alan_yok(self):
        g = self.kart()
        self.tur(g, "ret", "K1 KARŞILANMADI.")
        d = self.tur(g, "onay", "K1 KARŞILANDI. K2 KARŞILANMADI.")
        self.assertNotIn("kriter_ids", d)
        self.assertNotIn("tekrar_kriter", d)

    def test_ayni_kriter_art_arda_tekrar(self):
        g = self.kart()
        self.tur(g, "ret", "K1 KARŞILANMADI.")
        d = self.tur(g, "ret", "K1 KARŞILANMADI.")
        self.assertEqual(d["tekrar_kriter"], ["K1"])

    def test_eski_kart_alansiz_onceki_ret(self):
        g = self.kart()
        self.tur(g, "ret", "K1 KARŞILANMADI.")
        k = self.kart_json(g)
        for dn in k["denetimler"]:  # eski kart: alanlar yok
            dn.pop("kriter_ids", None)
            dn.pop("tekrar_kriter", None)
        with open(self.yol(g), "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False, indent=2)
        d = self.tur(g, "ret", "K1 KARŞILANMADI. K2 KANITSIZ.")
        self.assertEqual(d["kriter_ids"], ["K1", "K2"])
        self.assertEqual(d["tekrar_kriter"], [])

    def test_denetim_json_alanlari_tasir(self):
        g = self.kart()
        self.tur(g, "ret", "K1 KARŞILANMADI.")
        self.tur(g, "ret", "K1 KANITSIZ.")
        with open(self.yol(g, ".denetim.json"), encoding="utf-8") as f:
            y = json.load(f)
        self.assertEqual(y[-1]["kriter_ids"], ["K1"])
        self.assertEqual(y[-1]["tekrar_kriter"], ["K1"])

    # ---- K3: mevcut davranış
    def test_ret_neden_zorunlu(self):
        g = self.kart()
        self.bitir(g)
        once = self.kart_json(g)
        r = self.cli("kart", "denetim", g, "--karar", "ret", "--gerekce", "K1 KARŞILANMADI",
                     ajan_id="d1", ajan_tipi="orkestra:denetci")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--neden", r.stderr)
        self.assertEqual(self.kart_json(g), once)

    def test_gerekce_maskelenir_kimlik_yine_cozulur(self):
        g = self.kart()
        d = self.tur(g, "ret", "K1 KARŞILANMADI: yazan ab@example.com adresine gitti")
        self.assertNotIn("ab@example.com", d["gerekce"])
        self.assertEqual(d["kriter_ids"], ["K1"])


if __name__ == "__main__":
    unittest.main()
