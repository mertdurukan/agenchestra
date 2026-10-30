"""ADR-0080 P5: iş başına gerçekleşen/planlanan paralellik (S6) ve kapanış paralellik kapısı (S6a/S6b, K6-K8)."""
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.join(AD, "..")
sys.path.insert(0, os.path.join(KOK, "scripts"))

import is_rapor as IR  # noqa: E402
import metrikler as MT  # noqa: E402

IS_ID = "I-900"
GENIS_PLAN = "".join(
    f"### P{n} Madde {n}\n\n**Önce:** yok\n\n**Yazma alanı:** scripts/d{n}.py\n\n" for n in (1, 2, 3))  # planlanan 3,0
DAR_PLAN = ("### P1 A\n\n**Önce:** yok\n\n**Yazma alanı:** a.py\n\n"
            "### P2 B\n\n**Önce:** P1 — Çıktı: a.py çıktısı gerekir\n\n**Yazma alanı:** b.py\n\n")  # planlanan 1,0
OZET = ("# Paralellik ölçümü denemesi: çalışma özeti (23.10.2026)\n\n## Özet\n\n**Ne yapıldı?**\n\n- Ölçüm eklendi.\n\n"
        "**Amaca tamamen ulaşıldı mı?**\n\nEvet.\n")
SAPMA = ("\n## Paralellik sapması\n\nPlanlanan 3,00; gerçekleşen 1,00. Kartlar tek tek elle dağıtıldı, "
         "çünkü işçiler aynı yardımcı dosyayı paylaştı.\n")


def _satir(ajan, bitis_sn, sure_sn, aid, is_id=IS_ID):
    return {"v": 1, "zaman": f"2026-10-23T10:{bitis_sn // 60:02d}:{bitis_sn % 60:02d}+03:00", "oturum": "o1",
            "is": is_id, "tur": "alt", "agent_id": aid, "ajan": ajan, "sure_ms": sure_sn * 1000}


class Proje:
    """Geçici proje: .claude/orkestra (zaman.jsonl, gunluk.jsonl, isler.json) ve bir iş klasörü."""

    def __init__(self, plan=GENIS_PLAN, paralel=True, kartlar=(), zaman=(), mod=None):
        self.kok = tempfile.mkdtemp()
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.klasor = os.path.join(self.kok, "900-20261023-deneme")
        os.makedirs(self.klasor)
        kayit = {"id": IS_ID, "baslik": "deneme", "durum": "acik", "klasor": self.klasor, "kartlar": list(kartlar)}
        if paralel:
            kayit["paralel"] = True
        self._yaz(os.path.join(self.klasor, "is.json"), kayit)
        with open(os.path.join(self.klasor, "plan.md"), "w", encoding="utf-8") as f:
            f.write("# Plan\n\n" + plan)
        self._yaz(os.path.join(self.sd, "isler.json"), {"isler": {IS_ID: {"klasor": self.klasor, "baslik": "deneme", "durum": "acik"}}})
        with open(os.path.join(self.sd, "zaman.jsonl"), "w", encoding="utf-8") as f:
            for r in zaman:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if mod:
            self._yaz(os.path.join(self.sd, "paralellik_kapanis.json"), {"mod": mod})
        self.env = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.kok})
        self.env.start()

    @staticmethod
    def _yaz(yol, veri):
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)

    def ozet(self, metin):
        with open(os.path.join(self.klasor, "calisma_ozeti_20261023.md"), "w", encoding="utf-8") as f:
            f.write(metin)

    def gunluk(self, tur=None):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            satirlar = [json.loads(s) for s in f if s.strip()]
        return [o for o in satirlar if o.get("kapi") == "paralellik_kapanis" and (tur is None or o.get("tur") == tur)]

    def kapat(self):
        self.env.stop()
        shutil.rmtree(self.kok, ignore_errors=True)


SIRALI = [_satir("orkestra:isci-t2", 100, 100, "a1"), _satir("orkestra:isci-t2", 200, 100, "a2")]  # gerçekleşen 1,0
ESZAMANLI = [_satir("orkestra:isci-t2", 100, 100, "a1"), _satir("orkestra:isci-t3", 100, 100, "a2"),
             _satir("orkestra:test-yazari", 100, 100, "a3")]  # gerçekleşen 3,0


class Birim(unittest.TestCase):
    def test_tam_ortusen_iki_isci_iki(self):
        z = [_satir("orkestra:isci-t2", 100, 60, "a1"), _satir("orkestra:isci-t1", 100, 60, "a2")]
        self.assertEqual(MT.isci_eszamanlilik(IS_ID, z)["deger"], 2.0)

    def test_ardisik_iki_isci_bir(self):
        self.assertEqual(MT.isci_eszamanlilik(IS_ID, SIRALI)["deger"], 1.0)

    def test_denetci_ve_baska_is_sayilmaz_kayit_yoksa_olculemedi(self):
        z = [_satir("orkestra:denetci", 100, 100, "d1"), _satir("orkestra:isci-t2", 100, 100, "x", is_id="I-901")]
        self.assertIsNone(MT.isci_eszamanlilik(IS_ID, z)["deger"])

    def test_bilinmeyen_ajan_payi_raporlanir(self):
        z = SIRALI + [_satir("?", 150, 50, "?")]
        g = MT.isci_eszamanlilik(IS_ID, z)
        self.assertEqual(g["deger"], 1.0)  # ? işçiye sayılmaz
        self.assertEqual(g["bilinmeyen"]["kayit"], 1)
        self.assertAlmostEqual(g["bilinmeyen"]["pay"], round(1 / 3, 4))
        p = {"birim": "ortalama eşzamanlı iş sayısı", "planlanan": 3.0, "gerceklesen": 1.0, "oran": 0.333, "isci": g, "neden": []}
        self.assertIn("ajan:? payı 1/3 kayıt", IR.paralellik_satiri(p))


class Kapanis(unittest.TestCase):
    def setUp(self):
        self.isler = importlib.import_module("komutlar.isler")
        self.p = None

    def tearDown(self):
        if self.p:
            self.p.kapat()

    def test_ihlal_kartsiz_dusuk_eszamanlilik_sapmasiz_reddedilir_sapmali_gecer(self):
        self.p = Proje(zaman=SIRALI, mod="ihlal")
        self.p.ozet(OZET)
        e = self.isler._ozet_eksigi(self.p.klasor) or ""
        self.assertIn("Paralellik sapması", e)
        self.assertIn("kartlar is.json'a yüklenmedi", e)
        self.assertIn("oran 0.33", e)
        self.assertEqual(len(self.p.gunluk("kapi_ret")), 1)
        self.p.ozet(OZET + SAPMA)
        self.assertIsNone(self.isler._ozet_eksigi(self.p.klasor))

    def test_ihlal_kisa_sapma_yetmez(self):
        self.p = Proje(zaman=SIRALI, mod="ihlal")
        self.p.ozet(OZET + "\n## Paralellik sapması\n\nElle dağıtıldı.\n")
        self.assertIn("Paralellik sapması", self.isler._ozet_eksigi(self.p.klasor) or "")

    def test_ihlal_yeterli_eszamanlilik_gecer(self):
        self.p = Proje(zaman=ESZAMANLI, kartlar=["G-1", "G-2", "G-3"], mod="ihlal")
        self.p.ozet(OZET)
        self.assertIsNone(self.isler._ozet_eksigi(self.p.klasor))
        self.assertEqual(self.p.gunluk("kapi_ret"), [])

    def test_golge_gecer_ama_kapi_golge_yazar(self):
        self.p = Proje(zaman=SIRALI, mod="golge")
        self.p.ozet(OZET)
        with redirect_stderr(io.StringIO()) as err:
            self.assertIsNone(self.isler._ozet_eksigi(self.p.klasor))
        kayit = self.p.gunluk("kapi_golge")
        self.assertEqual(len(kayit), 1)
        self.assertIn("sapma gerekir", kayit[0]["neden"])
        self.assertIn("paralellik_kapanis", err.getvalue())

    def test_bayraksiz_is_muaf(self):
        self.p = Proje(zaman=SIRALI, paralel=False, mod="ihlal")
        self.p.ozet(OZET)
        self.assertIsNone(self.isler._ozet_eksigi(self.p.klasor))
        self.assertEqual(self.p.gunluk(), [])

    def test_dar_plan_muaf(self):
        self.p = Proje(plan=DAR_PLAN, zaman=SIRALI, mod="ihlal")
        self.p.ozet(OZET)
        self.assertIsNone(self.isler._ozet_eksigi(self.p.klasor))

    def test_ortam_anahtari_kapatir(self):
        self.p = Proje(zaman=SIRALI, mod="ihlal")
        self.p.ozet(OZET)
        with mock.patch.dict(os.environ, {"ORKESTRA_PARALELLIK_KAPANIS_KAPISI": "0"}):
            self.assertIsNone(self.isler._ozet_eksigi(self.p.klasor))

    def test_kalibrasyon_sayisi_esige_ulasinca_ihlal(self):
        self.p = Proje(zaman=SIRALI, mod="golge")  # kalibrasyon sayımı gölgeden başlar (ayar dosyası ihlal, ADR-0096)
        self.assertEqual(self.isler.paralellik_kapanis_modu(self.p.klasor), "golge")
        yol = os.path.join(self.p.sd, "gunluk.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            for i in range(19):
                f.write(json.dumps({"tur": "kapi_golge", "kapi": "paralellik_kapanis", "is": f"{i:03d}-is", "neden": "x"}) + "\n")
            f.write(json.dumps({"tur": "kapi_golge", "kapi": "baska", "is": "999-is", "neden": "x"}) + "\n")
            f.write(json.dumps({"tur": "kapi_golge", "kapi": "paralellik_kapanis", "is": "000-is", "neden": "y"}) + "\n")
        self.assertEqual(self.isler.paralellik_kapanis_modu(self.p.klasor), "golge")  # 19 farklı iş
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps({"tur": "kapi_golge", "kapi": "paralellik_kapanis", "is": "019-is", "neden": "x"}) + "\n")
        self.assertEqual(self.isler.paralellik_kapanis_modu(self.p.klasor), "ihlal")
        self.p.ozet(OZET)
        self.assertIn("Paralellik sapması", self.isler._ozet_eksigi(self.p.klasor) or "")


class Rapor(unittest.TestCase):
    def test_is_rapor_iki_degeri_ayni_birimde_basar(self):
        p = Proje(zaman=SIRALI + [_satir("?", 150, 50, "?")])
        try:
            metin = IR.metin_detay(IR.detay(p.sd, IS_ID))
        finally:
            p.kapat()
        self.assertIn("ortalama eşzamanlı iş sayısı", metin)
        self.assertIn("planlanan 3.00, gerçekleşen 1.00", metin)
        self.assertIn("oran (gerçekleşen ÷ planlanan) 0.33", metin)
        self.assertIn("ajan:? payı 1/3", metin)

    def test_isci_kaydi_yoksa_olculemedi(self):
        p = Proje(zaman=[_satir("orkestra:denetci", 100, 100, "d1")])
        try:
            metin = IR.metin_detay(IR.detay(p.sd, IS_ID))
        finally:
            p.kapat()
        self.assertIn("gerçekleşen ölçülemedi", metin)


if __name__ == "__main__":
    unittest.main()
