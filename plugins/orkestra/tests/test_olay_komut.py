"""orkestra olay komutu ve perspektif olay bölümü (I-286 P5)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import perspektif_gunluk as PG  # noqa: E402
import olay_kaydi as O  # noqa: E402

CLI = os.path.join(KOK, "scripts", "orkestra.py")


def durum_klasoru(d):
    sd = os.path.join(d, ".claude", "orkestra")
    os.makedirs(sd)
    satir = [{"zaman": "2026-10-01T10:00:00+03:00", "tur": "kapi_ret", "kapi": "adr", "neden": "n"},
             {"zaman": "2026-10-01T10:00:00+03:00", "tur": "onay-ekran", "bicim": "b"},
             {"zaman": "2026-10-01T10:00:00+03:00", "tur": "kural_ihlal", "kural": "secim_ekrani"},
             {"zaman": "2026-10-01T10:00:00+03:00", "tur": "istek", "metin": "hayır, bunu istemedim"}]
    with open(os.path.join(sd, "gunluk.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(x) for x in satir))
    return sd


class OlayKomutTesti(unittest.TestCase):
    def test_komut_dort_turu_ve_kapi_modunu_gosterir(self):
        with tempfile.TemporaryDirectory() as d:
            durum_klasoru(d)
            r = subprocess.run([sys.executable, CLI, "olay", "--json"], cwd=d, capture_output=True, text=True,
                               encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"))
            self.assertEqual(r.returncode, 0, r.stderr)
            o = json.loads(r.stdout)
            self.assertEqual(sorted(o["tur"]), ["kapi_ret", "karar", "kullanici_duzeltme", "yanlis_oneri"])
            self.assertEqual(o["kapi_modu"], "golge")

    def test_perspektif_olay_bolumu_ve_mevcut_anahtarlar(self):
        with tempfile.TemporaryDirectory() as d:
            sd = durum_klasoru(d)
            import datetime
            o = PG.ozet(sd, datetime.datetime(2026, 9, 1).astimezone(), datetime.datetime(2026, 10, 30).astimezone())
            self.assertEqual(o["olay"]["toplam"], 4)
            for k in ("kapi_golge", "kapi_ret", "kural_ihlal", "hata", "denetim_payi"):
                self.assertIn(k, o)

    def test_olay_bolumu_pencereye_uyar(self):
        import datetime
        with tempfile.TemporaryDirectory() as d:
            sd = durum_klasoru(d)
            bos = PG.ozet(sd, datetime.datetime(2026, 9, 1).astimezone(), datetime.datetime(2026, 9, 30).astimezone())
            self.assertEqual(bos["olay"]["toplam"], 0)

    def test_okuyucu_hata_verirse_perspektif_bozulmaz(self):
        orijinal = O.oku_sd
        O.oku_sd = lambda *a, **k: 1 / 0
        try:
            with tempfile.TemporaryDirectory() as d:
                self.assertEqual(PG.ozet(durum_klasoru(d))["olay"], {})
        finally:
            O.oku_sd = orijinal


if __name__ == "__main__":
    unittest.main()
