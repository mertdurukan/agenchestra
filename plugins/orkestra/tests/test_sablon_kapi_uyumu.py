"""Plan şablonları kendi kapılarından geçer (I-224 P2, kök neden R2).

Şablon ajanın ilk yazdığı plan.md'dir; iskelet kapıdan ret alıyorsa her iş aynı reti yeniden üretir. Bu test her plan
şablonunu şablondan açıldığı biçimiyle (`is_kaydi.sablon_metni`) kapılara verir:

- K-005 yazım kapısı (`belge_bicim.yazim_ihlalleri`): ihlal 0.
- P-015 ADR kapısı (`isler._adr_eksigi`) ve P-032 LLM beyanı (`is_sirasi.llm_beyan_eksikleri`): satır şablonda yorumsuz
  yer tutucu olarak durur; doldurulmamışsa kapı "satır yok" değil "doldur" der, şablonun söylediği biçimde doldurulunca
  ret yoktur.
- P-030 / ADR-0069 best in class bloğu: `bekliyor` satırları yalnız ayrı denetçinin dolduracağı satırlar için ret verir
  (yapısal ret yok); denetçi şablonun söylediği biçimde doldurunca ret yoktur.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(_KOK, "scripts"))
import belge_bicim as B  # noqa: E402
import is_kaydi as K  # noqa: E402
import is_sirasi as S  # noqa: E402
from komutlar import isler as I  # noqa: E402

PLAN_SABLONLARI = ("plan.md", "plan_sirali.md", "plan_dogrulamali.md")
SIRALI_SABLONLAR = ("plan_sirali.md", "plan_dogrulamali.md")
DEN_ID = "a8159550dfebaedf5"

ORNEK_P = """### P1 Şablonu onar

**Ne:** Şablon kendi kapısından geçer.

**Dayanak:** MD §1

**Kabul:** uyum testi geçer

**Geri alma:** git revert

**Alternatifler:**

- Seçilen: şablonu onarmak. Neden: ihlal şablonda doğuyor.
- Elenen: kapıyı gevşetmek. Neden elendi: kuralın amacı boşalır.

**Üretim noktası:** Düzeltme: `sablonlar/plan_sirali.md` — iskelet kendi kapısından sıfır ihlalle doğar

"""


def sablon(ad: str) -> str:
    return K.sablon_metni(ad, "Deneme işi", None, "20261024")


def doldur_slotlar(metin: str) -> str:
    """ADR ve LLM çıktısı yer tutucularını şablonun söylediği biçimde doldurur, bölüm 4'e örnek P maddesi koyar."""
    metin = re.sub(r"^\*\*ADR:\*\*.*$", "**ADR:** gerekmez — yalnız şablon metni değişiyor, mimari karar yok", metin, flags=re.M)
    metin = re.sub(r"^\*\*LLM çıktısı:\*\*.*$", "**LLM çıktısı:** yok — iş kullanıcıya giden bir LLM yanıtı üretmiyor",
                   metin, flags=re.M)
    return re.sub(r"^(## 4\. Plan maddeleri\n)", lambda m: m.group(1) + "\n" + ORNEK_P, metin, flags=re.M)


def doldur_bic(metin: str) -> str:
    """Ayrı denetçinin best in class bloğunu şablonun söylediği biçimde (✔ + ajan kimliği) doldurması."""
    m = S.BIC_DENETIM_BASLIK.search(metin)
    govde = re.sub(r"(\*\*[^*\n]+:\*\*) bekliyor\b", r"\1 ✔ denetçi onayladı", m.group(1))
    govde = re.sub(r"^\*\*Denetçi:\*\*.*$", f"**Denetçi:** orkestra:denetci {DEN_ID}", govde, flags=re.M)
    return metin[:m.start(1)] + govde + metin[m.end(1):]


class SablonKapiUyumu(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_sablon_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        with open(os.path.join(self.sd, "zaman.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"tur": "alt", "agent_id": DEN_ID, "ajan": "orkestra:denetci"}) + "\n")
        self.ortam = mock.patch.dict(os.environ, {
            "CLAUDE_PROJECT_DIR": self.proje, "ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_BIC_KAPISI": "1",
            "ORKESTRA_URETIM_KAPISI": "1", "ORKESTRA_KALITE_KAPISI": "1", "ORKESTRA_DURUM_YEREL": "1"})
        self.ortam.start()

    def tearDown(self):
        self.ortam.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def is_klasoru(self, plan: str) -> str:
        k = os.path.join(self.proje, "001-deneme")
        os.makedirs(k, exist_ok=True)
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-001", "sira": S.SIRA_ADI, "kalite": True, "uretim": True}, f)
        with open(os.path.join(k, "plan.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(plan)
        return k

    # ---- K1: K-005 yazım kapısı
    def test_k005_ihlali_yok(self):
        ayar = B.ayar_oku()
        for ad in PLAN_SABLONLARI:
            with self.subTest(sablon=ad):
                ihlal = B.yazim_ihlalleri(sablon(ad), "plan.md", ayar)
                self.assertEqual(ihlal, [], f"{ad}: {[(i['satir'], i['kural']) for i in ihlal]}")

    # ---- K2: ADR slotu (P-015)
    def test_adr_slotu_yorumsuz_ve_doldurulunca_gecer(self):
        for ad in PLAN_SABLONLARI:
            with self.subTest(sablon=ad):
                metin = sablon(ad)
                yorumsuz = S._YORUM.sub("", metin)
                self.assertRegex(yorumsuz, r"(?m)^\*\*ADR:\*\*", f"{ad}: `**ADR:**` satırı yorum dışında yok")
                bos = I._adr_eksigi(self.is_klasoru(metin), self.proje)
                self.assertIsNotNone(bos, f"{ad}: doldurulmamış yer tutucu kapıdan geçmemeli")
                self.assertNotIn("satırı yok", bos, f"{ad}: slot var, kapı yalnız doldurulmasını istemeli")
                self.assertIsNone(I._adr_eksigi(self.is_klasoru(doldur_slotlar(metin)), self.proje), ad)

    # ---- K2: LLM çıktısı slotu (P-032)
    def test_llm_slotu_yorumsuz_ve_doldurulunca_gecer(self):
        for ad in SIRALI_SABLONLAR:
            with self.subTest(sablon=ad):
                metin = sablon(ad)
                bos, _ = S.llm_beyan_eksikleri(self.proje, metin)
                self.assertTrue(bos, f"{ad}: doldurulmamış yer tutucu kapıdan geçmemeli")
                self.assertFalse(any("beyanı yok" in e for e in bos), f"{ad}: slot yorum içinde kalmış: {bos}")
                dolu, _ = S.llm_beyan_eksikleri(self.proje, doldur_slotlar(metin))
                self.assertEqual(dolu, [], ad)

    # ---- K2: best in class bloğu (P-030, ADR-0069)
    def test_bic_bekliyor_blogu_yalniz_denetci_satirlarini_ister(self):
        for ad in SIRALI_SABLONLAR:
            with self.subTest(sablon=ad):
                k = self.is_klasoru(doldur_slotlar(sablon(ad)))
                eksik = S.bic_eksikleri(k) + S.uretim_eksikleri(k)
                self.assertTrue(eksik, f"{ad}: denetçi doldurmadan blok geçmemeli")
                yapisal = [e for e in eksik if not e.startswith("best in class denetimi:")]
                self.assertEqual(yapisal, [], f"{ad}: şablon iskeleti denetçi dışı ret üretiyor")

    def test_bic_blogu_denetci_doldurunca_gecer(self):
        for ad in SIRALI_SABLONLAR:
            with self.subTest(sablon=ad):
                k = self.is_klasoru(doldur_bic(doldur_slotlar(sablon(ad))))
                self.assertEqual(S.bic_eksikleri(k), [], ad)
                self.assertEqual(S.uretim_eksikleri(k), [], ad)


if __name__ == "__main__":
    unittest.main()
