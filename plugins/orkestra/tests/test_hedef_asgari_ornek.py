"""I-142 P4/P5: asgari örnek eşiği (yetersiz-ornek) ve ret oranı için kayan 'son 30 karar' değeri."""
import copy
import os
import sys
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AD)
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import analitik as A  # noqa: E402
import test_hedef_panosu as T  # noqa: E402


def kararlar(kodlar, baslangic_gun=40):
    """kodlar: 'o' onay / 'r' ret; sırayla en eskiden en yeniye, her karar bir gün arayla."""
    return [{"zaman": T.z(baslangic_gun - i), "karar": "ret" if c == "r" else "onay", "sira": i} for i, c in enumerate(kodlar)]


class AsgariOrnek(unittest.TestCase):
    def pano(self, kodlar, asgari):
        hedef = copy.deepcopy(T.HEDEF)
        hedef["olculer"]["ret_orani"] = {"tur": "ust", "hedef": 0.06}
        if asgari is not None:
            hedef["asgari_ornek"] = {"ret_orani": asgari}
        k = T.kart("G-1", olus=T.z(0, 1), denetimler=kararlar(kodlar, baslangic_gun=0))
        return A.hedef_panosu([k], [], simdi=T.SIMDI, hedef=hedef, esik=T.ESIK)

    def test_az_ornekte_yetersiz_ornek(self):
        e = self.pano(["o", "r"], 20)["olculer"]["ret_orani"]["tum_zaman"]
        self.assertEqual((e["durum"], e["ornek"]), ("yetersiz-ornek", 2))
        self.assertEqual(e["deger"], 0.5)   # değer korunur, yalnız durum değişir

    def test_yeterli_ornekte_normal_durum(self):
        e = self.pano(["o"] * 15 + ["r"] * 5, 20)["olculer"]["ret_orani"]["tum_zaman"]
        self.assertEqual((e["durum"], e["ornek"]), ("kotu", 20))

    def test_asgari_yoksa_eski_davranis(self):
        e = self.pano(["o", "r"], None)["olculer"]["ret_orani"]["tum_zaman"]
        self.assertEqual(e["durum"], "kotu")

    def test_veri_yok_ayri_kalir(self):
        e = self.pano([], 20)["olculer"]["ret_orani"]["tum_zaman"]
        self.assertEqual(e["durum"], "veri-yok")

    def test_ayar_dosyasinda_asgari_var(self):
        import json
        with open(os.path.join(AD, "..", "ayarlar", "hedef.json"), encoding="utf-8") as f:
            a = json.load(f)["asgari_ornek"]
        self.assertEqual(a["ret_orani"], 20)
        self.assertTrue(all(isinstance(v, int) and v > 0 for v in a.values()))


class RetKayan(unittest.TestCase):
    SPEC = {"tur": "ust", "hedef": 0.06}

    def test_son_30_karar_el_hesabi(self):
        # 45 karar: ilk 15 hepsi ret (eski öğrenme), son 30'da 2 ret
        kodlar = ["r"] * 15 + ["o"] * 13 + ["r"] + ["o"] * 10 + ["r"] + ["o"] * 5
        self.assertEqual(len(kodlar), 45)
        k = T.kart("G-1", denetimler=kararlar(kodlar))
        r = A.ret_son_kararlar([k], self.SPEC, asgari=20)
        self.assertEqual((r["payda"], r["pay"], r["n"]), (30, 2, 30))
        self.assertAlmostEqual(r["deger"], 2 / 30, places=3)
        self.assertEqual(r["durum"], "uyari")   # %6,7 <= %6 * 1,25 = %7,5

    def test_kartlar_arasi_zamana_gore_siralanir(self):
        a = T.kart("G-1", denetimler=kararlar(["r"] * 40, baslangic_gun=100))   # çok eski
        b = T.kart("G-2", denetimler=kararlar(["o"] * 30, baslangic_gun=29))    # yeni
        r = A.ret_son_kararlar([a, b], self.SPEC)
        self.assertEqual((r["pay"], r["payda"]), (0, 30))

    def test_iptal_kart_sayilmaz_ve_az_veri(self):
        a = T.kart("G-1", durum="iptal", denetimler=kararlar(["r"] * 5))
        r = A.ret_son_kararlar([a], self.SPEC, asgari=20)
        self.assertEqual((r["deger"], r["durum"]), (None, "veri-yok"))

    def test_panoda_anahtar_var_ve_pencere_degerleri_degismez(self):
        k = T.kart("G-1", denetimler=kararlar(["o", "r"], baslangic_gun=0))
        p = A.hedef_panosu([k], [], simdi=T.SIMDI, hedef=T.HEDEF, esik=T.ESIK)
        self.assertEqual(p["ret_son_kararlar"]["payda"], 2)
        self.assertEqual(set(p["olculer"]["ret_orani"]), set(T.PENCERELER))   # kayan değer pencere sözlüğüne girmez


if __name__ == "__main__":
    unittest.main()
