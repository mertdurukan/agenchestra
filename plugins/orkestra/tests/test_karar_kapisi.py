"""Açık karar kapısı (ADR-0112): yanıtsız `Karar gerekir` maddesi plan yazımını engeller; yanıt yalnız hook kaydından sayılır."""
import json
import os
import sys
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as K  # noqa: E402
import is_sirasi as S  # noqa: E402
import karar_kapisi as KK  # noqa: E402

MD_YANITSIZ = "# MD\n\n## 5. Bilinmeyenler\n\n- **Karar gerekir (D1):** Hangi parçalar eklenecek?\n- **Teyit gerekir:** x\n"
MD_KIMLIKSIZ = "# MD\n\n- **Karar gerekir:** Hangi parçalar eklenecek?\n"
MD_YAZAR_SATIRI = MD_YANITSIZ + "- **Yanıtlandı (kullanıcı, 31.10):** D1 skill'ler girer.\n"
SORU = {"questions": [{"question": "[D1] Hangi parçalar eklensin?", "header": "Parçalar", "multiSelect": False,
                       "options": [{"label": "Skill'ler", "description": "a"}, {"label": "Hepsi", "description": "b"}]}]}
YANIT = {"answers": {"[D1] Hangi parçalar eklensin?": "Skill'ler"}}


class KararKapisi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def is_klasoru(self, md, karar=True, kararlar=None):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", "001-deneme")
        os.makedirs(k)
        kayit = {"id": "I-001", "sira": S.SIRA_ADI}
        if karar:
            kayit["karar"] = True
        if kararlar:
            kayit["kararlar"] = kararlar
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f)
        with open(os.path.join(k, "mevcut_durum_20261031.md"), "w", encoding="utf-8") as f:
            f.write(md)
        return k

    def ortam(self, **ek):
        return mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_KARAR_KAPISI": "1", **ek})

    def test_yanitsiz_karar_plan_kapisini_reddeder(self):
        with self.ortam():
            e = KK.engel(self.is_klasoru(MD_YANITSIZ))
        self.assertTrue(any("D1" in x and "yanıtı kayıtlı değil" in x for x in e), e)

    def test_kimliksiz_karar_eksik_sayilir(self):
        with self.ortam():
            e = KK.engel(self.is_klasoru(MD_KIMLIKSIZ))
        self.assertTrue(any("kimliği yok" in x for x in e), e)

    def test_yazarin_kendi_yanitlandi_satiri_kapiyi_gecirmez(self):
        with self.ortam():
            e = KK.engel(self.is_klasoru(MD_YAZAR_SATIRI))
        self.assertTrue(any("D1" in x for x in e), e)

    def test_kullanici_yaniti_kayitliysa_gecer(self):
        k = self.is_klasoru(MD_YANITSIZ, kararlar={"D1": {"yanit": "Skill'ler"}})
        with self.ortam():
            self.assertEqual(KK.engel(k), [])

    def test_karar_bayragi_olmayan_eski_is_muaf(self):
        with self.ortam():
            self.assertEqual(KK.engel(self.is_klasoru(MD_YANITSIZ, karar=False)), [])

    def test_kapatma_degiskeni_kapiyi_kapatir(self):
        k = self.is_klasoru(MD_YANITSIZ)
        with self.ortam(ORKESTRA_KARAR_KAPISI="0"):
            self.assertEqual(KK.engel(k), [])

    def test_golge_modunda_engellemez(self):
        k = self.is_klasoru(MD_YANITSIZ)
        with self.ortam(), mock.patch("kapi_mod.mod", return_value="golge"):
            self.assertEqual(KK.engel(k), [])

    def test_yorum_icindeki_karar_sayilmaz(self):
        with self.ortam():
            self.assertEqual(KK.engel(self.is_klasoru("<!-- - **Karar gerekir (D1):** örnek -->\n")), [])

    def test_plan_eksikleri_kapiyi_calistirir(self):
        k = self.is_klasoru(MD_YANITSIZ)
        with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
            f.write("# Plan\n")
        with self.ortam():
            e = S.plan_eksikleri(k)
        self.assertTrue(any("D1" in x and "yanıtı kayıtlı değil" in x for x in e), e)

    def test_ekran_etiketli_yanitlanmis_soru_kaydedilir(self):
        self.assertEqual(KK.ekran_kararlari(SORU, YANIT), [("D1", "Skill'ler")])

    def test_ekran_etiketsiz_soru_kaydedilmez(self):
        soru = {"questions": [{**SORU["questions"][0], "question": "Hangi parçalar eklensin?"}]}
        self.assertEqual(KK.ekran_kararlari(soru, {"answers": {"Hangi parçalar eklensin?": "Skill'ler"}}), [])

    def test_ekran_yanitsiz_soru_kaydedilmez(self):
        self.assertEqual(KK.ekran_kararlari(SORU, {"answers": {}}), [])

    def test_kaydet_is_json_a_yazar_ve_kapi_gecer(self):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", "002-kayit")
        os.makedirs(k)
        with self.ortam():
            kayit = K.is_ac(self.sd, "Deneme", k)
            with open(os.path.join(k, "mevcut_durum_20261031.md"), "w", encoding="utf-8") as f:
                f.write(MD_YANITSIZ)
            self.assertTrue(KK.engel(k))
            KK.kaydet(self.sd, kayit["id"], [("D1", "Skill'ler")])
            self.assertEqual(KK.engel(k), [])
        self.assertEqual(json.load(open(os.path.join(k, "is.json"), encoding="utf-8"))["kararlar"]["D1"]["yanit"], "Skill'ler")


if __name__ == "__main__":
    unittest.main()
