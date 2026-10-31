"""I-297 P5: bölme kapısı (gölge). Yönergeden sonra ilk anlamlı araç start_session değilse kapi_golge/bolme_kapisi yazılır.
`py -3.13 -m pytest plugins/orkestra/tests/test_bolme_kapisi.py`
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402

START = "mcp__ccd_session__start_session"


class BolmeKapisiTest(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_bolme_")

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def _kayitlar(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def _kapi(self, arac, aid=None, mod="golge"):
        with mock.patch.object(hook, "_ayar_dosyasi", return_value={"mod": mod}):
            hook._bolme_kapisi(self.sd, arac, "o1", aid)

    def test_atlanan_bolme_kaydedilir(self):
        hook._bolme_bekliyor_kaydet(self.sd, "o1", "I-021")
        self._kapi("Read")
        k = [x for x in self._kayitlar() if x.get("kapi") == "bolme_kapisi"]
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["tur"], "kapi_golge")
        self.assertEqual(k[0]["is"], "I-021")

    def test_bolunen_vaka_yazmaz(self):
        hook._bolme_bekliyor_kaydet(self.sd, "o1", "I-021")
        self._kapi(START)
        self.assertEqual(self._kayitlar(), [])
        self._kapi("Read")  # bekleyen kayıt tüketildi
        self.assertEqual(self._kayitlar(), [])

    def test_toolsearch_kaydi_tuketmez(self):
        hook._bolme_bekliyor_kaydet(self.sd, "o1", "I-021")
        self._kapi("ToolSearch")
        self._kapi(START)
        self.assertEqual(self._kayitlar(), [])

    def test_alt_ajan_sayilmaz(self):
        hook._bolme_bekliyor_kaydet(self.sd, "o1", "I-021")
        self._kapi("Read", aid="alt-1")
        self.assertEqual(self._kayitlar(), [])

    def test_kapali_mod_yazmaz(self):
        hook._bolme_bekliyor_kaydet(self.sd, "o1", "I-021")
        self._kapi("Read", mod="kapali")
        self.assertEqual(self._kayitlar(), [])

    def test_ihlal_modu_reddeder(self):
        hook._bolme_bekliyor_kaydet(self.sd, "o1", "I-021")
        with mock.patch.object(hook, "reddet", side_effect=SystemExit) as r:
            with self.assertRaises(SystemExit):
                self._kapi("Read", mod="ihlal")
        self.assertTrue(r.called)

    def test_eski_kayit_gecersiz(self):
        hook._bolme_bekliyor_kaydet(self.sd, "o1", "I-021")
        d = hook._bolme_oku(self.sd)
        d["o1"]["zaman"] -= 3600
        hook._bolme_yaz(self.sd, d)
        self._kapi("Read")
        self.assertEqual(self._kayitlar(), [])


if __name__ == "__main__":
    unittest.main()
