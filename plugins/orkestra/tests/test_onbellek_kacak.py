"""onbellek_kacak: kaçak sınıflaması (katman_5dk, model, bosluk, sikistirma, diger), akış satırı tekilleştirme, 5 dk sayacı."""
import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import onbellek_kacak as OK  # noqa: E402

M = "claude-sonnet-5-5"


def cagri(dk, model=M, girdi=10, okuma=0, yazma=0, y5=0):
    t = datetime.datetime(2026, 10, 21, 8, 0, tzinfo=datetime.timezone.utc) + datetime.timedelta(minutes=dk)
    return [t.isoformat().replace("+00:00", "Z"), model, girdi, okuma, yazma, y5]


ONCEKI = cagri(0, okuma=200_000, yazma=1_000)


def tek(sonraki, onceki=ONCEKI):
    return OK.sinifla({"o1": [onceki, sonraki]})


class Siniflama(unittest.TestCase):
    def test_normal_cagri_kacak_degil(self):
        self.assertEqual(tek(cagri(1, okuma=200_000, yazma=2_000)), [])

    def test_kucuk_yazma_kacak_degil(self):
        self.assertEqual(tek(cagri(1, okuma=0, yazma=30_000)), [])

    def test_katman_5dk_oncelikli(self):
        o = tek(cagri(1, model="claude-opus-5-5", yazma=100_000, y5=100_000))
        self.assertEqual([x["sinif"] for x in o], ["katman_5dk"])

    def test_model_degisimi(self):
        o = tek(cagri(1, model="claude-opus-5-5", yazma=100_000))
        self.assertEqual([x["sinif"] for x in o], ["model"])

    def test_bosluk_60_dk_ve_ustu(self):
        self.assertEqual([x["sinif"] for x in tek(cagri(60, yazma=100_000))], ["bosluk"])
        self.assertEqual([x["sinif"] for x in tek(cagri(59, okuma=0, yazma=150_000))], ["diger"])

    def test_sikistirma_baglam_kuculdu(self):
        o = tek(cagri(2, okuma=20_000, yazma=60_000))
        self.assertEqual([x["sinif"] for x in o], ["sikistirma"])

    def test_usd_katman_fiyatiyla(self):
        bir_saat = tek(cagri(60, yazma=100_000))[0]["usd"]
        bes_dk = tek(cagri(1, yazma=100_000, y5=100_000))[0]["usd"]
        self.assertGreater(bir_saat, bes_dk)

    def test_sayac_son_24_saat(self):
        simdi = datetime.datetime(2026, 10, 21, 20, 0, tzinfo=datetime.timezone.utc)
        c = {"o1": [cagri(0, yazma=5, y5=5), cagri(1, yazma=5), cagri(-60 * 30, yazma=5, y5=5)]}
        self.assertEqual(OK.katman_5dk_sayisi(c, simdi), 1)


class DosyaOkuma(unittest.TestCase):
    def test_akis_satirlari_tekillesir_ilk_zaman_son_kullanim(self):
        def satir(ts, cikis, yan=False):
            return json.dumps({"type": "assistant", "timestamp": ts, "isSidechain": yan, "message": {
                "id": "m1", "model": M, "usage": {"input_tokens": 3, "cache_read_input_tokens": 7,
                                                  "cache_creation_input_tokens": 9, "output_tokens": cikis,
                                                  "cache_creation": {"ephemeral_5m_input_tokens": 4, "ephemeral_1h_input_tokens": 5}}}})
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "a.jsonl")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(satir("2026-10-21T08:00:00Z", 1) + "\n" + satir("2026-10-21T08:00:09Z", 50) + "\n"
                        + satir("2026-10-21T08:01:00Z", 1, yan=True) + "\n"
                        + json.dumps({"type": "user", "message": {"content": "x"}}) + "\n")
            self.assertEqual(OK._dosya_cagrilari(yol), [["2026-10-21T08:00:00Z", M, 3, 7, 9, 4]])


if __name__ == "__main__":
    unittest.main()
