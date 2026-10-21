"""I-139 P8 (bce F49/F50): `orkestra isabet` - anılan dosyalar ile commit'te değişen dosyaların kesinlik ve duyarlılığı."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import isabet as IS  # noqa: E402

ICERIDE = "2026-01-10T10:00:00+00:00"
DISARIDA = "2026-01-05T10:00:00+00:00"


def _yaz(kok, goreli, metin="x\n"):
    yol = os.path.join(kok, goreli)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)


def _commit(kok, tarih, mesaj):
    ortam = dict(os.environ, GIT_AUTHOR_DATE=tarih, GIT_COMMITTER_DATE=tarih)
    subprocess.run(["git", "-C", kok, "add", "-A"], check=True, env=ortam, capture_output=True)
    subprocess.run(["git", "-C", kok, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", mesaj],
                   check=True, env=ortam, capture_output=True)


class Isabet(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_isabet_")
        subprocess.run(["git", "-C", self.kok, "init", "-q"], check=True, capture_output=True)
        _yaz(self.kok, "src/x.py")  # pencere dışı; planda anılır, değişmemiştir
        _commit(self.kok, DISARIDA, "once")
        _yaz(self.kok, "src/a.py")
        _yaz(self.kok, "src/b.py")
        _yaz(self.kok, "src/c.py")
        _yaz(self.kok, "is1/plan.md", "# Plan\n\n- `src/a.py` değişir\n- `src/x.py` okunur\n- `src/zz.py` okunur\n")
        _commit(self.kok, ICERIDE, "is")
        self.kayit = {"id": "I-1", "baslik": "deneme", "durum": "kapandi", "klasor": os.path.join(self.kok, "is1"),
                      "olusturma": "2026-01-10T09:00:00+00:00",
                      "gecmis": [{"zaman": "2026-01-10T12:00:00+00:00", "olay": "durum:kapandi"}]}

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def test_elle_hesaplanan_kesinlik_ve_duyarlilik(self):
        s = IS.olc(self.kayit, [self.kok], [self.kok])
        # anılan ve diskte var: a, x (zz yok). Değişen: a, b, c (is1/ kendi klasörü ve pencere dışı x çıkar).
        self.assertEqual((s["anilan"], s["degisen"], s["isabet"]), (2, 3, 1))
        self.assertEqual(s["kesinlik"], 0.5)
        self.assertEqual(s["duyarlilik"], 0.333)
        self.assertEqual(s["kacirilan"], sorted(IS.norm(os.path.join(self.kok, f"src/{d}.py")) for d in "bc"))

    def test_tahmin_anilanin_yerini_alir(self):
        yollar = [os.path.join(self.kok, "src", d) for d in ("a.py", "b.py")]
        s = IS.olc(self.kayit, [self.kok], [self.kok], tahmin=lambda k: yollar)
        self.assertEqual((s["anilan"], s["isabet"], s["kesinlik"], s["duyarlilik"]), (2, 2, 1.0, 0.667))

    def test_kapanmamis_is_olculmez(self):
        self.assertIsNone(IS.olc(dict(self.kayit, durum="acik"), [self.kok], [self.kok]))

    def test_toplam_mikro_ortalama(self):
        t = IS.toplam([{"anilan": 2, "degisen": 3, "isabet": 1}, {"anilan": 0, "degisen": 1, "isabet": 0}])
        self.assertEqual((t["is_sayisi"], t["anilan"], t["degisen"], t["isabet"]), (2, 2, 4, 1))
        self.assertEqual((t["kesinlik"], t["duyarlilik"]), (0.5, 0.25))
        self.assertEqual(IS.toplam([])["kesinlik"], None)


class IsabetCLI(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def test_kapanmis_is_yoksa_bos_mesaj_ve_json(self):
        subprocess.run(["git", "-C", self.proje, "init", "-q"], check=True, capture_output=True)
        r = TC.kos([TC.CLI, "isabet"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kapanmış iş yok", r.stdout)
        j = TC.kos([TC.CLI, "isabet", "--json"], self.proje)
        self.assertEqual(json.loads(j.stdout)["toplam"]["is_sayisi"], 0)


if __name__ == "__main__":
    unittest.main()
