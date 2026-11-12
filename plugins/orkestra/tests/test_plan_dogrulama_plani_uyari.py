"""I-461 P5: sözleşmeli işte plan yazımında eksik doğrulama planı gölge uyarı alır."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, _SCRIPTS)
import is_sirasi as S  # noqa: E402

SOZLESME = """# Sözleşme

## Başarı kriterleri

- **S1:** Birinci kriter.
- **S2:** İkinci kriter.
"""
PLAN_T_YOK = "# Plan\n\n### P1 Baslik\n\nGovde.\n"
PLAN_T_VAR = PLAN_T_YOK + "\n## Doğrulama planı\n\n- **T1:** S1, S2 — `python -m pytest -q`\n"
PLAN_T_KISMI = PLAN_T_YOK + "\n## Doğrulama planı\n\n- **T1:** S1 — `python -m pytest -q`\n"


class DogrulamaPlaniUyari(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="dp_uyari_")
        yama = mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_SOZLESME_KAPISI": "1"})
        yama.start()
        self.addCleanup(yama.stop)
        with open(os.path.join(self.kok, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-9", "sira": "mevcut-durum-plan-todo", "sozlesme": True}, f)
        with open(os.path.join(self.kok, "sozlesme_20261112.md"), "w", encoding="utf-8") as f:
            f.write(SOZLESME)

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def _golge(self, metin):
        return S.plan_yazim_eksikleri(self.kok, metin)[1]

    def test_t_siz_plan_golgede(self):
        e = [x for x in self._golge(PLAN_T_YOK) if "Doğrulama planı" in x]
        self.assertEqual(len(e), 1)

    def test_t_li_plan_temiz(self):
        self.assertEqual([x for x in self._golge(PLAN_T_VAR) if "doğrulama planı" in x.lower()], [])

    def test_anilmayan_s_golgede(self):
        self.assertIn("S2: doğrulama planında T yok", self._golge(PLAN_T_KISMI))

    def test_sozlesmesiz_is_bos(self):
        os.remove(os.path.join(self.kok, "sozlesme_20261112.md"))
        with open(os.path.join(self.kok, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-9", "sira": "mevcut-durum-plan-todo"}, f)
        self.assertEqual(S.dogrulama_plani_eksikleri(self.kok, PLAN_T_YOK), [])


if __name__ == "__main__":
    unittest.main()
