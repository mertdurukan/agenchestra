"""Kural metni kapı modunu kopyalamaz (ADR-0125, I-300): mod `{{mod:<ayar>}}` yer tutucusundan ayardan basılır.

`py -3.13 -m pytest plugins/orkestra/tests/test_kural_mod.py`
Üretim testleri geçici eklenti deposu kullanır (ORKESTRA_EKLENTI_KURALLARI); gerçek kural JSON'u yalnız tarama testlerinde okunur.
"""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
KOK = os.path.abspath(os.path.join(AD, ".."))
sys.path.insert(0, SCRIPTS)
import kapi_mod as KM  # noqa: E402
import onay  # noqa: E402
from komutlar import kapi as KAPI  # noqa: E402

GERCEK_KURALLAR = os.path.join(KOK, "kurallar", "eklenti_kurallari.json")
ELLE_MOD = re.compile(r"gölge modundadır|mod golge|mod ihlal|ilk 20 işte golge|gölgededir|ihlaldedir|ihlal modundadır")


def kural(kid, metin):
    return {"id": kid, "metin": metin, "neden": "", "durum": "etkin", "kaynak": "cli", "olusturma": "2026-10-31T10:00:00+03:00",
            "guncelleme": "2026-10-31T10:00:00+03:00", "gecmis": []}


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.sd = os.path.join(self.t.name, "proje", ".claude", "orkestra")
        os.makedirs(self.sd)
        self.depo = os.path.join(self.t.name, "eklenti", "kurallar", "eklenti_kurallari.json")
        os.makedirs(os.path.dirname(self.depo))
        self.env = mock.patch.dict(os.environ, {"ORKESTRA_EKLENTI_KURALLARI": self.depo})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.t.cleanup()

    def depo_yaz(self, *kurallar):
        with open(self.depo, "w", encoding="utf-8") as f:
            json.dump({"kurallar": list(kurallar)}, f, ensure_ascii=False)

    def ezme(self, kapi, mod):
        with open(os.path.join(self.sd, kapi + ".json"), "w", encoding="utf-8") as f:
            json.dump({"mod": mod}, f)


class ModCoz(Temel):
    def test_ham_deger_ayardan_gelir_iki_mod_disi_dahil(self):
        self.assertEqual(KM.ham_mod("best_in_class"), "ihlal")
        self.assertEqual(KM.ham_mod("secim_ekrani_hatirlatma"), "block")  # kapi_mod.mod() bunu sessizce golge yapardı

    def test_olmayan_kapi_none_ve_mod_coz_hata(self):
        self.assertIsNone(KM.ham_mod("yok_boyle_kapi"))
        with self.assertRaises(ValueError):
            KM.mod_coz("x {{mod:yok_boyle_kapi}} y", self.sd)

    def test_yer_tutucu_cozulur_ve_cikti_tutucu_icermez(self):
        c = KM.mod_coz("A {{mod:best_in_class}} B {{mod:secim_ekrani_hatirlatma}}", self.sd)
        self.assertEqual(c, "A ihlal B block")

    def test_proje_ezmesi_cikti_degistirir(self):
        self.assertEqual(KM.mod_coz("{{mod:best_in_class}}", self.sd), "ihlal")
        self.ezme("best_in_class", "golge")
        self.assertEqual(KM.mod_coz("{{mod:best_in_class}}", self.sd), "golge")

    def test_sd_yoksa_varsayilan_ve_ezme_notu(self):
        c = KM.mod_coz("{{mod:best_in_class}}")
        self.assertIn("ihlal", c)
        self.assertIn("orkestra kapi durum", c)

    def test_tutucu_olmayan_metin_ayni_kalir(self):
        self.assertEqual(KM.mod_coz("düz metin {{mod:<ayar>}}", self.sd), "düz metin {{mod:<ayar>}}")


class Uretim(Temel):
    def setUp(self):
        super().setUp()
        self.depo_yaz(kural("P-901", "Kapı modu: {{mod:best_in_class}}; seçim: {{mod:secim_ekrani_hatirlatma}}."))

    def test_kural_dosyasi_ayardaki_modu_basar(self):
        m = onay._kural_dosya_metni(self.sd)
        self.assertIn("Kapı modu: ihlal; seçim: block.", m)
        self.assertNotIn("{{mod:", m)

    def test_ezme_degisince_dosya_degisir_ve_esitle_yeniler(self):
        onay._kural_dosyasini_yaz(self.sd)
        yol = onay._kural_dosya_yolu(self.sd)
        self.assertFalse(onay.kural_dosyasi_esitle(self.sd))  # değişiklik yok
        self.ezme("best_in_class", "golge")
        self.assertTrue(onay.kural_dosyasi_esitle(self.sd))
        with open(yol, encoding="utf-8") as f:
            self.assertIn("Kapı modu: golge;", f.read())

    def test_gosterim_yuzeyleri_tutucu_gostermez(self):
        for r in onay.kurallar(self.sd):
            self.assertNotIn("{{mod:", r["metin"])
        self.assertIn("{{mod:", onay.kurallar(self.sd)[0]["metin_ham"])  # düzenleme için ham metin ayrı alanda
        for r in onay.kural_gorunum(self.sd, os.path.dirname(os.path.dirname(self.sd)))["etkin"]:
            self.assertNotIn("{{mod:", r["metin"])


class GercekKurallar(unittest.TestCase):
    def setUp(self):
        with open(GERCEK_KURALLAR, encoding="utf-8") as f:
            self.kurallar = json.load(f)["kurallar"]

    def test_elle_yazilmis_mod_ifadesi_yok(self):
        kotu = [(r["id"], m.group(0)) for r in self.kurallar if r.get("durum") == "etkin" for m in ELLE_MOD.finditer(r["metin"])]
        self.assertEqual(kotu, [], "kapı modu elle yazılamaz; `{{mod:<ayar>}}` kullan")

    def test_her_yer_tutucu_ayara_baglanir_ve_yeterince_var(self):
        sayi = 0
        for r in self.kurallar:
            if r.get("durum") != "etkin":
                continue
            KM.mod_coz(r["metin"], None)  # ayarsız kapı ValueError verir
            sayi += r["metin"].count("{{mod:") - r["metin"].count("{{mod:<")
        self.assertGreaterEqual(sayi, 6)

    def test_p028_okuma_kaynagini_soyler(self):
        p028 = next(r for r in self.kurallar if r["id"] == "P-028")
        self.assertIn("orkestra kapi durum", p028["metin"])


class KapiDurum(unittest.TestCase):
    def test_her_mod_alanli_ayar_dosyasi_listelenir(self):
        ayarlar = os.path.join(KOK, "ayarlar")
        beklenen = 0
        for ad in os.listdir(ayarlar):
            if ad.endswith(".json"):
                try:
                    with open(os.path.join(ayarlar, ad), encoding="utf-8") as f:
                        d = json.load(f)
                except ValueError:
                    continue
                beklenen += isinstance(d, dict) and isinstance(d.get("mod"), str)
        satirlar = KAPI.kapi_satirlari(None)
        self.assertEqual(len(satirlar), beklenen)
        s = {r["kapi"]: r["etkin"] for r in satirlar}
        self.assertEqual(s["best_in_class"], "ihlal")
        self.assertEqual(s["secim_ekrani_hatirlatma"], "block")

    def test_proje_ezmesi_ayri_sutunda(self):
        with tempfile.TemporaryDirectory() as sd:
            with open(os.path.join(sd, "best_in_class.json"), "w", encoding="utf-8") as f:
                json.dump({"mod": "golge"}, f)
            r = next(x for x in KAPI.kapi_satirlari(sd) if x["kapi"] == "best_in_class")
        self.assertEqual((r["varsayilan"], r["ezme"], r["etkin"]), ("ihlal", "golge", "golge"))


if __name__ == "__main__":
    unittest.main()
