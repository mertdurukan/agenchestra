"""Görev sözleşmesi kapısı (ADR-0035, P1 ve P2): `sozlesme: true` bayraklı iş, sözleşme tamam olmadan ilerlemez (ihlal modu)
ya da uyarılır (golge modu). Bayraksız iş etkilenmez. Geçici klasörde koşar."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S  # noqa: E402
import kapi_mod as KM  # noqa: E402

SOZLESME_TAMAM = """# Deneme: görev sözleşmesi

## Özet

Deneme işi tamam sayılır, kapsam dışı yok.

## Problem

Bir kapı eksik.

## Başarı kriterleri

- **S1:** kapı çalışır.
- **S2:** test geçer.

## Kapsam dışı

Yok.

## Kısıtlar

Yok.
"""

MD_TAMAM = """# Deneme: mevcut durum

**Ölçüm saati:**

22.10.2026 10:00

## 1. İstek ya da veri hangi yoldan geçiyor

- `a.py:10` alır.

## 2. Bugünkü davranış ve çalışan korumalar

- Koruma yok.

## 3. Etki haritası

- `a.py:10` → alır → orta risk.

## 4. Git durumu

- main.

## 5. Bilinmeyenler

- Yok.
"""


def plan(p1="S1", p2="S2"):
    s1 = f"\n**Sözleşme:** {p1}\n" if p1 else ""
    s2 = f"\n**Sözleşme:** {p2}\n" if p2 else ""
    return ("# Deneme: plan\n\n[mevcut_durum_20261022.md](mevcut_durum_20261022.md) → bu plan → todo.md.\n\n"
            f"## 4. Plan maddeleri\n\n### P1 Birinci\n\n**Dayanak:** MD §3\n{s1}\n### P2 İkinci\n\n**Dayanak:** MD §3\n{s2}\n")


class Sozlesme(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.mkdtemp(prefix="ork_sozlesme_")
        self.addCleanup(shutil.rmtree, self.klasor, True)
        env = mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_SOZLESME_KAPISI": "1",
                                           "ORKESTRA_KALITE_KAPISI": "0", "ORKESTRA_GAP_KAPISI": "0",
                                           "ORKESTRA_HARITA_KAPISI": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.yaz("is.json", json.dumps({"sira": S.SIRA_ADI, "sozlesme": True}))

    def yaz(self, ad, metin):
        with open(os.path.join(self.klasor, ad), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def mod(self, deger):
        return mock.patch.object(KM, "mod", return_value=deger)

    def test_bayraksiz_is_etkilenmez(self):
        self.yaz("is.json", json.dumps({"sira": S.SIRA_ADI}))
        self.assertEqual(S.sozlesme_eksikleri(self.klasor), [])
        self.assertEqual(S.sozlesme_uyari(self.klasor), [])
        self.assertEqual(S.adim(self.klasor)[0], "mevcut_durum")

    def test_kapi_kapaliysa_sozlesme_aranmaz(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_SOZLESME_KAPISI": "0"}):
            self.assertEqual(S.sozlesme_eksikleri(self.klasor), [])

    def test_sozlesme_dosyasi_yoksa_eksik(self):
        self.assertIn("sozlesme_<YYYYMMDD>.md yok", S.sozlesme_eksikleri(self.klasor)[0])

    def test_iskelet_sozlesme_eksik_sayilir(self):
        self.yaz("sozlesme_20261022.md", TC_SABLON())
        eksik = " ".join(S.sozlesme_eksikleri(self.klasor))
        for parca in ("Özet", "Problem", "Başarı kriterleri", "Kapsam dışı", "Kısıtlar"):
            self.assertIn(parca, eksik)

    def test_tam_sozlesme_eksiksiz(self):
        self.yaz("sozlesme_20261022.md", SOZLESME_TAMAM)
        self.assertEqual(S.sozlesme_eksikleri(self.klasor), [])
        self.assertEqual(S.sozlesme_kriterleri(self.klasor), {1, 2})

    def test_kriter_satiri_yoksa_eksik(self):
        self.yaz("sozlesme_20261022.md", SOZLESME_TAMAM.replace("- **S1:** kapı çalışır.\n- **S2:** test geçer.", "kriter yazılmadı"))
        self.assertTrue(any("S1" in e for e in S.sozlesme_eksikleri(self.klasor)))

    def test_golge_modunda_adim_atlar_ve_kayit_dusurur(self):
        self.yaz("sozlesme_20261022.md", TC_SABLON())
        with self.mod("golge"), mock.patch.object(KM, "kaydet") as kayit:
            self.assertNotEqual(S.adim(self.klasor)[0], "sozlesme")
            kayit.assert_not_called()  # adim sessizdir
            sonuc = S.plan_onkosulu(self.klasor)
            self.assertFalse(any("sözleşme" in e for e in sonuc))  # engel yok
            kayit.assert_called_once()
            self.assertEqual(kayit.call_args.args[1], "sozlesme")

    def test_ihlal_modunda_sozlesme_adimi_ve_plan_engeli(self):
        self.yaz("sozlesme_20261022.md", TC_SABLON())
        with self.mod("ihlal"):
            adim, eksik = S.adim(self.klasor)
            self.assertEqual(adim, "sozlesme")
            self.assertTrue(eksik)
            self.assertTrue(any("sözleşme" in e for e in S.plan_onkosulu(self.klasor)))
            self.yaz("sozlesme_20261022.md", SOZLESME_TAMAM)
            self.assertEqual(S.adim(self.klasor)[0], "mevcut_durum")

    def test_p2_plan_maddesi_sozlesme_kriterine_baglanir(self):
        self.yaz("sozlesme_20261022.md", SOZLESME_TAMAM)
        self.yaz("mevcut_durum_20261022.md", MD_TAMAM)
        self.yaz("plan.md", plan(p1="S1", p2=None))
        eksik = S.sozlesme_baglanti_eksikleri(self.klasor)
        self.assertTrue(any(e.startswith("P2:") for e in eksik), eksik)
        self.assertTrue(any(e.startswith("S2:") for e in eksik), eksik)
        with self.mod("ihlal"):
            self.assertEqual(S.adim(self.klasor)[0], "plan")
            self.yaz("plan.md", plan())
            self.assertEqual(S.sozlesme_baglanti_eksikleri(self.klasor), [])
            self.assertEqual(S.adim(self.klasor)[0], "todo")

    def test_p2_olmayan_kriter_reddedilir(self):
        self.yaz("sozlesme_20261022.md", SOZLESME_TAMAM)
        self.yaz("plan.md", plan(p1="S1", p2="S9"))
        self.assertTrue(any("S9" in e for e in S.sozlesme_baglanti_eksikleri(self.klasor)))

    def test_p2_ozet_anilmayan_sozlesme_kriterini_uyarir(self):
        from komutlar import isler
        self.yaz("sozlesme_20261022.md", SOZLESME_TAMAM)
        self.yaz("is.json", json.dumps({"sira": S.SIRA_ADI, "sozlesme": True, "kalite": True}))
        self.yaz("plan.md", plan())
        metin = "## Özet\n\nBitti.\n\n## Plana göre gerçekleşen\n\n- P1: tamam. S1 sağlandı.\n- P2: tamam.\n"
        with mock.patch.dict(os.environ, {"ORKESTRA_KALITE_KAPISI": "1"}), mock.patch.object(KM, "kaydet") as kayit:
            with self.mod("golge"):
                self.assertIsNone(isler._ozet_kalite_eksigi(self.klasor, metin))  # gölge: engellemez
                kayit.assert_called_once()
            with self.mod("ihlal"):
                self.assertIn("S2", isler._ozet_kalite_eksigi(self.klasor, metin))


def TC_SABLON():
    import is_kaydi
    return is_kaydi.sablon_metni("sozlesme.md", "Deneme")


class IsAcSozlesme(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def cli(self, *args, sozlesme="1"):
        return TC.kos([TC.CLI, *args], self.proje, ortam={"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_SOZLESME_KAPISI": sozlesme,
                                                          "ORKESTRA_KALITE_KAPISI": "0", "ORKESTRA_HARITA_KAPISI": "0"})

    def test_is_ac_sozlesme_acar_ve_bayrak_koyar(self):
        klasor = os.path.join(self.proje, "is1")
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(any(re.match(r"sozlesme_\d{8}\.md$", a) for a in os.listdir(klasor)))
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            self.assertIs(json.load(f).get("sozlesme"), True)

    def test_kapali_kapi_sozlesme_acmaz(self):
        klasor = os.path.join(self.proje, "is2")
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor, sozlesme="0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(any(a.startswith("sozlesme_") for a in os.listdir(klasor)))
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            self.assertNotIn("sozlesme", json.load(f))


if __name__ == "__main__":
    unittest.main()
