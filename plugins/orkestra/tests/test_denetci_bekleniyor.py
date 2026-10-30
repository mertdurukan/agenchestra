"""I-271: ayrı denetçinin satırları henüz boşken (`bekliyor`) kapı `kapi_ret` yazmaz, `bekleniyor` durumunu döndürür;
plan yine geçmez (bağımsız denetim özü). İçerik hataları eskisi gibi `kapi_ret` yazar; `is rapor` ikisini ayrı sayar."""
import json
import os
import sys
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S  # noqa: E402
import kapi_mod as KM  # noqa: E402

DUZELTME = "Düzeltme: `sablonlar/plan_sirali.md` — soru plan yazılırken şablonda hazır durur"
DIGER = "Düzeltme: `agents/denetci.md` — yargı ölçütü ajan tanımında yazılıdır ve denetçi her planda aynı mercekle bakar"
DEN_ID = "a8159550dfebaedf5"
ALT = "**Alternatifler:**\n\n- Seçilen: betik.\n- Elenen: elle. Neden elendi: tekrar eder.\n\n"
BOS_DENETIM = ("## Best in class denetimi\n\n- **Kök neden:** bekliyor\n- **Alternatifler:** bekliyor\n"
               "- **Kapsam özü:** bekliyor\n- **Ölçüm:** bekliyor\n- **Üretim noktası:** bekliyor\n\n"
               "**Denetçi:** bekliyor (`orkestra:denetci <agent_id>`)\n")
DOLU_DENETIM = ("## Best in class denetimi\n\n- **Kök neden:** ✔ a\n- **Alternatifler:** ✔ b\n- **Kapsam özü:** ✔ c\n"
                f"- **Ölçüm:** ✔ d\n- **Üretim noktası:** ✔ yer doğru.\n\n**Denetçi:** orkestra:denetci {DEN_ID}\n")


def madde(n, alan):
    govde = f"### P{n} Madde\n\n**Ne:** Betik yazılır.\n\n**Dayanak:** MD §1\n\n" + ALT
    if alan is not None:
        govde += f"**Üretim noktası:** {alan}\n\n"
    return govde + "**Kabul:** x\n\n"


def plan(p1=DUZELTME, den=BOS_DENETIM):
    return "# Plan\n\n## 4. Plan maddeleri\n\n" + madde(1, p1) + madde(2, DIGER) + den


class DenetciBekleniyor(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def is_klasoru(self, metin):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", "001-deneme")
        os.makedirs(k)
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-001", "sira": S.SIRA_ADI, "uretim": True, "kalite": True}, f)
        with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
            f.write(metin)
        return k

    def denetci_kaydi(self):
        with open(os.path.join(self.sd, "zaman.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"tur": "alt", "agent_id": DEN_ID, "ajan": "orkestra:denetci"}) + "\n")

    def ortam(self):
        return mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_URETIM_KAPISI": "1",
                                            "ORKESTRA_BIC_KAPISI": "1"})

    def olaylar(self, tur, kapi=None):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [o for o in (json.loads(s) for s in f if s.strip())
                    if o.get("tur") == tur and (kapi is None or o.get("kapi") == kapi)]

    # ---- K1: boş denetçi satırı -> 'bekleniyor', kapi_ret yok
    def test_k1_bos_denetci_satiri_bekleniyor_ve_kapi_ret_yazilmaz(self):
        k = self.is_klasoru(plan())
        self.assertEqual(KM.mod("uretim_noktasi", k), "ihlal")
        with self.ortam():
            self.assertEqual(S.uretim_durumu(k), "bekleniyor")
            self.assertEqual(S.bic_durumu(k), "bekleniyor")
            S.plan_eksikleri(k)
            S.uretim_engeli(k)
            S.bic_uyari(k)
        self.assertEqual(self.olaylar("kapi_ret"), [])
        self.assertEqual(self.olaylar("kapi_golge", "best_in_class"), [])
        self.assertEqual(len(self.olaylar("kapi_bekleniyor", "uretim_noktasi")), 1)  # tekrar çağrı yeniden yazmaz

    def test_k1_bos_deger_de_bekleniyor_sayilir(self):
        den = "## Best in class denetimi\n\n- **Üretim noktası:**\n\n**Denetçi:**\n"
        with self.ortam():
            self.assertEqual(S.uretim_durumu(self.is_klasoru(plan(den=den))), "bekleniyor")

    # ---- K2: aynı durumda plan geçmez, todo yazılamaz
    def test_k2_bekleyen_plan_gecmez_todo_yazilamaz(self):
        k = self.is_klasoru(plan())
        with self.ortam():
            engel = S.uretim_engeli(k)
            pe = S.plan_eksikleri(k)
            with mock.patch.object(S, "mevcut_durum_eksikleri", return_value=[]), \
                    mock.patch.object(S, "sozlesme_engeli", return_value=[]):
                todo = S.todo_onkosulu(k)
                adim, _ = S.adim(k)
        self.assertTrue(engel and all(S.BEKLENIYOR in e for e in engel), engel)
        self.assertTrue(any(S.BEKLENIYOR in e and "Üretim noktası" in e for e in pe), pe)
        self.assertTrue(any(S.BEKLENIYOR in e and "Denetçi" in e for e in todo), todo)
        self.assertEqual(adim, "plan")

    def test_k2_denetci_doldurunca_gecer(self):
        self.denetci_kaydi()
        with self.ortam():
            k = self.is_klasoru(plan(den=DOLU_DENETIM))
            self.assertEqual(S.uretim_durumu(k), "tamam")
            self.assertEqual(S.uretim_engeli(k), [])

    # ---- K3: içerik hatası -> kapi_ret
    def test_k3_icerik_hatasi_kapi_ret_yazar(self):
        k = self.is_klasoru(plan(p1=None))  # P1 alanı eksik, denetçi satırları da boş
        with self.ortam():
            self.assertEqual(S.uretim_durumu(k), "ret")
            e = S.uretim_engeli(k)
        self.assertTrue(any("P1" in x and "alanı yok" in x for x in e), e)
        self.assertTrue(any(S.BEKLENIYOR in x for x in e), e)  # bekleyen satırlar da döner
        ret = self.olaylar("kapi_ret", "uretim_noktasi")
        self.assertEqual(len(ret), 1)
        self.assertIn("P1", ret[0]["neden"])
        self.assertNotIn(S.BEKLENIYOR, ret[0]["neden"])

    def test_k3_denetci_ret_isareti_ve_uydurma_kimlik_ret_sayilir(self):
        den = ("## Best in class denetimi\n\n- **Üretim noktası:** ✘ — yer yok.\n\n"
               "**Denetçi:** orkestra:denetci deadbeef0001\n")
        k = self.is_klasoru(plan(den=den))
        with self.ortam():
            self.assertEqual(S.uretim_durumu(k), "ret")
            S.uretim_engeli(k)
        self.assertEqual(len(self.olaylar("kapi_ret", "uretim_noktasi")), 1)

    def test_k3_bicimsiz_denetci_satiri_ret(self):
        den = "## Best in class denetimi\n\n- **Üretim noktası:** tamam gibi\n\n**Denetçi:** biri baktı\n"
        with self.ortam():
            self.assertEqual(S.uretim_durumu(self.is_klasoru(plan(den=den))), "ret")

    # ---- is rapor: gerçek ret ve bekleniyor ayrı
    def test_rapor_ret_ve_bekleniyor_ayri_sayilir(self):
        import is_rapor
        eski = ("best in class denetimi: `**Üretim noktası:**` satırı `✔` ile başlamıyor (ayrı denetçi doldurur; ADR-0069); "
                "best in class denetimi: `**Denetçi:**` satırı denetçi ajan kimliği taşımıyor (ADR-0069)")
        with open(os.path.join(self.sd, "gunluk.jsonl"), "a", encoding="utf-8") as f:
            for o in ({"tur": "kapi_ret", "kapi": "uretim_noktasi", "is": "a", "neden": "P1: alan yok"},
                      {"tur": "kapi_ret", "kapi": "uretim_noktasi", "is": "b", "neden": eski},
                      {"tur": "kapi_bekleniyor", "kapi": "uretim_noktasi", "is": "c", "neden": "x"}):
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        r = is_rapor.rapor(self.sd)
        self.assertEqual(r["kapi_ret"], {"uretim_noktasi": 1})
        self.assertEqual(r["kapi_bekleniyor"], {"uretim_noktasi": 2})
        m = is_rapor.metin(r)
        self.assertIn("kapı retleri (ihlal modu): uretim_noktasi 1", m)
        self.assertIn("denetçi bekleniyor (ret sayılmaz): uretim_noktasi 2", m)


if __name__ == "__main__":
    unittest.main()
