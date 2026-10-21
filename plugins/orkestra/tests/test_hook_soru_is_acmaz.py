"""I-138 P2: bağsız oturumda bilgi sorusu iş açmaz, iş isteği açar.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_hook_soru_is_acmaz.py`
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hook_yonlendirme import _Ortak  # noqa: E402
import is_kaydi  # noqa: E402  (scripts yolu test_hook_yonlendirme ile eklenir)


class SoruIsAcmaz(_Ortak):
    def idler(self):
        return {g["id"] for g in is_kaydi.is_liste(self.sd, "acik")}

    def test_bilgi_sorusu_is_acmaz(self):
        once = self.idler()
        self.istek("Bu ne demek?")
        self.assertEqual(self.idler(), once)
        self.assertFalse(self.oturum_json().get("is"))

    def test_is_istegi_is_acar(self):
        once = self.idler()
        self.istek("Şunu düzeltelim")
        self.assertEqual(len(self.idler() - once), 1)


if __name__ == "__main__":
    unittest.main()
