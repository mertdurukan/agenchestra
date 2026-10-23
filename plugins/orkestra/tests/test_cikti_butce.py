"""P-001 / ADR-0075: kullanıcı çıktısı bütçesi (scripts/cikti_butce.py), Stop hook bağlantısı ve rapor sayacı.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_cikti_butce.py`
Hepsi geçici projede koşar; sınırlar testte sabitlenmez, ayardan okunur.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import cikti_butce as CB  # noqa: E402
import hook  # noqa: E402
import is_rapor  # noqa: E402

OTURUM = "cikti12345678-oturum"


def _satir(tur, **kw):
    return json.dumps({"type": tur, **kw}, ensure_ascii=False)


def _transkript(yol, metinler, kutu_sonrasi=None):
    """Tek tur: kullanıcı mesajı, ana ajan metinleri, istenirse wrap_up çağrısı ve ardından kapanış metni."""
    s = [_satir("user", message={"content": "iş yap"})]
    for m in metinler:
        s.append(_satir("assistant", message={"content": [{"type": "text", "text": m}]}))
    if kutu_sonrasi is not None:
        s.append(_satir("assistant", message={"content": [{"type": "tool_use", "name": "mcp__ccd_turn__wrap_up", "input": {}}]}))
        s.append(_satir("assistant", message={"content": [{"type": "text", "text": kutu_sonrasi}]}))
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(s) + "\n")


class CiktiButceTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sd = os.path.join(self.d, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.tr = os.path.join(self.d, "t.jsonl")
        self.ayar = CB.ayar_oku()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_ayar_golge_ve_sinirlar(self):
        self.assertEqual(self.ayar["mod"], "golge")
        self.assertEqual((self.ayar["tur_siniri"], self.ayar["kapanis_siniri"]), (800, 300))

    def test_uzun_kapanis_yakalanir(self):
        _transkript(self.tr, ["kısa"], kutu_sonrasi="x" * 1200)
        o = CB.tur_olc(self.tr)
        self.assertEqual(o["kapanis"], 1200)
        self.assertTrue(CB.asimlar(o, self.ayar))

    def test_kisa_kapanis_yakalanmaz(self):
        _transkript(self.tr, ["kısa"], kutu_sonrasi="x" * 200)
        o = CB.tur_olc(self.tr)
        self.assertEqual(CB.asimlar(o, self.ayar), [])

    def test_kutu_yoksa_kapanis_none(self):
        _transkript(self.tr, ["a" * 100, "b" * 50])
        o = CB.tur_olc(self.tr)
        self.assertEqual((o["toplam"], o["kapanis"]), (150, None))

    def test_yan_ajan_ve_onceki_tur_sayilmaz(self):
        s = [_satir("user", message={"content": "eski"}),
             _satir("assistant", message={"content": [{"type": "text", "text": "e" * 5000}]}),
             _satir("user", message={"content": "yeni"}),
             _satir("assistant", isSidechain=True, message={"content": [{"type": "text", "text": "y" * 5000}]}),
             _satir("assistant", message={"content": [{"type": "text", "text": "a" * 70}]})]
        with open(self.tr, "w", encoding="utf-8") as f:
            f.write("\n".join(s) + "\n")
        self.assertEqual(CB.tur_olc(self.tr)["toplam"], 70)

    def test_son_mesaj_transkriptte_yoksa_eklenir(self):
        _transkript(self.tr, ["a" * 100])
        self.assertEqual(CB.tur_olc(self.tr, son_mesaj="b" * 40)["toplam"], 140)

    def test_okunamayan_transkript_none(self):
        self.assertIsNone(CB.tur_olc(os.path.join(self.d, "yok.jsonl")))
        self.assertIsNone(CB.tur_olc(None))

    def test_hook_olcum_ve_golge_yazar_engellemez(self):
        _transkript(self.tr, ["kısa"], kutu_sonrasi="x" * 1200)
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            hook._cikti_butce_yanit(self.sd, OTURUM, {"transcript_path": self.tr})
        self.assertEqual(cikti.getvalue(), "")  # engelleme yok
        g = self._gunluk()
        self.assertEqual([x["tur"] for x in g], ["cikti_olcum", "kapi_golge"])
        self.assertEqual(g[1]["kapi"], "cikti_butce")

    def test_hook_kisa_turda_yalniz_olcum(self):
        _transkript(self.tr, ["kısa"], kutu_sonrasi="x" * 200)
        hook._cikti_butce_yanit(self.sd, OTURUM, {"transcript_path": self.tr})
        self.assertEqual([x["tur"] for x in self._gunluk()], ["cikti_olcum"])

    def test_ortam_degiskeni_kapatir(self):
        _transkript(self.tr, ["kısa"], kutu_sonrasi="x" * 1200)
        eski = os.environ.get("ORKESTRA_CIKTI_BUTCE")
        os.environ["ORKESTRA_CIKTI_BUTCE"] = "0"
        try:
            hook._cikti_butce_yanit(self.sd, OTURUM, {"transcript_path": self.tr})
        finally:
            if eski is None:
                os.environ.pop("ORKESTRA_CIKTI_BUTCE")
            else:
                os.environ["ORKESTRA_CIKTI_BUTCE"] = eski
        self.assertEqual(self._gunluk(), [])

    def test_rapor_ortanca_p90_ve_karar(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            for i in range(10):
                f.write(json.dumps({"tur": "cikti_olcum", "toplam": 100 * (i + 1), "kapanis": None if i % 2 else 50}) + "\n")
        c = is_rapor._cikti(self.sd)
        self.assertEqual((c["tur"], c["ortanca"], c["p90"]), (10, 600, 1000))
        self.assertAlmostEqual(c["asim_orani"], 0.2)
        self.assertIn("yetersiz örnek", c["karar"])

    def test_rapor_200_tur_karari(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            for _ in range(200):
                f.write(json.dumps({"tur": "cikti_olcum", "toplam": 300, "kapanis": None}) + "\n")
        self.assertIn("hedef tutuyor", is_rapor._cikti(self.sd)["karar"])
        with open(yol, "w", encoding="utf-8") as f:
            for _ in range(200):
                f.write(json.dumps({"tur": "cikti_olcum", "toplam": 900, "kapanis": None}) + "\n")
        self.assertIn("ihlal geçişi önerilir", is_rapor._cikti(self.sd)["karar"])

    def test_rapor_veri_yoksa_none(self):
        self.assertIsNone(is_rapor._cikti(self.sd))


if __name__ == "__main__":
    unittest.main()
