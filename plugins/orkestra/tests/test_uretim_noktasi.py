"""K-006 üretim noktası kapısı (ADR-0069): plan maddesinde `**Üretim noktası:**` alanı ve ayrı denetçinin `✔` satırı.

Kapı ilk günden `ihlal` modundadır (kullanıcı kararı, P-028'den bilinçli sapma); her ret `kapi_ret` olarak kaydedilir.
Her karar dalı için bir vaka vardır (26).
"""
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
KONTROL = "Kontrol: `scripts/is_sirasi.py` — alanın türü ve dolgusu; Kaynakta çözülmedi çünkü: plan yazımı dışında zorlayan başka geçit yok"
YENI = "Yeni yetenek — iş açma komutuna eklenen kapsam bayrağıdır, mevcut davranışta kusur yoktur"
DIGER = "Düzeltme: `agents/denetci.md` — yargı ölçütü ajan tanımında yazılıdır ve denetçi her planda aynı mercekle bakar"
DEN_ID = "a8159550dfebaedf5"


def denetim(satir="✔ — alanların türü ve yeri doğru.", denetci=f"orkestra:denetci {DEN_ID}"):
    return f"## Best in class denetimi\n\n- **Üretim noktası:** {satir}\n\n**Denetçi:** {denetci}\n"


def madde(n, alan, baslik="Madde", ne="Betik yazılır."):
    govde = f"### P{n} {baslik}\n\n**Ne:** {ne}\n\n**Dayanak:** MD §1\n\n"
    if alan is not None:
        govde += f"**Üretim noktası:** {alan}\n\n"
    return govde + "**Kabul:** x\n\n"


def plan(*maddeler, den=None):
    return "# Plan\n\n## 4. Plan maddeleri\n\n" + "".join(maddeler) + (denetim() if den is None else den)


class UretimNoktasi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def is_klasoru(self, metin, uretim=True):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", "001-deneme")
        os.makedirs(k)
        kayit = {"id": "I-001", "sira": S.SIRA_ADI}
        if uretim:
            kayit["uretim"] = True
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f)
        with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
            f.write(metin)
        return k

    def denetci_kaydi(self, kimlik=DEN_ID, ajan="orkestra:denetci"):
        with open(os.path.join(self.sd, "zaman.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"tur": "alt", "agent_id": kimlik, "ajan": ajan}) + "\n")

    def ortam(self, **ek):
        return mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_URETIM_KAPISI": "1", **ek})

    def eksik(self, metin, kayitli=True, **kw):
        if kayitli:
            self.denetci_kaydi()
        with self.ortam():
            return S.uretim_eksikleri(self.is_klasoru(metin, **kw))

    def p1(self, alan, **kw):
        """P1 sınanan alan, P2 her zaman geçerli ve kendine özgü bir Düzeltme."""
        return self.eksik(plan(madde(1, alan), madde(2, DIGER)), **kw)

    # ---- Düzeltme: geçerli, eksik, kısa, yer yok (4)
    def test_duzeltme_gecerli(self):
        # Ne: metninde satır içi `**Üretim noktası:**` anması alan sayılmaz (canlı koşuda yakalanan hata)
        ne = "Kapı `**Üretim noktası:**` satırını sınar:\n\n- Alan her P'de dolu olur."
        self.assertEqual(self.eksik(plan(madde(1, DUZELTME, ne=ne), madde(2, DIGER))), [])

    def test_duzeltme_alani_eksik(self):
        e = self.p1(None)
        self.assertTrue(any("P1" in x and "alanı yok" in x for x in e), e)

    def test_duzeltme_onleme_kisa(self):
        e = self.p1("Düzeltme: `scripts/x.py` — kısa")
        self.assertTrue(any("P1" in x and "en az 15" in x for x in e), e)

    def test_duzeltme_yer_yok(self):
        e = self.p1("Düzeltme: ortada bir yerde — önleme metni yeterince uzun ve açık yazılmıştır")
        self.assertTrue(any("P1" in x and "yer" in x for x in e), e)

    # ---- Kontrol: geçerli, eksik, kısa, yer yok (4)
    def test_kontrol_gecerli(self):
        self.assertEqual(self.p1(KONTROL), [])

    def test_kontrol_kaynakta_cozulmedi_cunku_eksik(self):
        e = self.p1("Kontrol: `scripts/is_sirasi.py` — alanın türü ve dolgusu kontrol edilir")
        self.assertTrue(any("P1" in x and "biçim" in x for x in e), e)

    def test_kontrol_neden_kisa(self):
        e = self.p1("Kontrol: `scripts/is_sirasi.py` — alanın türü ve dolgusu; Kaynakta çözülmedi çünkü: kısa")
        self.assertTrue(any("P1" in x and "en az" in x for x in e), e)

    def test_kontrol_yer_yok(self):
        e = self.p1("Kontrol: ortada bir yerde — alanın türü ve dolgusu; Kaynakta çözülmedi çünkü: başka geçit olmadığı için")
        self.assertTrue(any("P1" in x and "yer" in x for x in e), e)

    # ---- Yeni yetenek: geçerli, eksik, kısa, biçim (4)
    def test_yeni_yetenek_gecerli(self):
        self.assertEqual(self.p1(YENI), [])

    def test_yeni_yetenek_gerekce_yok(self):
        e = self.p1("Yeni yetenek")
        self.assertTrue(any("P1" in x and "biçim" in x for x in e), e)

    def test_yeni_yetenek_gerekce_kisa(self):
        e = self.p1("Yeni yetenek — kısa")
        self.assertTrue(any("P1" in x and "en az 15" in x for x in e), e)

    def test_yeni_yetenek_ayirac_yanlis(self):
        e = self.p1("Yeni yetenek: iş açma komutuna eklenen kapsam bayrağıdır ve kusur yoktur")
        self.assertTrue(any("P1" in x and "biçim" in x for x in e), e)

    # ---- Kopya (3)
    def test_birebir_kopya_reddedilir(self):
        ikinci = "Düzeltme: `agents/denetci.md` — soru plan yazılırken şablonda hazır durur"
        e = self.eksik(plan(madde(1, DUZELTME), madde(2, ikinci)))
        self.assertTrue(any("P2" in x and "P1 ile aynı" in x for x in e), e)

    def test_jaccard_yuksek_kopya_reddedilir(self):
        ikinci = "Düzeltme: `agents/denetci.md` — soru plan yazılırken şablonda hazır durur artık"
        e = self.eksik(plan(madde(1, DUZELTME), madde(2, ikinci)))
        self.assertTrue(any("P2" in x and "benzer" in x for x in e), e)

    def test_jaccard_dusuk_gecer(self):
        self.assertEqual(self.eksik(plan(madde(1, DUZELTME), madde(2, DIGER))), [])

    # ---- Yeni yetenek yasağı (2)
    def test_baslikta_hata_varsa_yeni_yetenek_yasak(self):
        e = self.eksik(plan(madde(1, YENI, baslik="Hata kaydı alanı"), madde(2, DIGER)))
        self.assertTrue(any("P1" in x and "hata" in x.lower() for x in e), e)

    def test_ne_metninde_ret_varsa_yeni_yetenek_yasak(self):
        e = self.eksik(plan(madde(1, YENI, ne="Her ret kaydedilir."), madde(2, DIGER)))
        self.assertTrue(any("P1" in x and "ret" in x for x in e), e)

    # ---- Tümü Yeni yetenek (2)
    def test_tumu_yeni_yetenek_onaysiz_reddedilir(self):
        ikinci = "Yeni yetenek — panel sayfasına eklenen yeni bir görünümdür ve eski davranış değişmez"
        e = self.eksik(plan(madde(1, YENI), madde(2, ikinci)))
        self.assertTrue(any("tümü yeni yetenek onaylandı" in x for x in e), e)

    def test_tumu_yeni_yetenek_onayli_gecer(self):
        ikinci = "Yeni yetenek — panel sayfasına eklenen yeni bir görünümdür ve eski davranış değişmez"
        d = denetim("✔ — tümü yeni yetenek onaylandı, düzeltilecek kusur yok.")
        self.assertEqual(self.eksik(plan(madde(1, YENI), madde(2, ikinci), den=d)), [])

    # ---- Denetçi satırı (4)
    def test_denetci_satiri_ret_isareti(self):
        e = self.eksik(plan(madde(1, DUZELTME), madde(2, DIGER), den=denetim("✘ — yer yok.")))
        self.assertTrue(any("ile başlamıyor" in x for x in e), e)

    def test_denetci_satiri_bekliyor(self):
        e = self.eksik(plan(madde(1, DUZELTME), madde(2, DIGER), den=denetim("bekliyor")))
        self.assertTrue(any("ile başlamıyor" in x for x in e), e)

    def test_denetci_kimligi_kayitsiz(self):
        e = self.eksik(plan(madde(1, DUZELTME), madde(2, DIGER)), kayitli=False)
        self.assertTrue(any(DEN_ID in x and "kaydı bulunamadı" in x for x in e), e)

    def test_denetci_kimligi_kayitli(self):
        self.assertEqual(self.eksik(plan(madde(1, DUZELTME), madde(2, DIGER))), [])

    # ---- Kapsam, kapatma, kayıt (3)
    def test_bayraksiz_is_muaf(self):
        self.assertEqual(self.eksik(plan(madde(1, None)), uretim=False), [])

    def test_kapatma_anahtari(self):
        k = self.is_klasoru(plan(madde(1, None)))
        with self.ortam(ORKESTRA_URETIM_KAPISI="0"):
            self.assertEqual(S.uretim_eksikleri(k), [])
            self.assertEqual(S.uretim_engeli(k), [])

    def test_ret_kapi_ret_olarak_kaydedilir(self):
        k = self.is_klasoru(plan(madde(1, None), madde(2, DIGER)))
        self.assertEqual(KM.mod("uretim_noktasi", k), "ihlal")
        with self.ortam():
            e = S.plan_eksikleri(k)
            S.plan_eksikleri(k)  # aynı ret ikinci kez yazılmaz
        self.assertTrue(any("Üretim noktası" in x and "P1" in x for x in e), e)
        with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
            olaylar = [json.loads(s) for s in f if s.strip()]
        ret = [o for o in olaylar if o.get("tur") == "kapi_ret" and o.get("kapi") == "uretim_noktasi"]
        self.assertEqual(len(ret), 1, olaylar)
        self.assertFalse([o for o in olaylar if o.get("tur") == "kapi_golge" and o.get("kapi") == "uretim_noktasi"], olaylar)


if __name__ == "__main__":
    unittest.main()
