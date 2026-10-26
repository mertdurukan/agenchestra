"""I-216 P4: `orkestra is dalga` plan→kart köprüsü (ADR-0080, sözleşme S4). Kendi fixture'ıyla."""
import json
import os
import sys
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(TC.KOK, "scripts"))
import paralellik as PR  # noqa: E402
from komutlar import dalga as D  # noqa: E402

# I-216 planına benzer 7 maddelik plan: Dalga 1 = P1, P2, P7; Dalga 2 = P3, P4, P5, P6 (P3 → P7 ileri başvuru).
PLAN = """# Örnek plan

## Özet

Yedi madde.

## 4. Plan maddeleri

### P1 Ortak modül

**Kabul:** `pytest tests/test_paralellik.py` yeşil.

**Önce:** yok

**Yazma alanı:** scripts/paralellik.py, tests/test_paralellik.py

### P2 Şablon alanları

**Kabul:** iki şablonda `Yazma alanı` geçer.

**Önce:** yok

**Yazma alanı:** sablonlar/plan_sirali.md, sablonlar/plan_dogrulamali.md

### P3 Plan kapısı

**Kabul:** `pytest tests/test_paralellik_kapi.py` yeşil.

**Önce:** P1 — Çıktı: kapı modül fonksiyonlarını çağırır; P7 — Çıktı: taban ölçüm kapsamı sınar

**Yazma alanı:** scripts/is_sirasi.py, scripts/is_kaydi.py, tests/test_paralellik_kapi.py

### P4 Dalga komutu

**Kabul:** `pytest tests/test_dalga.py` yeşil.

**Önce:** P1 — Çıktı: dalga hesabı modülden gelir, P7 — Çıktı: yükleme adımı ölçüme bağlı

**Yazma alanı:** scripts/komutlar/dalga.py, scripts/orkestra.py, tests/test_dalga.py

### P5 Kapanış denetimi

**Kabul:** `pytest tests/test_paralellik_oran.py` yeşil.

**Önce:** P1 — Çıktı: planlanan oran modülden gelir; P7 — Çıktı: taban değer

**Yazma alanı:** scripts/metrikler.py, scripts/komutlar/isler.py, tests/test_paralellik_oran.py

### P6 Kural kaydı

**Kabul:** `P-035` iki dosyada geçer.

**Önce:** P7 — Çıktı: kural metni ölçüm sonucuna göre yazılır

**Yazma alanı:** kurallar/eklenti_kurallari.json, KURALLAR.md

### P7 Taban ölçüm

**Kabul:** ölçüm raporu n ve medyanla yazılır.

**Önce:** yok

**Yazma alanı:** calisma/taban/**, calisma/taban_olcum.md

## Dalgalar

Elle hesaplandı; eski içerik.

- **Dalga 1:** P1

## Gap kapsama

- **G1** → P1
"""


class Dalga(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def kos(self, *args):
        return TC.kos([TC.CLI] + list(args), self.proje)

    def plan_yaz(self, metin=PLAN, klasor="is_klasoru"):
        d = os.path.join(self.proje, klasor)
        os.makedirs(d, exist_ok=True)
        yol = os.path.join(d, "plan.md")
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)
        return d, yol

    def oku(self, yol):
        with open(yol, encoding="utf-8") as f:
            return f.read()

    # ------------------------------------------------------------ hesap
    def test_iki_dalga_3_4_kritik_yol_2(self):
        an = PR.analiz(PLAN, ileri_yasak=False)
        self.assertEqual(an["dalgalar"], [[1, 2, 7], [3, 4, 5, 6]])
        self.assertEqual(an["kritik_yol"], 2)
        self.assertEqual(an["genislik"], 4)
        self.assertEqual(D.eksikler(PLAN, an), [])
        _, yol = self.plan_yaz()
        r = self.kos("is", "dalga", yol)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Dalga 1: P1, P2, P7", r.stdout)
        self.assertIn("Dalga 2: P3, P4, P5, P6", r.stdout)
        self.assertIn("Kritik yol: 2", r.stdout)
        self.assertIn("Genişlik: 4", r.stdout)
        self.assertIn("Planlanan eşzamanlılık (ağırlıksız): 3,5", r.stdout)
        self.assertIn("Planlanan eşzamanlılık (ağırlıklı):", r.stdout)

    def test_kart_json_semasi(self):
        an = PR.analiz(PLAN, ileri_yasak=False)
        kartlar = {k["ref"]: k for k in D.kartlar_uret(PLAN, an, "I-001", "plan.md")}
        self.assertEqual(sorted(kartlar), [f"P{n}" for n in range(1, 8)])
        p3 = kartlar["P3"]
        self.assertEqual(p3["bagimliliklar"], ["P1", "P7"])
        self.assertEqual(p3["kabul_kriterleri"], ["`pytest tests/test_paralellik_kapi.py` yeşil."])
        self.assertEqual(p3["yazma_alani"], ["scripts/is_sirasi.py", "scripts/is_kaydi.py", "tests/test_paralellik_kapi.py"])
        self.assertEqual(p3["sinif"], "kod")
        self.assertEqual(p3["test_alani"], ["tests/test_paralellik_kapi.py"])
        self.assertEqual(p3["is"], "I-001")
        self.assertEqual(kartlar["P6"]["sinif"], "belge")
        self.assertNotIn("test_komutu", kartlar["P6"])
        self.assertEqual(kartlar["P7"]["bagimliliklar"], [])
        for k in kartlar.values():
            self.assertTrue(k["soru"] and len(k["soru"]) <= 200 and "\n" not in k["soru"])

    # ------------------------------------------------------------ kart toplu
    def test_json_kart_toplu_ile_yuklenir(self):
        r = self.kos("is", "ac", "Dalga deneme", "--klasor", os.path.join(self.proje, "is_klasoru"))
        self.assertEqual(r.returncode, 0, r.stderr)
        _, yol = self.plan_yaz()
        is_id = json.loads(self.oku(os.path.join(self.proje, "is_klasoru", "is.json")))["id"]
        cikti = os.path.join(self.proje, "kartlar.json")
        r = self.kos("is", "dalga", is_id, "--json-cikti", cikti)
        self.assertEqual(r.returncode, 0, r.stderr)
        paket = json.loads(self.oku(cikti))
        self.assertEqual(len(paket["gorevler"]), 7)
        self.assertTrue(all(k["is"] == is_id for k in paket["gorevler"]))
        r = self.kos("kart", "toplu", "--json-dosya", cikti)
        self.assertEqual(r.returncode, 0, r.stderr)
        olusan = {k["baslik"].split()[0]: k for k in json.loads(r.stdout)}
        self.assertEqual(len(olusan), 7)
        self.assertEqual(sorted(olusan["P3"]["bagimliliklar"]), sorted([olusan["P1"]["id"], olusan["P7"]["id"]]))
        self.assertEqual(olusan["P1"]["bagimliliklar"], [])

    # ------------------------------------------------------------ --yaz
    def test_yaz_dalgalar_bolumunu_gunceller(self):
        _, yol = self.plan_yaz()
        r = self.kos("is", "dalga", yol, "--yaz")
        self.assertEqual(r.returncode, 0, r.stderr)
        metin = self.oku(yol)
        self.assertEqual(metin.count("## Dalgalar"), 1)
        self.assertNotIn("eski içerik", metin)
        self.assertIn("- **Dalga 1:** P1, P2, P7", metin)
        self.assertIn("- **Dalga 2:** P3, P4, P5, P6", metin)
        self.assertIn("- **Kritik yol:** 2", metin)
        self.assertLess(metin.index("## Dalgalar"), metin.index("## Gap kapsama"))
        self.assertIn("- **G1** → P1", metin)
        # İkinci koşu kararlıdır (aynı metin).
        self.assertEqual(self.kos("is", "dalga", yol, "--yaz").returncode, 0)
        self.assertEqual(self.oku(yol), metin)

    def test_yaz_bolum_yoksa_gap_kapsamadan_once_ekler(self):
        bolumsuz = PLAN.replace("## Dalgalar\n\nElle hesaplandı; eski içerik.\n\n- **Dalga 1:** P1\n\n", "")
        self.assertNotIn("## Dalgalar", bolumsuz)
        _, yol = self.plan_yaz(bolumsuz)
        r = self.kos("is", "dalga", yol, "--yaz")
        self.assertEqual(r.returncode, 0, r.stderr)
        metin = self.oku(yol)
        self.assertLess(metin.index("## Dalgalar"), metin.index("## Gap kapsama"))
        self.assertGreater(metin.index("## Dalgalar"), metin.index("### P7"))
        # Gap kapsama da yoksa sona eklenir.
        self.assertTrue(D.bolum_yaz("# x\n", "## Dalgalar\n").endswith("## Dalgalar\n"))

    def test_eksik_alanli_plan_yazilmaz(self):
        eksik = PLAN.replace("**Yazma alanı:** sablonlar/plan_sirali.md, sablonlar/plan_dogrulamali.md\n", "")
        eksik = eksik.replace("**Kabul:** ölçüm raporu n ve medyanla yazılır.\n", "")
        _, yol = self.plan_yaz(eksik)
        r = self.kos("is", "dalga", yol, "--yaz", "--json-cikti", os.path.join(self.proje, "k.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("P2: **Yazma alanı:**", r.stderr)
        self.assertIn("P7: **Kabul:**", r.stderr)
        self.assertEqual(self.oku(yol), eksik)
        self.assertFalse(os.path.exists(os.path.join(self.proje, "k.json")))

    # ------------------------------------------------------------ hata yolları
    def test_bilinmeyen_is_hata_verir(self):
        r = self.kos("is", "dalga", "I-9999")
        self.assertEqual(r.returncode, 2)
        self.assertIn("iş yok: I-9999", r.stderr)
        r = self.kos("is", "dalga", os.path.join(self.proje, "olmayan_klasor"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("plan bulunamadı", r.stderr)

    def test_klasor_ile_cozulur(self):
        d, _ = self.plan_yaz()
        r = self.kos("is", "dalga", d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"ref": "P4"', r.stdout)

    def test_komut_kaydi_ve_yardim(self):
        r = self.kos("is", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dalga", r.stdout)
        r = self.kos("is", "dalga", "--yardım")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--json-cikti", r.stdout)


if __name__ == "__main__":
    unittest.main()
