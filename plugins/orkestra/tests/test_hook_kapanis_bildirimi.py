"""I-461 P3: SessionStart hook'u iş kapatmaz, 'kapanabilir' diye bildirir.
`python -m unittest plugins/orkestra/tests/test_hook_kapanis_bildirimi.py`
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_hook_yonlendirme as ty  # noqa: E402


class KapanisBildirimi(ty._Ortak):
    def _acik(self):
        return [g["id"] for g in ty.is_kaydi.is_liste(self.sd, "acik")]

    def test_todo_biten_is_acik_kalir_ve_kapanabilir_der(self):
        a = self.is_ac("Bitmiş iş başlığı", "001-bitmis")
        self.todo_yaz(a, "# T\n\n- [x] bir\n- [x] iki\n")
        p = self.parca(self.acilis(), a["id"])
        self.assertIn("kapanabilir", p)
        self.assertIn("orkestra is kapat " + a["id"], p)
        self.assertNotIn("otomatik kapandı", p)
        self.assertIn(a["id"], self._acik())

    def test_acik_kart_varsa_bildirim_yok(self):
        a = self.is_ac("Kartlı iş başlığı", "001-kartli")
        self.todo_yaz(a, "# T\n\n- [x] bir\n")
        self.kart_yaz("G-001", a["id"], "isleniyor")
        self.assertNotIn("kapanabilir", self.parca(self.acilis(), a["id"]))
        self.assertIn(a["id"], self._acik())


if __name__ == "__main__":
    unittest.main()
