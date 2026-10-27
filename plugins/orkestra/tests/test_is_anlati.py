"""G-171: scripts/is_anlati.py kanıt paketi (coz, paket, durum kuralları, güçlü fiil izni, metin).

Tüm veri sahtedir; geçici durum dizini ve iş klasörü kurulur.
"""
import copy
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
sys.path.insert(0, SCRIPTS)

import is_anlati as IA  # noqa: E402

ANAHTARLAR = {"is", "belgeler", "ne_icin", "sonuc", "yontem", "durum", "nasil_karar", "ana_sayi", "maddeler",
              "gapler", "sinirlar", "guclu_fiil_izni", "uyarilar"}

MD = """# mevcut durum

## 6. Gap analizi

- **G1:** hedef bir → mevcut iki → fark üç
- **G2:** hedef dört → mevcut beş → fark altı
"""

PLAN = """# plan

## Özet

Plan özeti.

## 1. Hedef

Sahte hedef cümlesi.

## 3. Kararlar

- **K1:** Birinci karar. Neden: sahte.

## 4. Plan maddeleri

### P1 Birinci madde

**Gap:** G1

### P2 İkinci madde

**Gap:** G2

## Gap kapsama

- **G1** → P1
- **G2** → P2
"""

OZET = """# özet

## Özet

Sahte sonuç.

**Amaç:**

Sahte amaç.

**Ana bulgu:**

Sahte bulgu.

**Doğrulanmayanlar:**

- Yok

**Açık işler:**

- Yok

## Plana göre gerçekleşen

- P1: yapıldı. Kanıt: x
- P2: yapıldı. Kanıt: y
- G1: kapandı. P1 ile.
- G2: kapandı. P2 ile.
"""

TODO_TAM = """# Yapılacaklar

- [x] P1: bir — 2026-10-22: kanıt: pytest => 3 passed
- [x] P2: iki — 2026-10-22: kanıt: komut çıktısı 0 failed
"""


class Ortam:
    def __init__(self):
        self._t = tempfile.TemporaryDirectory()
        self.kok = self._t.name
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.merkez = {"sayac": 0, "isler": {}}

    def is_ekle(self, kimlik, baslik, klasor_ad, durum="acik", belgeler=None, **ek):
        klasor = os.path.join(self.kok, klasor_ad)
        os.makedirs(klasor, exist_ok=True)
        for ad, ic in (belgeler or {}).items():
            with open(os.path.join(klasor, ad), "w", encoding="utf-8") as f:
                f.write(ic)
        kayit = {"id": kimlik, "baslik": baslik, "durum": durum, "klasor": klasor,
                 "olusturma": "2026-10-22T10:00:00+03:00", "guncelleme": "2026-10-22T11:00:00+03:00",
                 "kartlar": [], "oturumlar": [{"oturum": "o1"}]}
        kayit.update(ek)
        with open(os.path.join(klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f)
        self.merkez["isler"][kimlik] = {"klasor": klasor, "baslik": baslik, "durum": durum,
                                        "olusturma": kayit["olusturma"]}
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump(self.merkez, f)
        return kayit

    def kapat(self):
        self._t.cleanup()


def tam_is(o, durum="kapandi", todo=TODO_TAM, ozet=OZET):
    return o.is_ekle("I-900", "Sahte iş", "105-20261022-pe-1234-sahte-is", durum=durum,
                     belgeler={"mevcut_durum_20261022.md": MD, "plan.md": PLAN, "todo.md": todo,
                               "calisma_ozeti_20261022.md": ozet})


class CozTest(unittest.TestCase):
    def setUp(self):
        self.o = Ortam()
        self.addCleanup(self.o.kapat)
        tam_is(self.o)

    def test_kimlik_klasor_no_ve_jira(self):
        self.assertEqual([i["id"] for i in IA.coz(self.o.sd, "I-900")], ["I-900"])
        self.assertEqual([i["id"] for i in IA.coz(self.o.sd, "i-900")], ["I-900"])
        self.assertEqual([i["id"] for i in IA.coz(self.o.sd, "105")], ["I-900"])
        self.assertEqual([i["id"] for i in IA.coz(self.o.sd, "PE-1234")], ["I-900"])

    def test_eslesmeyen_bos_liste(self):
        for k in ("I-901", "999", "PE-9999", "PE-123", "", "rastgele"):
            self.assertEqual(IA.coz(self.o.sd, k), [], k)

    def test_birden_cok_eslesme(self):
        self.o.is_ekle("I-901", "Başka iş PE-1234 için", "106-20261022-baska")
        self.assertEqual(sorted(i["id"] for i in IA.coz(self.o.sd, "pe-1234")), ["I-900", "I-901"])


class PaketTest(unittest.TestCase):
    def setUp(self):
        self.o = Ortam()
        self.addCleanup(self.o.kapat)

    def test_tam_belgeli_is_sema(self):
        p = IA.paket(tam_is(self.o), self.o.sd)
        self.assertEqual(set(p), ANAHTARLAR)
        self.assertEqual(set(p["is"]), {"id", "baslik", "durum", "onay", "mod", "olusturma", "guncelleme",
                                        "oturum_say", "kart_say"})
        self.assertTrue(all(p["belgeler"].values()))
        self.assertEqual(p["uyarilar"], [])
        self.assertEqual([m["durum"] for m in p["maddeler"]], ["Doğrulandı", "Doğrulandı"])
        self.assertEqual([g["durum"] for g in p["gapler"]], ["kapandı", "kapandı"])
        self.assertEqual(p["gapler"][0]["maddeler"], ["P1"])
        self.assertEqual(p["ne_icin"][0], "Sahte hedef cümlesi.")
        self.assertEqual(p["sinirlar"], [])
        self.assertTrue(p["guclu_fiil_izni"])

    def test_belgesiz_is_hata_atmaz(self):
        k = self.o.is_ekle("I-902", "Belgesiz", "107-belgesiz")
        p = IA.paket(k, self.o.sd)
        self.assertEqual(set(p), ANAHTARLAR)
        self.assertFalse(any(p["belgeler"].values()))
        self.assertEqual(p["maddeler"], [])
        self.assertTrue(any("çalışma özeti yok" in u for u in p["uyarilar"]))
        self.assertFalse(p["guclu_fiil_izni"])
        self.assertIsInstance(IA.metin(p), str)
        self.assertIsInstance(IA.audit_metin(p), str)

    def test_klasorsuz_kayit_hata_atmaz(self):
        p = IA.paket({"id": "I-903", "baslik": "x", "durum": "acik"})
        self.assertEqual(set(p), ANAHTARLAR)
        self.assertTrue(p["uyarilar"])


class DurumTest(unittest.TestCase):
    def setUp(self):
        self.o = Ortam()
        self.addCleanup(self.o.kapat)

    def madde(self, todo, ozet=OZET, kimlik="P1"):
        p = IA.paket(tam_is(self.o, todo=todo, ozet=ozet), self.o.sd)
        return next(m for m in p["maddeler"] if m["kimlik"] == kimlik)

    def test_dogrulandi_sinyalli_not(self):
        m = self.madde(TODO_TAM)
        self.assertEqual((m["durum"], m["kanit"]), ("Doğrulandı", "Doğrulandı"))
        self.assertIn("doğruladım", m["fiiller"])

    def test_tamamlandi_notsuz(self):
        m = self.madde("- [x] P1: bir\n- [x] P2: iki\n")
        self.assertEqual((m["durum"], m["kanit"]), ("Tamamlandı", "Beyan/kayıt"))
        m = self.madde("- [x] P1: bir — 2026-10-22: kanıt: yapıldı bitti\n- [x] P2: iki\n")
        self.assertEqual(m["durum"], "Tamamlandı")

    def test_cok_satir_hepsi_x_biri_sinyalsiz_tamamlandi(self):
        m = self.madde("- [x] P1: bir — 2026-10-22: kanıt: pytest => 3 passed\n"
                       "- [x] P1: bir daha — 2026-10-22: kanıt: elle baktım\n- [x] P2: iki\n")
        self.assertEqual((m["durum"], m["kanit"]), ("Tamamlandı", "Beyan/kayıt"))

    def test_cok_satir_hepsi_sinyalli_dogrulandi(self):
        m = self.madde("- [x] P1: bir — 2026-10-22: kanıt: pytest => 3 passed\n"
                       "- [x] P1: bir daha — 2026-10-22: kanıt: git diff ortak.js\n- [x] P2: iki\n")
        self.assertEqual(m["durum"], "Doğrulandı")

    def test_hepsi_x_ozet_kismen_baslandi(self):
        m = self.madde(TODO_TAM, ozet=OZET.replace("P1: yapıldı", "P1: kısmen"))
        self.assertEqual(m["durum"], "Başlandı")

    def test_dosya_sayisi_sinyal_degil(self):
        self.assertFalse(IA._sinyal("dosya sayısı arttı"))
        m = self.madde("- [x] P1: bir — 2026-10-22: kanıt: dosya sayısı arttı\n- [x] P2: iki\n")
        self.assertEqual(m["durum"], "Tamamlandı")

    def test_kismi_x_baslandi(self):
        m = self.madde("- [x] P1: bir — 2026-10-22: kanıt: test\n- [ ] P1: bir daha\n- [x] P2: iki\n",
                       ozet=OZET.replace("P1: yapıldı", "P1: kısmen"))
        self.assertEqual(m["durum"], "Başlandı")
        self.assertIn("başladım", m["fiiller"])

    def test_hic_x_yok_planlandi(self):
        m = self.madde("- [ ] P1: bir\n- [ ] P2: iki\n", ozet="")
        self.assertEqual((m["durum"], m["kanit"]), ("Planlandı", "Beyan/kayıt"))

    def test_ozet_yapildi_ama_todo_acik_celiski(self):
        m = self.madde("- [ ] P1: bir\n- [x] P2: iki — 2026-10-22: kanıt: test\n")
        self.assertEqual((m["durum"], m["kanit"]), ("Planlandı", "Çıkarım"))
        self.assertIn("çelişki", " ".join(IA.paket(tam_is(self.o, todo="- [ ] P1: bir\n"), self.o.sd)["uyarilar"]))
        self.assertTrue(m["celiski"])

    def test_todosuz_ozet_yapildi_celiski(self):
        m = self.madde("# boş\n")
        self.assertEqual((m["durum"], m["kanit"]), ("Planlandı", "Çıkarım"))

    def test_engelli_kart_notu(self):
        m = self.madde("- [ ] P1: bir — 2026-10-22: engel: API yok\n", ozet="")
        self.assertEqual(m["durum"], "Engelli")

    def test_celiskide_gap_acik(self):
        p = IA.paket(tam_is(self.o, todo="- [ ] P1: bir\n- [x] P2: iki — 2026-10-22: kanıt: test\n"), self.o.sd)
        g1 = next(g for g in p["gapler"] if g["kimlik"] == "G1")
        self.assertEqual(g1["durum"], "açık")

    def test_ozetsiz_gap_bilinmiyor(self):
        k = self.o.is_ekle("I-904", "Özetsiz", "108-ozetsiz",
                           belgeler={"mevcut_durum_20261022.md": MD, "plan.md": PLAN, "todo.md": TODO_TAM})
        p = IA.paket(k, self.o.sd)
        self.assertEqual({g["durum"] for g in p["gapler"]}, {"Bilinmiyor"})

    def test_sinyal_listesi_sabit(self):
        for s in ("=>", "test", "pytest", "komut", "çıktı", "ölçüm", "canlı", "exit", "çıkış kodu", "ara ", "0 failed",
                  "failed", "passed", "grep", "git diff", "node --check"):
            self.assertIn(s, IA.SINYALLER)


class GucluFiilTest(unittest.TestCase):
    def setUp(self):
        self.o = Ortam()
        self.addCleanup(self.o.kapat)
        self.taban = IA.paket(tam_is(self.o), self.o.sd)

    def test_tum_kosullar_true(self):
        self.assertTrue(self.taban["guclu_fiil_izni"])
        self.assertTrue(IA.guclu_fiil_izni(self.taban))

    def test_kapanmamis_false(self):
        p = copy.deepcopy(self.taban)
        p["is"]["durum"] = "acik"
        self.assertFalse(IA.guclu_fiil_izni(p))

    def test_dogrulanmamis_madde_false(self):
        p = copy.deepcopy(self.taban)
        p["maddeler"][1]["durum"] = "Tamamlandı"
        self.assertFalse(IA.guclu_fiil_izni(p))

    def test_dogrulanmayan_var_false(self):
        o = Ortam()
        self.addCleanup(o.kapat)
        ozet = OZET.replace("**Doğrulanmayanlar:**\n\n- Yok", "**Doğrulanmayanlar:**\n\n- Canlıda gözlenmedi")
        p = IA.paket(tam_is(o, ozet=ozet), o.sd)
        self.assertEqual(p["sinirlar"], ["Doğrulanmayanlar: Canlıda gözlenmedi"])
        self.assertFalse(p["guclu_fiil_izni"])

    def test_ozet_yok_false(self):
        p = copy.deepcopy(self.taban)
        p["belgeler"]["calisma_ozeti"] = False
        self.assertFalse(IA.guclu_fiil_izni(p))

    def test_madde_yok_false(self):
        p = copy.deepcopy(self.taban)
        p["maddeler"] = []
        self.assertFalse(IA.guclu_fiil_izni(p))


class MetinTest(unittest.TestCase):
    def setUp(self):
        self.o = Ortam()
        self.addCleanup(self.o.kapat)

    def test_metin_kisa_ve_basliklar(self):
        t = IA.metin(IA.paket(tam_is(self.o), self.o.sd))
        self.assertLessEqual(len(t.splitlines()), 70)
        for b in ("# I-900", "NE İÇİN", "SONUÇ", "YÖNTEM", "MADDELER", "GAP'LER", "GÜÇLÜ FİİL İZNİ: evet"):
            self.assertIn(b, t)

    def test_cok_madde_70_satir_asmaz(self):
        todo = "".join(f"- [x] P{i}: m{i} — 2026-10-22: kanıt: test\n" for i in range(1, 40))
        t = IA.metin(IA.paket(tam_is(self.o, todo=todo), self.o.sd))
        self.assertLessEqual(len(t.splitlines()), 70)
        self.assertIn("+", t)

    def test_audit_tablo_ve_toplu(self):
        tam_is(self.o)
        p = IA.paket(IA.coz(self.o.sd, "I-900")[0], self.o.sd)
        self.assertIn("| P1 |", IA.audit_metin(p))
        sonuc = IA.toplu(self.o.sd, gun=36500)
        self.assertEqual(sonuc[0]["id"], "I-900")
        self.assertEqual((sonuc[0]["madde_say"], sonuc[0]["dogrulandi_say"]), (2, 2))


if __name__ == "__main__":
    unittest.main()
