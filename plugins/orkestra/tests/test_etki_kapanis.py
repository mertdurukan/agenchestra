"""Kapanışta etki yeniden doğrulama (ADR-0118, I-296): işlenmemiş yüzey gölge kaydı üretir, işlenmişse üretmez."""
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


class EtkiKapanis(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        graf = os.path.join(harita.klasor_yolu(self.sd), "bilgi_grafigi", "kartlar")
        os.makedirs(graf)
        with open(os.path.join(graf, "skill.md"), "w", encoding="utf-8") as f:
            f.write(KART)
        self.klasor = os.path.join(self.kok, "Claude_Orkestrasyon", "001-x")
        os.makedirs(self.klasor)
        with open(os.path.join(self.klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-1", "baslik": "Yeni skill ekle", "sira": "mevcut-durum-plan-todo", "etki": True,
                       "olusturma": "2026-01-01T00:00:00+00:00"}, f)

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def test_islenmemis_yuzey_golge_kaydi_uretir(self):
        e = SIRA.etki_kapanis_eksikleri(self.klasor, {"skills/yeni/SKILL.md"})
        self.assertEqual(len(e), 1)
        self.assertIn("arayüz aç/kapa listesi", e[0])

    def test_kapanis_kaydi_engellemez_ve_kapi_golge_yazar(self):
        import unittest.mock as mock
        with mock.patch.object(SIRA, "degisen_dosyalar", return_value={"skills/yeni/SKILL.md"}):
            self.assertEqual(SIRA.etki_kapanis_kaydi(self.klasor), [])
        self.assertTrue(any(k["tur"] == "kapi_golge" and k["kapi"] == "harita_etki" for k in self.gunluk()))

    def test_tum_yuzeyler_islenmisse_kayit_yok(self):
        degisen = {"skills/yeni/SKILL.md", "scripts/araclar_skill.py"}
        self.assertEqual(SIRA.etki_kapanis_eksikleri(self.klasor, degisen), [])
        import unittest.mock as mock
        with mock.patch.object(SIRA, "degisen_dosyalar", return_value=degisen):
            SIRA.etki_kapanis_kaydi(self.klasor)
        self.assertEqual(self.gunluk(), [])

    def test_biten_p_yazma_alani_islenmis_sayilir(self):
        with open(os.path.join(self.klasor, "plan.md"), "w", encoding="utf-8") as f:
            f.write("## 4. Plan maddeleri\n\n### P1 x\n**Ne:** x\n**Yazma alanı:** scripts/araclar_skill.py, skills/yeni/SKILL.md\n\n")
        with open(os.path.join(self.klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("- [x] P1 x\n")
        self.assertEqual(SIRA.etki_kapanis_eksikleri(self.klasor, set()), [])


if __name__ == "__main__":
    unittest.main()
