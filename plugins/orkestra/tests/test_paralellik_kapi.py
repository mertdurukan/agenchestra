"""Plan paralellik kapısı (ADR-0080): `**Önce:**` gerekçeli bağımlılık, `**Yazma alanı:**`, dalga kesişimi, tam sıralı gerekçe.

Kapı ilk günden `ihlal` modundadır (kullanıcı kararı); her ret `kapi_ret` olarak kaydedilir. Yalnız is.json `paralel: true`
taşıyan sıralı işler kapsamdadır; `ORKESTRA_PARALELLIK_KAPISI=0` kapatır.
"""
import glob
import json
import os
import sys
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S  # noqa: E402
import kapi_mod as KM  # noqa: E402

TAM_SIRALI = "Tam sıralı çünkü: her adım bir öncekinin ürettiği şemayı okur ve değiştirir."


def madde(n, once="yok", yazma="scripts/a.py"):
    govde = f"### P{n} Madde {n}\n\n**Ne:** Betik yazılır.\n\n**Dayanak:** MD §1\n\n"
    if once is not None:
        govde += f"**Önce:** {once}\n\n"
    if yazma is not None:
        govde += f"**Yazma alanı:** {yazma}\n\n"
    return govde + "**Kabul:** x\n\n"


def plan(*maddeler, ek=""):
    return "# Plan\n\n## 4. Plan maddeleri\n\n" + "".join(maddeler) + ek


# Temiz plan: P1 ve P2 paralel (ayrık alan), P3 P1'in çıktısını okur.
TEMIZ = plan(madde(1, yazma="scripts/a.py"), madde(2, yazma="scripts/b.py"),
             madde(3, once="P1 — Çıktı: P1'in ürettiği şemayı okur", yazma="scripts/c.py"))
VAKALAR = {
    "alan_yok": (plan(madde(1, once=None), madde(2, yazma="scripts/b.py")), "Önce:** alanı yok"),
    "sahte_cakisma": (plan(madde(1, yazma="scripts/a.py"), madde(2, once="P1 — Çakışma: aynı dosyaya yazarlar", yazma="scripts/b.py")),
                      "Çakışma gerekçesi sahte"),
    "ayni_dalga_kesisim": (plan(madde(1, yazma="scripts/a.py"), madde(2, yazma="scripts/a.py, docs/x.md")), "yazma alanı kesişiyor"),
    "tam_sirali_gerekcesiz": (plan(madde(1, yazma="scripts/a.py"), madde(2, once="P1 — Çıktı: şemayı okur", yazma="scripts/b.py"),
                                   madde(3, once="P2 — Çıktı: tabloyu okur", yazma="scripts/c.py")), "Tam sıralı çünkü:"),
}


class ParalellikKapisi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def is_klasoru(self, metin, paralel=True, ad="001-deneme"):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", ad)
        os.makedirs(k)
        kayit = {"id": "I-" + ad[:3], "sira": S.SIRA_ADI}
        if paralel:
            kayit["paralel"] = True
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f)
        with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
            f.write(metin)
        return k

    def ortam(self, **ek):
        return mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_PARALELLIK_KAPISI": "1", **ek})

    def eksik(self, metin, **kw):
        with self.ortam():
            return S.paralellik_eksikleri(self.is_klasoru(metin, **kw))

    def olaylar(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def assertIcerir(self, e, parca):
        self.assertTrue(any(parca in x for x in e), e)

    # ---- temiz ve ihlal vakaları
    def test_temiz_plan_gecer(self):
        self.assertEqual(self.eksik(TEMIZ), [])

    def test_alan_yok(self):
        e = self.eksik(VAKALAR["alan_yok"][0])
        self.assertIcerir(e, "P1: **Önce:** alanı yok")

    def test_yazma_alani_yok(self):
        e = self.eksik(plan(madde(1, yazma=None), madde(2, yazma="scripts/b.py")))
        self.assertIcerir(e, "P1: **Yazma alanı:** alanı yok")

    def test_once_bicimsiz(self):
        e = self.eksik(plan(madde(1), madde(2, once="P1'den sonra", yazma="scripts/b.py")))
        self.assertIcerir(e, "biçimsiz girdi")

    def test_sahte_cakisma(self):
        e = self.eksik(VAKALAR["sahte_cakisma"][0])
        self.assertIcerir(e, "P2: **Önce:** P1 — Çakışma gerekçesi sahte")

    def test_gercek_cakisma_gecer(self):
        metin = plan(madde(1, yazma="scripts/a.py"), madde(2, once="P1 — Çakışma: ikisi de a.py'ye yazar", yazma="scripts/a.py"),
                     madde(3, yazma="scripts/c.py"))
        self.assertEqual(self.eksik(metin), [])

    def test_ayni_dalgada_kesisen_alan(self):
        e = self.eksik(VAKALAR["ayni_dalga_kesisim"][0])
        self.assertIcerir(e, "Dalga 1: P1 ve P2 yazma alanı kesişiyor")

    def test_genislik_bir_gerekcesiz_ret(self):
        e = self.eksik(VAKALAR["tam_sirali_gerekcesiz"][0])
        self.assertIcerir(e, "Plan tam sıralı (3 madde, genişlik 1)")

    def test_genislik_bir_gerekceli_gecer(self):
        self.assertEqual(self.eksik(VAKALAR["tam_sirali_gerekcesiz"][0] + TAM_SIRALI + "\n"), [])

    def test_ileri_basvuru_gecer(self):
        metin = plan(madde(1, once="P3 — Çıktı: P3'ün yazdığı ayarı okur", yazma="scripts/a.py"),
                     madde(2, yazma="scripts/b.py"), madde(3, yazma="ayarlar/x.json"))
        self.assertEqual(self.eksik(metin), [])

    def test_dongu_reddedilir(self):
        metin = plan(madde(1, once="P2 — Çıktı: P2'nin şemasını okur", yazma="scripts/a.py"),
                     madde(2, once="P1 — Çıktı: P1'in tablosunu okur", yazma="scripts/b.py"), madde(3, yazma="scripts/c.py"))
        self.assertIcerir(self.eksik(metin), "bağımlılık döngüsü")

    def test_var_olmayan_basvuru(self):
        e = self.eksik(plan(madde(1), madde(2, once="P9 — Çıktı: şemayı okur", yazma="scripts/b.py")))
        self.assertIcerir(e, "var olmayan P9")

    # ---- kayıt, kapsam, kapatma, mod
    def test_ayar_modu_ihlal(self):
        k = self.is_klasoru(TEMIZ)
        self.assertEqual(KM.mod("paralellik", k), "ihlal")

    def test_her_ihlal_kapi_ret_yazar(self):
        for i, (ad, (metin, parca)) in enumerate(sorted(VAKALAR.items()), 1):
            with self.subTest(vaka=ad):
                k = self.is_klasoru(metin, ad=f"{i:03d}-{ad}")
                with self.ortam():
                    e = S.plan_eksikleri(k)
                    S.plan_eksikleri(k)  # aynı ret ikinci kez yazılmaz
                self.assertIcerir(e, parca)
                ret = [o for o in self.olaylar() if o.get("tur") == "kapi_ret" and o.get("kapi") == "paralellik"
                       and o.get("is") == os.path.basename(k)]
                self.assertEqual(len(ret), 1, self.olaylar())
        self.assertFalse([o for o in self.olaylar() if o.get("tur") == "kapi_golge" and o.get("kapi") == "paralellik"])

    def test_temiz_plan_kayit_yazmaz(self):
        k = self.is_klasoru(TEMIZ)
        with self.ortam():
            e = S.plan_eksikleri(k)
        self.assertFalse([x for x in e if "ADR-0080" in x], e)
        self.assertFalse([o for o in self.olaylar() if o.get("kapi") == "paralellik"])

    def test_bayraksiz_eski_is_muaf(self):
        k = self.is_klasoru(VAKALAR["alan_yok"][0], paralel=False)
        with self.ortam():
            self.assertEqual(S.paralellik_eksikleri(k), [])
            self.assertFalse([x for x in S.plan_eksikleri(k) if "ADR-0080" in x])
        self.assertFalse([o for o in self.olaylar() if o.get("kapi") == "paralellik"])

    def test_kapatma_anahtari(self):
        k = self.is_klasoru(VAKALAR["alan_yok"][0])
        with self.ortam(ORKESTRA_PARALELLIK_KAPISI="0"):
            self.assertFalse(S.paralellik_kapisi_acik())
            self.assertEqual(S.paralellik_eksikleri(k), [])
            self.assertEqual(S.paralellik_engeli(k), [])

    def test_golge_modunda_kapi_golge(self):
        with open(os.path.join(self.sd, "paralellik.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "golge"}, f)  # proje ezmesi
        k = self.is_klasoru(VAKALAR["sahte_cakisma"][0])
        self.assertEqual(KM.mod("paralellik", k), "golge")
        with self.ortam():
            self.assertEqual(S.paralellik_engeli(k), [])
            self.assertFalse([x for x in S.plan_eksikleri(k) if "ADR-0080" in x])
        golge = [o for o in self.olaylar() if o.get("tur") == "kapi_golge" and o.get("kapi") == "paralellik"]
        self.assertEqual(len(golge), 1, self.olaylar())
        self.assertFalse([o for o in self.olaylar() if o.get("tur") == "kapi_ret" and o.get("kapi") == "paralellik"])

    def test_yeni_is_paralel_bayragi_alir(self):
        r = TC.kos([TC.CLI, "is", "ac", "Paralel bayrak denemesi", "--klasor", "Claude_Orkestrasyon/001-deneme"], self.proje,
                   ortam={"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_PARALELLIK_KAPISI": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        kayitlar = glob.glob(os.path.join(self.proje, "**", "is.json"), recursive=True)
        self.assertTrue(kayitlar, r.stdout)
        with open(kayitlar[0], encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d.get("sira"), S.SIRA_ADI, d)
        self.assertIs(d.get("paralel"), True, d)
        self.assertIs(d.get("uretim"), None, d)  # kos() üretim kapısını kapatır; bayraklar bağımsız

    def test_kapali_iken_yeni_is_bayraksiz(self):
        r = TC.kos([TC.CLI, "is", "ac", "Bayraksız deneme", "--klasor", "Claude_Orkestrasyon/001-deneme"], self.proje,
                   ortam={"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_PARALELLIK_KAPISI": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        kayitlar = glob.glob(os.path.join(self.proje, "**", "is.json"), recursive=True)
        self.assertTrue(kayitlar, r.stdout)
        with open(kayitlar[0], encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d.get("sira"), S.SIRA_ADI, d)
        self.assertNotIn("paralel", d)


if __name__ == "__main__":
    unittest.main()
