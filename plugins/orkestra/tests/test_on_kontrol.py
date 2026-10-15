"""on_kontrol.py (T0 ön kontrol kapısı) testleri. Geçici projede çalışır; ağ/model yok."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import on_kontrol as OK  # noqa: E402

# test_komutu: bayrak dosyalarına göre pytest biçiminde FAILED satırı basar
TEST_BETIGI = (
    "import os, sys\n"
    "bad = [n for n in ('a', 'b') if os.path.exists('dus_' + n)]\n"
    "for n in bad:\n"
    "    print('FAILED t.py::test_' + n + ' - x')\n"
    "sys.exit(1 if bad else 0)\n"
)


class Taban(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = self.tmp.name
        os.makedirs(os.path.join(self.p, ".claude", "orkestra", "gorevler"))
        os.makedirs(os.path.join(self.p, "src"))
        with open(os.path.join(self.p, "t.py"), "w") as f:
            f.write(TEST_BETIGI)
        self.dosya = os.path.join(self.p, "src", "x.txt")
        self.yaz(b"a\nb\n")

    def tearDown(self):
        self.tmp.cleanup()

    def yaz(self, veri, yol=None):
        with open(yol or self.dosya, "wb") as f:
            f.write(veri)

    def kart(self, **ek):
        k = {"id": "G-1", "yazma_alani": ["src/*.txt"], "test_komutu": f'"{sys.executable}" t.py'}
        k.update(ek)
        with open(os.path.join(self.p, ".claude", "orkestra", "gorevler", "G-1.json"), "w", encoding="utf-8") as f:
            json.dump(k, f)

    def kos(self, *args):
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            kod = OK.main(list(args) + ["--proje", self.p])
        return kod, json.loads(cikti.getvalue())

    def taban(self):
        self.assertEqual(self.kos("taban", "G-1")[0], 0)

    def turler(self, sonuc):
        return [i["tur"] for i in sonuc["ihlaller"]]

    def test_temiz_gecer(self):
        self.kart(); self.taban()
        kod, s = self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.assertEqual((kod, s["gecti"], s["ihlaller"]), (0, True, []))
        self.assertIn("sure_sn", s)

    def test_crlf_degisimi(self):
        self.kart(test_komutu=None); self.taban()
        self.yaz(b"a\r\nb\r\n")
        kod, s = self.kos("kontrol", "G-1")
        self.assertEqual(kod, 4)
        self.assertEqual(self.turler(s), ["satir-sonu"])

    def test_bom_eklenmesi(self):
        self.kart(test_komutu=None); self.taban()
        self.yaz(b"\xef\xbb\xbfa\nb\n")
        kod, s = self.kos("kontrol", "G-1")
        self.assertEqual(kod, 4)
        self.assertEqual(self.turler(s), ["bom"])

    def test_kapsam_disi_cikti(self):
        self.kart(test_komutu=None); self.taban()
        disari = os.path.join(self.p, "baska", "y.txt")
        kod, s = self.kos("kontrol", "G-1", "--ciktilar", f"{self.dosya},{disari}")
        self.assertEqual(kod, 4)
        self.assertEqual(self.turler(s), ["kapsam"])
        self.assertIn("y.txt", s["ihlaller"][0]["ayrinti"])

    def test_tabanda_dusen_test_ihlal_degil(self):
        open(os.path.join(self.p, "dus_a"), "w").close()
        self.kart(); self.taban()
        kod, s = self.kos("kontrol", "G-1")
        self.assertEqual(kod, 0)
        self.assertEqual(s["onceden_dusen"], ["t.py::test_a"])

    def test_yeni_dusen_test_ihlal(self):
        open(os.path.join(self.p, "dus_a"), "w").close()
        self.kart(); self.taban()
        open(os.path.join(self.p, "dus_b"), "w").close()
        kod, s = self.kos("kontrol", "G-1")
        self.assertEqual(kod, 4)
        self.assertEqual(s["ihlaller"], [{"tur": "yeni-test-hatasi", "ayrinti": ["t.py::test_b"]}])
        self.assertEqual(s["onceden_dusen"], ["t.py::test_a"])

    def test_taban_yok_atlanir(self):
        self.kart()
        open(os.path.join(self.p, "dus_a"), "w").close()
        kod, s = self.kos("kontrol", "G-1")
        self.assertEqual(kod, 0)
        self.assertIn("taban-yok", s["uyarilar"])

    def test_kullanim_hatasi(self):
        self.kart()
        self.assertEqual(self.kos("kontrol", "YOK-9")[0], 2)

    def test_eksik_token_ihlal(self):
        self.kart(test_komutu=None); self.taban()
        kaynak = os.path.join(self.p, "kaynak.md")
        self.yaz("Pay %59,5, 742 bin ve 1.787 satır; bkz. §4 ST-123 ile G5a.".encode("utf-8"), kaynak)
        self.yaz("Pay %59,5 ve 1.787; ST-123".encode("utf-8"))
        kod, s = self.kos("kontrol", "G-1", "--ciktilar", self.dosya, "--kaynak", kaynak)
        self.assertEqual(kod, 4)
        self.assertEqual(self.turler(s), ["eksik-token"])
        eksik = s["ihlaller"][0]["ayrinti"]
        self.assertEqual(sorted(eksik), sorted(["742", "§4", "G5a"]))

    def test_kaynak_yokken_token_atlanir(self):
        self.kart(test_komutu=None); self.taban()
        kod, s = self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.assertEqual(kod, 0)
        self.assertNotIn("eksik-token", self.turler(s))


if __name__ == "__main__":
    unittest.main()
