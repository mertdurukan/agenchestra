"""Plan paralellik modülü (ADR-0080, I-216 P1): `Önce` / `Yazma alanı` ayrıştırma, dalgalar, ağırlıklı oran ve kontroller."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import paralellik as PA  # noqa: E402


def plan(*maddeler: tuple[int, str, str], ek: str = "") -> str:
    """(n, Önce, Yazma alanı) üçlülerinden plan metni; boş alan satırı hiç yazılmaz."""
    parcalar = ["# Plan", "", "## 4. Plan maddeleri", ""]
    for n, once, yazma in maddeler:
        parcalar += [f"### P{n} Madde {n}", "", "**Ne:** iş", ""]
        if once is not None:
            parcalar += [f"**Önce:** {once}", ""]
        if yazma is not None:
            parcalar += [f"**Yazma alanı:** {yazma}", ""]
    parcalar += ["## Dalgalar", "", ek, ""]
    return "\n".join(parcalar)


# I-216 planının P blokları (ACMECO/064-20261023-golge-modda-degil-dogrudan-al/plan.md), alanlar birebir kopya.
I216_PLAN = """# Orkestra: plan aşamasında maksimum paralellik

## 4. Plan maddeleri

### P1 Ortak ayrıştırma ve dalga modülü

**Kabul:** `python -m pytest tests/test_paralellik.py` 12 ya da daha fazla testle yeşil.

**Önce:** yok

**Yazma alanı:** scripts/paralellik.py, tests/test_paralellik.py

**Alternatifler:**

- Seçilen: ayrı modül. Neden: P3, P4 ve P5 aynı fonksiyonlara bağlanır.

### P2 Plan şablonuna zorunlu alanlar

**Önce:** yok

**Yazma alanı:** sablonlar/plan_sirali.md, sablonlar/plan_dogrulamali.md

### P3 Plan kapısı (ihlal modu) ve iş bayrağı

**Önce:** P1 — Çıktı: `paralellik.dalgalar` ve kontrol fonksiyonlarının dönüş biçimini kapı çağırır; P7 — Çıktı: taban ölçüm kök neden varsayımını (C9) sınar, tutmazsa kapı kapsamı yeniden değerlendirilir

**Yazma alanı:** scripts/is_sirasi.py, scripts/is_kaydi.py, ayarlar/paralellik.json, tests/test_paralellik_kapi.py

### P4 `orkestra is dalga` plan→kart köprüsü

**Önce:** P1 — Çıktı: dalga hesabı ve kart JSON alanları `paralellik.py` fonksiyonlarından gelir; P7 — Çıktı: taban ölçüm C9'u sınar, kayıp dağıtımda çıkarsa komuta yükleme adımı eklenir

**Yazma alanı:** scripts/komutlar/dalga.py, scripts/orkestra.py, tests/test_dalga.py

### P5 Gerçekleşen eşzamanlılık ve kapanış denetimi

**Önce:** P1 — Çıktı: planlanan eşzamanlılık `paralellik` genişlik ve kritik yol fonksiyonlarından gelir; P7 — Çıktı: `taban_olcum_20261023.md` işçi-ajan eşzamanlılık tabanını verir, kapı çıktısı bununla karşılaştırılır

**Yazma alanı:** scripts/metrikler.py, scripts/komutlar/isler.py, scripts/is_rapor.py, sablonlar/calisma_ozeti.md, ayarlar/paralellik_kapanis.json, tests/test_paralellik_oran.py

### P6 Kural P-035, skill adımı ve eklenti kaydı

**Önce:** P7 — Çıktı: `taban_olcum_20261023.md` C9'u kapatır, kural metni bu sonuca göre yazılır

**Yazma alanı:** kurallar/eklenti_kurallari.json, KURALLAR.md, skills/is/SKILL.md

### P7 Taban ölçüm: sıralılığın doğduğu aşama

**Önce:** yok

**Yazma alanı:** ACMECO/98_calisma/paralellik_taban_20261023/**, ACMECO/064-20261023-golge-modda-degil-dogrudan-al/taban_olcum_20261023.md

## Dalgalar

- **Dalga 1:** P1, P2, P7
"""


class OnceAyristirma(unittest.TestCase):
    def test_yok_ve_iki_tur(self):
        self.assertEqual(PA.once_ayristir("yok"), ([], []))
        bag, hata = PA.once_ayristir("P1 — Çıktı: modülü okur; P2 - Çakışma: aynı dosya, ortak satır")
        self.assertEqual(hata, [])
        self.assertEqual(bag, [(1, "Çıktı", "modülü okur"), (2, "Çakışma", "aynı dosya, ortak satır")])

    def test_ayraclar_ve_virgul_ile_ayrim(self):
        bag, hata = PA.once_ayristir("P1 – Çıktı: a, b ve c, P3 — Çakışma: x")
        self.assertEqual(hata, [])
        self.assertEqual([(n, t) for n, t, _ in bag], [(1, "Çıktı"), (3, "Çakışma")])
        self.assertEqual(bag[0][2], "a, b ve c")

    def test_bicimsiz_ve_bos_gerekce(self):
        _, hata = PA.once_ayristir("P1")
        self.assertEqual(len(hata), 1)
        _, hata = PA.once_ayristir("P1 — Çıktı:")
        self.assertIn("gerekçe boş", hata[0])

    def test_yazma_alani_kumesi(self):
        self.assertEqual(PA.yazma_ayristir("`a.py`, b\\c.md ,  ./d.json"), {"a.py", "b/c.md", "d.json"})


class Kesisim(unittest.TestCase):
    def test_glob_ve_onek(self):
        self.assertTrue(PA.alan_kesisir({"ACMECO/98/x/**"}, {"ACMECO/98/x/a/b.py"}))
        self.assertTrue(PA.alan_kesisir({"tests/test_*.py"}, {"tests/test_dalga.py"}))
        self.assertTrue(PA.alan_kesisir({"scripts/"}, {"scripts/a.py"}))
        self.assertTrue(PA.alan_kesisir({"a/**"}, {"a/b/*.py"}))
        self.assertFalse(PA.alan_kesisir({"ACMECO/98/x/**"}, {"ACMECO/98/y.md"}))
        self.assertFalse(PA.alan_kesisir({"a.py"}, {"b.py"}))


class Kontroller(unittest.TestCase):
    def test_dongu(self):
        md = PA.maddeler(plan((1, "P2 — Çıktı: b'yi okur", "a.py"), (2, "P1 — Çıktı: a'yı okur", "b.py")))
        self.assertEqual(len(PA.dongu_var_mi(md)), 1)
        self.assertIn("döngüsü", PA.dongu_var_mi(md)[0])
        self.assertEqual(PA.dalgalar(md)["dalgalar"], [])
        self.assertTrue(any("döngüsü" in e for e in PA.analiz(plan((1, "P2 — Çıktı: x", "a"), (2, "P1 — Çıktı: y", "b")))["eksikler"]))

    def test_ileri_kendine_ve_olmayan_basvuru(self):
        md = PA.maddeler(plan((1, "P2 — Çıktı: sonraki", "a"), (2, "P2 — Çıktı: kendisi", "b"), (3, "P9 — Çıktı: yok", "c")))
        hatalar = PA.gecersiz_basvuru(md)
        self.assertEqual(len(hatalar), 3)
        self.assertIn("ileri", hatalar[0])
        self.assertIn("kendine", hatalar[1])
        self.assertIn("var olmayan P9", hatalar[2])
        self.assertEqual(len(PA.gecersiz_basvuru(md, ileri_yasak=False)), 2)

    def test_sahte_cakisma(self):
        md = PA.maddeler(plan((1, "yok", "a.py"), (2, "P1 — Çakışma: aynı dosya", "b.py"),
                              (3, "P1 — Çakışma: aynı dosya", "a.py, c.py")))
        hatalar = PA.cakisma_sahtesi(md)
        self.assertEqual(hatalar, ["P2: **Önce:** P1 — Çakışma gerekçesi sahte; yazma alanları kesişmiyor"])

    def test_ayni_dalga_kesisim(self):
        md = PA.maddeler(plan((1, "yok", "ortak.py, a.py"), (2, "yok", "src/**"), (3, "yok", "ortak.py"), (4, "yok", "src/x.py")))
        hatalar = PA.ayni_dalga_kesisim(md)
        self.assertEqual(len(hatalar), 2)
        self.assertIn("P1 ve P3", hatalar[0])
        self.assertIn("P2 ve P4", hatalar[1])
        # Çakışma bağımlılığı eklenince maddeler farklı dalgaya düşer, kesişim kalkar.
        md2 = PA.maddeler(plan((1, "yok", "ortak.py"), (2, "P1 — Çakışma: ortak.py iki maddede", "ortak.py")))
        self.assertEqual(PA.ayni_dalga_kesisim(md2), [])
        self.assertEqual(PA.cakisma_sahtesi(md2), [])

    def test_genislik_bir_plan(self):
        zincir = ((1, "yok", "a"), (2, "P1 — Çıktı: a'yı okur", "b"), (3, "P2 — Çıktı: b'yi okur", "c"))
        sonuc = PA.analiz(plan(*zincir))
        self.assertEqual((sonuc["kritik_yol"], sonuc["genislik"]), (3, 1))
        self.assertEqual(len([e for e in sonuc["eksikler"] if "Tam sıralı çünkü" in e]), 1)
        kisa = PA.analiz(plan(*zincir, ek="**Tam sıralı çünkü:** kısa"))
        self.assertTrue(any("Tam sıralı çünkü" in e for e in kisa["eksikler"]))
        tamam = PA.analiz(plan(*zincir, ek="**Tam sıralı çünkü:** her adım öncekinin şemasını okur"))
        self.assertEqual(tamam["eksikler"], [])
        # İki maddelik zincir gerekçe istemez.
        self.assertFalse(PA.tam_sirali_mi(PA.maddeler(plan(*zincir[:2]))))

    def test_eksik_ve_bicimsiz_alan(self):
        md = PA.maddeler(plan((1, None, "a.py"), (2, "yok", None), (3, "P1 bağlı", "c.py")))
        hatalar = PA.alan_eksikleri(md)
        self.assertEqual(len(hatalar), 3)
        self.assertIn("P1: **Önce:** alanı yok", hatalar[0])
        self.assertIn("P2: **Yazma alanı:**", hatalar[1])
        self.assertIn("P3: **Önce:** biçimsiz", hatalar[2])


class Olculer(unittest.TestCase):
    def test_agirlikli_oran(self):
        # P1 (3 dosya) → P3 (1); P2 (2) bağımsız. Σ ağırlık 6, ağırlıklı kritik yol 4 (P1+P3), kritik yol 2.
        md = PA.maddeler(plan((1, "yok", "a, b, c"), (2, "yok", "d, e"), (3, "P1 — Çıktı: a'yı okur", "f")))
        d = PA.dalgalar(md)
        self.assertEqual(d["dalgalar"], [[1, 2], [3]])
        self.assertEqual(d["agirlikli_kritik_yol"], 4)
        self.assertEqual(d["planlanan_agirlikli"], 1.5)
        self.assertEqual(d["planlanan_agirliksiz"], 1.5)
        # Yazma alanı boş madde ağırlık 1 sayılır.
        self.assertEqual(PA.dalgalar(PA.maddeler(plan((1, "yok", None))))["agirlik"], {1: 1})

    def test_i216_plani_iki_dalga(self):
        sonuc = PA.analiz(I216_PLAN)
        self.assertEqual(sonuc["dalgalar"], [[1, 2, 7], [3, 4, 5, 6]])
        self.assertEqual([len(k) for k in sonuc["dalgalar"]], [3, 4])
        self.assertEqual((sonuc["kritik_yol"], sonuc["genislik"]), (2, 4))
        self.assertEqual(sonuc["planlanan_agirliksiz"], 3.5)
        # Σ ağırlık 2+2+4+3+6+3+2 = 22; en ağır zincir P1/P7 (2) → P5 (6) = 8.
        self.assertEqual(sonuc["agirlikli_kritik_yol"], 8)
        self.assertEqual(sonuc["planlanan_agirlikli"], 2.75)
        # Bu plan P3-P6'dan sonraki P7'ye başvurur: ileri başvuru yasağı açıkken yalnız bu 4 uyarı kalır.
        self.assertEqual(len(sonuc["eksikler"]), 4)
        self.assertTrue(all("ileri" in e and "P7" in e for e in sonuc["eksikler"]))
        self.assertEqual(PA.analiz(I216_PLAN, ileri_yasak=False)["eksikler"], [])


if __name__ == "__main__":
    unittest.main()
