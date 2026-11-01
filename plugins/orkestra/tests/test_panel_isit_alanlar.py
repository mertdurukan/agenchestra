"""panel._isit: açılış ısıtması alan listesini önbellekli /alanlar.json uç noktasından ister ve ağır uç noktalardan ÖNCE;
tarayıcının ilk /alanlar.json isteği soğuk üretimi (tüm transkript taraması) ısıtmayla yarışarak beklemez."""
import json
import os
import sys
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import panel  # noqa: E402


class _Yanit:
    def __init__(self, govde):
        self.govde = govde

    def read(self):
        return self.govde


class IsitAlanlar(unittest.TestCase):
    def test_ilk_istek_alanlar_json_sonra_agir_uclar(self):
        istenen = []

        def sahte(url, timeout=0):
            istenen.append(url)
            if url.endswith("/alanlar.json"):
                return _Yanit(json.dumps([{"id": "a1", "orkestra": True}, {"id": "a2", "orkestra": False}]).encode())
            return _Yanit(b"{}")

        with mock.patch.object(panel.urllib.request, "urlopen", sahte):
            panel._isit(1234)
        self.assertEqual(istenen[0], "http://127.0.0.1:1234/alanlar.json")
        self.assertIn("http://127.0.0.1:1234/isler.json?alan=a1", istenen)
        self.assertNotIn("http://127.0.0.1:1234/isler.json?alan=a2", istenen)   # orkestrasız alan ısıtılmaz

    def test_alan_listesi_alinamazsa_isitma_sessizce_biter(self):
        def sahte(url, timeout=0):
            raise OSError("sunucu yok")

        with mock.patch.object(panel.urllib.request, "urlopen", sahte):
            self.assertIsNone(panel._isit(1234))


if __name__ == "__main__":
    unittest.main()
