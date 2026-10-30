"""P-044 / ADR-0106 gölge kapısı: görünen yerleşim değişikliği maddesinin Kabul alanı tarayıcı ölçümü taşır."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S  # noqa: E402

PLAN = """### P1 Düğme konumu
**Ne:** düğmeyi sağ kenara sabitle
**Dokunulan yer:** app.css
**Kabul:** {kabul}
**Geri alma:** geri al
"""


def eksik(kabul, metin=PLAN):
    with mock.patch.object(S, "_plan_oku", return_value=metin.format(kabul=kabul)):
        return S.gorunum_olcumu_eksikleri("x")


class GorunumOlcumu(unittest.TestCase):
    def test_olcumsuz_kabul_yakalanir(self):
        self.assertEqual(len(eksik("yapıldı")), 1)  # ihlal vakası: ilk teslimdeki "genişlik sabit, yapıldı"

    def test_tarayici_olcumu_gecer(self):
        self.assertEqual(eksik("getBoundingClientRect ile tüm düğmelerin sağ kenarı eşit"), [])

    def test_gorunmeyen_is_etkilenmez(self):
        self.assertEqual(eksik("test yeşil", PLAN.replace("düğmeyi sağ kenara sabitle", "hook ekle").replace("app.css", "hook.py")), [])

    def test_golge_modda_engellemez(self):
        with mock.patch.object(S, "_plan_oku", return_value=PLAN.format(kabul="yapıldı")), \
             mock.patch.object(S, "gorunum_olcumu_kapsaminda_mi", return_value=True), \
             mock.patch("kapi_mod.kaydet", return_value=False), mock.patch("kapi_mod.mod", return_value="golge"):
            self.assertEqual(S.gorunum_olcumu_uyari("x"), [])


if __name__ == "__main__":
    unittest.main()
