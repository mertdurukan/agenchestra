"""P-030 best in class kapısı (ADR-0041): plan maddesinde `Alternatifler` ve ayrı denetçinin `Best in class denetimi` bloğu.

Kapı golge modunda açılır: eksik uyarılır, `kapi_golge` kaydı düşer, todo yazımı engellenmez (P-028).
"""
import json
import os
import sys
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S  # noqa: E402

ALT_TAM = """**Alternatifler:**

- Seçilen: CLI ile kayıt. Neden: geçmiş tutulur.
- Elenen: elle düzenleme. Neden elendi: alanlar bozulur.
"""

DENETIM_TAM = """## Best in class denetimi

- **Kök neden:** ✔ — kökü çözüyor.
- **Alternatifler:** ✔ — gerçek alternatifler var.
- **Kapsam özü:** ✔ — öz korunuyor.
- **Ölçüm:** ✔ — eşik ve örnek gerekçeli.

**Denetçi:** orkestra:denetci a8159550dfebaedf5
"""


LLM_YOK = "**LLM çıktısı:** yok — kural metni, kullanıcıya LLM yanıtı üretilmiyor"


def plan(alt=ALT_TAM, denetim=DENETIM_TAM, llm=LLM_YOK):
    return f"# Plan\n\n{llm}\n\n## 4. Plan maddeleri\n\n### P1 Madde\n\n**Dayanak:** MD §1\n\n{alt}\n**Kabul:** x\n\n{denetim}\n"


class BestInClass(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def is_klasoru(self, kalite=True, plan_metni=None):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", "001-deneme")
        os.makedirs(k)
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-001", "sira": S.SIRA_ADI, "kalite": kalite}, f)
        if plan_metni is not None:
            with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
                f.write(plan_metni)
        return k

    def denetci_kaydi(self, kimlik="a8159550dfebaedf5", ajan="orkestra:denetci"):
        """SubagentStop hook'unun yazdığı zaman.jsonl `alt` kaydını taklit eder."""
        with open(os.path.join(self.sd, "zaman.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"tur": "alt", "agent_id": kimlik, "ajan": ajan}) + "\n")

    def ortam(self, **ek):
        return mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_BIC_KAPISI": "1", **ek})

    def test_tam_plan_eksiksiz(self):
        self.denetci_kaydi()
        with self.ortam():
            self.assertEqual(S.bic_eksikleri(self.is_klasoru(plan_metni=plan())), [])

    def test_alternatif_alani_yok(self):
        with self.ortam():
            e = S.bic_eksikleri(self.is_klasoru(plan_metni=plan(alt="")))
        self.assertTrue(any("P1" in x and "Alternatifler" in x for x in e), e)

    def test_tek_alternatif_ya_da_elenen_yok(self):
        with self.ortam():
            tek = S.bic_eksikleri(self.is_klasoru(plan_metni=plan(alt="**Alternatifler:**\n\n- Seçilen: x. Neden: y.\n")))
        self.assertTrue(any("P1" in x for x in tek), tek)

    def test_denetim_blogu_yok_ya_da_bekliyor(self):
        with self.ortam():
            yok = S.bic_eksikleri(self.is_klasoru(plan_metni=plan(denetim="")))
        self.assertTrue(any("bloğu yok" in x for x in yok), yok)
        bekle = DENETIM_TAM.replace("✔ — kökü çözüyor.", "bekliyor").replace("orkestra:denetci a8159550dfebaedf5", "bekliyor")
        os.rename(os.path.join(self.proje, "Claude_Orkestrasyon"), os.path.join(self.proje, "eski"))
        with self.ortam():
            e = S.bic_eksikleri(self.is_klasoru(plan_metni=plan(denetim=bekle)))
        self.assertTrue(any("Kök neden" in x for x in e) and any("Denetçi" in x for x in e), e)

    def test_denetci_kaydi_yoksa_ya_da_denetci_degilse_eksik(self):
        with self.ortam():
            k = self.is_klasoru(plan_metni=plan())
            self.assertTrue(any("kaydı bulunamadı" in x for x in S.bic_eksikleri(k)))  # kayıt hiç yok: uydurma kimlik
            self.denetci_kaydi(ajan="orkestra:isci-t3")  # aynı kimlik ama denetçi türü değil
            self.assertTrue(any("kaydı bulunamadı" in x for x in S.bic_eksikleri(k)))
            self.denetci_kaydi()
            self.assertEqual(S.bic_eksikleri(k), [])

    def test_olay_tekrari_jira_plani_yakalanir(self):
        """23.10 Jira olayı: tek yaklaşım, alternatifsiz, denetçisiz plan; kapı üç ayrı eksik bildirir."""
        kotu = "# Plan\n\n## 4. Plan maddeleri\n\n### P1 Açıklamalar\n\n**Ne:** Şablon doldur.\n\n**Kabul:** yapıldı\n"
        with self.ortam():
            e = S.bic_eksikleri(self.is_klasoru(plan_metni=kotu))
        self.assertTrue(any("P1" in x and "Alternatifler" in x for x in e), e)
        self.assertTrue(any("bloğu yok" in x for x in e), e)

    def test_bayraksiz_is_muaf_ve_kapi_kapatilabilir(self):
        with self.ortam():
            self.assertEqual(S.bic_eksikleri(self.is_klasoru(kalite=False, plan_metni=plan(alt=""))), [])
        os.rename(os.path.join(self.proje, "Claude_Orkestrasyon"), os.path.join(self.proje, "eski"))
        with self.ortam(ORKESTRA_BIC_KAPISI="0"):
            self.assertEqual(S.bic_eksikleri(self.is_klasoru(plan_metni=plan(alt=""))), [])

    def test_golge_modu_engellemez_ama_kaydeder(self):
        with self.ortam():
            k = self.is_klasoru(plan_metni=plan(alt=""))
            self.assertEqual(S.bic_engeli(k), [])  # golge: sessiz kapı engel döndürmez
            self.assertEqual(S.bic_uyari(k), [])  # golge: uyarı engel döndürmez
        gunluk = os.path.join(self.sd, "gunluk.jsonl")
        with open(gunluk, encoding="utf-8") as f:
            olaylar = [json.loads(s) for s in f if s.strip()]
        self.assertTrue(any(o.get("tur") == "kapi_golge" and o.get("kapi") == "best_in_class" for o in olaylar), olaylar)

    def test_ihlal_modunda_eksik_doner(self):
        import kapi_mod as KM
        with self.ortam():
            k = self.is_klasoru(plan_metni=plan(alt=""))
            with mock.patch.object(KM, "mod", return_value="ihlal"):
                self.assertTrue(S.bic_engeli(k))
                self.assertTrue(S.bic_uyari(k))
                self.assertTrue(any("Alternatifler" in x for x in S.plan_eksikleri(k)))

    def llm_eksikleri(self, llm, denetim=DENETIM_TAM):
        self.denetci_kaydi()
        with self.ortam():
            return S.bic_eksikleri(self.is_klasoru(plan_metni=plan(llm=llm, denetim=denetim)))

    def dogrulama_dosyasi(self, icerik="def test_ihlal_yakalanir():\n    pass\n"):
        os.makedirs(os.path.join(self.proje, "tests"), exist_ok=True)
        with open(os.path.join(self.proje, "tests", "test_dogrulama.py"), "w", encoding="utf-8") as f:
            f.write(icerik)

    def test_llm_beyani_yok(self):
        e = self.llm_eksikleri("")
        self.assertTrue(any("beyanı yok" in x and "P-032" in x for x in e), e)

    def test_llm_yok_gerekcesi_kisaysa_eksik(self):
        e = self.llm_eksikleri("**LLM çıktısı:** yok — yok")
        self.assertTrue(any("gerekçesi" in x for x in e), e)

    def test_llm_yok_yeterli_gerekceyle_eksiksiz(self):
        self.assertEqual(self.llm_eksikleri(LLM_YOK), [])

    def test_llm_gider_yolsuz_eksik(self):
        e = self.llm_eksikleri("**LLM çıktısı:** kullanıcıya gider")
        self.assertTrue(any("doğrulama yolu vermiyor" in x for x in e), e)

    def test_llm_gider_olmayan_yolla_eksik(self):
        e = self.llm_eksikleri("**LLM çıktısı:** kullanıcıya gider — Doğrulama: tests/yok_dosya.py")
        self.assertTrue(any("bulunamadı" in x for x in e), e)

    def test_llm_gider_var_olan_yolla_ve_yanit_kisiti_satiriyla_eksiksiz(self):
        self.dogrulama_dosyasi()
        denetim = DENETIM_TAM.replace("\n**Denetçi:**", "- **Yanıt kısıtı:** ✔ — doğrulama ihlali yakalıyor.\n\n**Denetçi:**")
        e = self.llm_eksikleri("**LLM çıktısı:** kullanıcıya gider — Doğrulama: tests/test_dogrulama.py::test_ihlal_yakalanir", denetim)
        self.assertEqual(e, [])

    def test_llm_gider_test_adi_dosyada_yoksa_eksik(self):
        self.dogrulama_dosyasi()
        e = self.llm_eksikleri("**LLM çıktısı:** kullanıcıya gider — Doğrulama: tests/test_dogrulama.py::test_baska")
        self.assertTrue(any("geçmiyor" in x for x in e), e)

    def test_llm_gider_beyanli_planda_yanit_kisiti_satiri_zorunlu(self):
        self.dogrulama_dosyasi()
        e = self.llm_eksikleri("**LLM çıktısı:** kullanıcıya gider — Doğrulama: tests/test_dogrulama.py")
        self.assertTrue(any("Yanıt kısıtı" in x for x in e), e)

    def test_beyansiz_yok_planda_yanit_kisiti_istenmez(self):
        self.assertFalse(any("Yanıt kısıtı" in x for x in self.llm_eksikleri(LLM_YOK)))

    def test_llm_kontrolu_kapi_kapatilinca_calismaz(self):
        with self.ortam(ORKESTRA_BIC_KAPISI="0"):
            self.assertEqual(S.bic_eksikleri(self.is_klasoru(plan_metni=plan(llm=""))), [])


if __name__ == "__main__":
    unittest.main()
