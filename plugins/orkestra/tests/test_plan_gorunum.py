import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S
import plan_gorunum as PG

PLAN = ("# T: plan\n\n## 4. Plan maddeleri\n\n### P1 Saldırı mesajları engellenir\n\n**Ne:** Kapı eklenir.\n\n"
        "**Kabul:** 5 mesajın 5'i engellenir\n")
TODO = "# Yapılacaklar — T\n\n- [ ] P1: Kapıyı yaz\n"


class PlanGorunum(unittest.TestCase):
    def test_todo_gorunumu_bitti_sayilir_etiketi_yok_ve_baslik_duz(self):
        g = PG.todo_gorunumu(TODO, PLAN)
        self.assertNotIn("Bitti sayılır", g)
        self.assertIn("## 1. Saldırı mesajları engellenir", g)
        self.assertIn("5 mesajın 5'i engellenir", g)

    def test_gap_satiri_numarali_ve_g_oneki_kabul(self):
        for satir in ("- **1.** hedef → mevcut → fark", "- **G1:** hedef → mevcut → fark", "- **1:** x"):
            self.assertEqual(S._GAP_SATIRI.findall(satir), ["1"], satir)


if __name__ == "__main__":
    unittest.main()
