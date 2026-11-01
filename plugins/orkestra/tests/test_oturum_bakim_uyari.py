"""ADR-0145: yavaş SessionStart uyarıları bakım koşucusunda hesaplanır; hook yalnız önbellekten okur."""
import json, os, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import oturum_bakim as OB  # noqa: E402


class YavasUyarilar(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"ORKESTRA_OTURUM_BAKIM": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _onbellege_yaz(self, **kv):
        with open(os.path.join(self.sd, OB.ONBELLEK), "w", encoding="utf-8") as f:
            json.dump(kv, f)

    def test_onbellek_varsa_agir_islev_cagrilmaz(self):
        self._onbellege_yaz(uyari_hata="HATA: x", uyari_todo="todo var", bayatlik={"farkli": 1})
        with mock.patch.object(OB, "UYARI_ADIMLARI", (("uyari_hata", mock.Mock(side_effect=AssertionError)),)):
            self.assertEqual(OB.yavas_uyarilar(self.sd, None), ["HATA: x"])

    def test_onbellek_yoksa_bos(self):
        self.assertEqual(OB.yavas_uyarilar(self.sd, None), [])

    def test_kapaliyken_esdeger_sonuc_dogrudan_hesaplanir(self):
        yok = mock.Mock(return_value=None)
        var = mock.Mock(return_value="uyarı")
        with mock.patch.dict(os.environ, {"ORKESTRA_OTURUM_BAKIM": "0"}), \
                mock.patch.object(OB, "UYARI_ADIMLARI", (("a", yok), ("b", var), ("c", mock.Mock(side_effect=OSError)))):
            self.assertEqual(OB.yavas_uyarilar(self.sd, "/x"), ["uyarı"])

    def test_kosucu_adimlari_onbellege_yazar(self):
        adimlar = [(ad, f) for ad, f in OB._adimlar(self.sd, "")]
        self.assertEqual([a for a, _ in adimlar][-5:], [a for a, _ in OB.UYARI_ADIMLARI])
        with mock.patch.object(OB, "_adimlar", return_value=[("uyari_iz", lambda: "iz uyarı")]):
            self.assertTrue(OB.calistir(self.sd, ""))
        self.assertEqual(OB.onbellek(self.sd)["uyari_iz"], "iz uyarı")


if __name__ == "__main__":
    unittest.main()
