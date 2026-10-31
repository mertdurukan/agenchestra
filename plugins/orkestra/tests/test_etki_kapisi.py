"""Plan etki kapısı (ADR-0112, I-296): gölge modda kapi_golge kaydı, şablon enjeksiyonu; geçici projede koşar."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as SIRA  # noqa: E402
import harita  # noqa: E402

KART = ("# Skill\n## Amaç\nSkill eklemek.\n## Eşanlamlılar\n- skill ekle\n"
        "## Yüzeyler\n- arayüz aç/kapa listesi (scripts/araclar_skill.py)\n- skill dosyası (skills/*/SKILL.md)\n"
        "## Değişmezler\nSKILL.md zorunlu\n")
PLAN = ("## 4. Plan maddeleri\n\n### P1 Skill ekle\n**Ne:** x\n**Etki:** {etki}\n**Kabul:** y\n\n")


class Etki(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        self.graf = os.path.join(harita.klasor_yolu(self.sd), "bilgi_grafigi")
        os.makedirs(os.path.join(self.graf, "kartlar"))
        with open(os.path.join(self.graf, "kartlar", "skill.md"), "w", encoding="utf-8") as f:
            f.write(KART)
        self.is_klasor = os.path.join(self.kok, "Claude_Orkestrasyon", "001-x")
        os.makedirs(self.is_klasor)
        self.is_json({"id": "I-1", "baslik": "Yeni skill ekle", "sira": "mevcut-durum-plan-todo", "etki": True})

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def is_json(self, d):
        with open(os.path.join(self.is_klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def plan(self, etki):
        with open(os.path.join(self.is_klasor, "plan.md"), "w", encoding="utf-8") as f:
            f.write(PLAN.format(etki=etki))

    def test_anilmayan_yuzey_eksik(self):
        self.plan("arayüz aç/kapa listesi")
        e = SIRA.etki_eksikleri(self.is_klasor)
        self.assertEqual(len(e), 1)
        self.assertIn("skill dosyası", e[0])

    def test_tum_yuzeyler_anilinca_eksik_yok(self):
        self.plan("arayüz aç/kapa listesi, skills/*/SKILL.md")
        self.assertEqual(SIRA.etki_eksikleri(self.is_klasor), [])

    def test_golge_modda_engellemez_ve_kapi_golge_yazar(self):
        self.plan("arayüz aç/kapa listesi")
        self.assertEqual(SIRA.etki_engeli(self.is_klasor), [])
        gunluk = os.path.join(self.sd, "gunluk.jsonl")
        with open(gunluk, encoding="utf-8") as f:
            kayitlar = [json.loads(s) for s in f if s.strip()]
        self.assertTrue(any(k["tur"] == "kapi_golge" and k["kapi"] == "harita_etki" for k in kayitlar))

    def test_bayraksiz_is_muaf(self):
        self.is_json({"id": "I-1", "baslik": "Yeni skill ekle", "sira": "mevcut-durum-plan-todo"})
        self.plan("")
        self.assertEqual(SIRA.etki_eksikleri(self.is_klasor), [])

    def test_sablon_iskeleti_etki_kumesini_tasir(self):
        b = SIRA.etki_bolumu(self.is_klasor)
        self.assertIn("## Etki kümesi", b)
        self.assertIn("arayüz aç/kapa listesi", b)

    def test_belge_olustur_plan_iskeleti_yuzeyi_tasir(self):
        import unittest.mock as mock
        import is_kaydi as IK
        with mock.patch.object(IK.SIRA, "plan_onkosulu", return_value=[]), \
                mock.patch.object(IK.SIRA, "mevcut_durum_yolu", return_value=None):
            yol, oldu = IK.belge_olustur(self.is_klasor, "Yeni skill ekle", "plan")
        self.assertTrue(oldu)
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        self.assertIn("## Etki kümesi", metin)
        self.assertIn("arayüz aç/kapa listesi", metin)
        self.assertIn("**Etki:**", metin)

    def test_eslesmeyen_istek_bolum_uretmez(self):
        self.is_json({"id": "I-1", "baslik": "Hava durumu", "sira": "mevcut-durum-plan-todo", "etki": True})
        self.assertEqual(SIRA.etki_bolumu(self.is_klasor), "")


if __name__ == "__main__":
    unittest.main()
