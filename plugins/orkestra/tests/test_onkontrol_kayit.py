"""on_kontrol.py kontrol: koşuların karta kalıcı yazılması (onkontrol_kosulari). Geçici proje; ağ/model yok."""
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

TEST_BETIGI = (
    "import os, sys\n"
    "bad = [n for n in ('a', 'b') if os.path.exists('dus_' + n)]\n"
    "for n in bad:\n"
    "    print('FAILED t.py::test_' + n + ' - x')\n"
    "sys.exit(1 if bad else 0)\n"
)
IZINLI = {"kapsam", "bom", "satir-sonu", "yeni-test-hatasi", "eksik-token"}


class Kayit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = self.tmp.name
        self.gd = os.path.join(self.p, ".claude", "orkestra", "gorevler")
        os.makedirs(self.gd)
        os.makedirs(os.path.join(self.p, "src"))
        with open(os.path.join(self.p, "t.py"), "w") as f:
            f.write(TEST_BETIGI)
        self.dosya = os.path.join(self.p, "src", "x.txt")
        self.yaz(b"a\nb\n")
        self.kart_yolu = os.path.join(self.gd, "G-1.json")

    def tearDown(self):
        self.tmp.cleanup()

    def yaz(self, veri, yol=None):
        with open(yol or self.dosya, "wb") as f:
            f.write(veri)

    def kart(self, **ek):
        k = {"id": "G-1", "baslik": "B", "durum": "isleniyor", "yazma_alani": ["src/*.txt"],
             "test_komutu": f'"{sys.executable}" t.py', "ciktilar": [self.dosya], "ozel_alan": {"x": [1, 2]}}
        k.update(ek)
        with open(self.kart_yolu, "w", encoding="utf-8") as f:
            json.dump(k, f)

    def kart_oku(self):
        with open(self.kart_yolu, encoding="utf-8") as f:
            return json.load(f)

    def kos(self, *args):
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            kod = OK.main(list(args) + ["--proje", self.p])
        return kod, json.loads(cikti.getvalue())

    def taban(self):
        self.assertEqual(self.kos("taban", "G-1")[0], 0)

    def kayitlar(self):
        return self.kart_oku().get("onkontrol_kosulari", [])

    def yazma_bozuk(self):
        """Karta atomik yazımı OSError'a çeviren bağlam; diğer dosyalar normal yazılır."""
        orijinal = OK.L.atomik_yaz

        def bozuk(yol, *a, **k):
            if str(yol).replace("\\", "/").endswith("gorevler/G-1.json"):
                raise OSError("yazılamaz")
            return orijinal(yol, *a, **k)

        @contextlib.contextmanager
        def ctx():
            OK.L.atomik_yaz = bozuk
            try:
                yield
            finally:
                OK.L.atomik_yaz = orijinal
        return ctx()

    # 1
    def test_gecen_kontrol_kaydi(self):
        self.kart(); self.taban()
        kod, s = self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.assertEqual((kod, s["gecti"]), (0, True))
        k = self.kayitlar()
        self.assertEqual(len(k), 1)
        self.assertIs(k[0]["gecti"], True)
        self.assertEqual(k[0]["ihlal_turleri"], [])
        for alan in ("zaman", "sira", "agent_id", "cikti_ozeti_sha"):
            self.assertIn(alan, k[0])
        self.assertIsInstance(k[0]["sira"], int)
        self.assertTrue(k[0]["zaman"])
        self.assertNotIn("kapi_sinifi", k[0])
        self.assertNotIn("sinif", k[0])

    def test_agent_id_verilmezse_null_verilirse_yazilir(self):
        self.kart(); self.taban()
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya, "--ajan-id", "abc123")
        k = self.kayitlar()
        self.assertIsNone(k[0]["agent_id"])
        self.assertEqual(k[1]["agent_id"], "abc123")

    # 2
    def _ihlal(self, beklenen):
        k = self.kayitlar()
        self.assertEqual(len(k), 1)
        self.assertIs(k[0]["gecti"], False)
        self.assertIn(beklenen, k[0]["ihlal_turleri"])
        self.assertTrue(set(k[0]["ihlal_turleri"]) <= IZINLI)

    def test_kapsam_ihlali(self):
        self.kart(); self.taban()
        dis = os.path.join(self.p, "baska.txt")
        self.yaz(b"x\n", dis)
        kod, _ = self.kos("kontrol", "G-1", "--ciktilar", dis)
        self.assertEqual(kod, 4)
        self._ihlal("kapsam")

    def test_bom_ihlali(self):
        self.kart(test_komutu=None); self.taban()
        self.yaz(b"\xef\xbb\xbfa\nb\n")
        kod, _ = self.kos("kontrol", "G-1")
        self.assertEqual(kod, 4)
        self._ihlal("bom")

    def test_satir_sonu_ihlali(self):
        self.kart(test_komutu=None); self.taban()
        self.yaz(b"a\r\nb\r\n")
        kod, _ = self.kos("kontrol", "G-1")
        self.assertEqual(kod, 4)
        self._ihlal("satir-sonu")

    def test_yeni_test_hatasi_ihlali(self):
        self.kart(); self.taban()
        open(os.path.join(self.p, "dus_a"), "w").close()
        kod, _ = self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.assertEqual(kod, 4)
        self._ihlal("yeni-test-hatasi")

    def test_eksik_token_ihlali(self):
        self.kart(test_komutu=None); self.taban()
        kaynak = os.path.join(self.p, "kaynak.md")
        self.yaz("Oran 42 ve §3.1 ve PE-636\n".encode(), kaynak)
        kod, _ = self.kos("kontrol", "G-1", "--ciktilar", self.dosya, "--kaynak", kaynak)
        self.assertEqual(kod, 4)
        self._ihlal("eksik-token")

    def test_birden_cok_ihlal_turu_tek_kayit(self):
        self.kart(test_komutu=None); self.taban()
        self.yaz(b"\xef\xbb\xbfa\r\nb\r\n")
        dis = os.path.join(self.p, "baska.txt")
        self.yaz(b"x\n", dis)
        kod, _ = self.kos("kontrol", "G-1", "--ciktilar", dis)
        self.assertEqual(kod, 4)
        k = self.kayitlar()
        self.assertEqual(len(k), 1)
        self.assertEqual(sorted(k[0]["ihlal_turleri"]), ["bom", "kapsam", "satir-sonu"])

    # 3
    def test_ardisik_iki_kayit_artan_sira_alanlar_korunur(self):
        self.kart(); self.taban()
        once = self.kart_oku()
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        k = self.kayitlar()
        self.assertEqual(len(k), 2)
        self.assertLess(k[0]["sira"], k[1]["sira"])
        son = self.kart_oku()
        for ad in ("id", "baslik", "durum", "yazma_alani", "test_komutu", "ciktilar", "ozel_alan"):
            self.assertEqual(son[ad], once[ad], ad)

    def test_onceki_kayitlar_korunur_sira_devam_eder(self):
        eski = {"zaman": "2026-01-01T00:00:00+03:00", "sira": 7, "agent_id": None, "gecti": True,
                "ihlal_turleri": [], "cikti_ozeti_sha": "0" * 64}
        self.kart(onkontrol_kosulari=[eski], olay_sira=7); self.taban()
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        k = self.kayitlar()
        self.assertEqual(len(k), 2)
        self.assertEqual(k[0], eski)
        self.assertGreater(k[1]["sira"], 7)

    # 4
    def test_cikti_ozeti_sha_icerige_baglidir(self):
        self.kart(); self.taban()
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.yaz(b"a\nb\nc\n")
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        k = self.kayitlar()
        self.assertRegex(k[0]["cikti_ozeti_sha"], r"^[0-9a-f]{64}$")
        self.assertEqual(k[0]["cikti_ozeti_sha"], k[1]["cikti_ozeti_sha"])
        self.assertNotEqual(k[1]["cikti_ozeti_sha"], k[2]["cikti_ozeti_sha"])

    def test_cikti_ozeti_sha_dosya_kumesine_baglidir(self):
        self.kart(); self.taban()
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        ikinci = os.path.join(self.p, "src", "y.txt")
        self.yaz(b"y\n", ikinci)
        k = self.kart_oku()
        k["ciktilar"] = [self.dosya, ikinci]
        with open(self.kart_yolu, "w", encoding="utf-8") as f:
            json.dump(k, f)
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        s = self.kayitlar()
        self.assertEqual(len(s), 2)
        self.assertNotEqual(s[0]["cikti_ozeti_sha"], s[1]["cikti_ozeti_sha"])

    # 5
    def test_kart_yoksa_cokmez_eski_cikis_kodu(self):
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            kod = OK.main(["kontrol", "G-yok", "--proje", self.p])
        self.assertEqual(kod, 2)
        self.assertFalse(os.path.exists(os.path.join(self.gd, "G-yok.json")))

    def test_kart_yazilamazsa_gecen_kontrol_cokmez(self):
        self.kart(); self.taban()
        with self.yazma_bozuk():
            kod, s = self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        self.assertEqual((kod, s["gecti"]), (0, True))
        self.assertNotIn("onkontrol_kosulari", self.kart_oku())

    def test_kart_yazilamazsa_ihlal_cikis_kodu_4_kalir(self):
        self.kart(test_komutu=None); self.taban()
        self.yaz(b"a\r\nb\r\n")
        with self.yazma_bozuk():
            kod, s = self.kos("kontrol", "G-1")
        self.assertEqual((kod, s["gecti"]), (4, False))

    def test_onkontrol_json_davranisi_degismez(self):
        self.kart(); self.taban()
        yol = os.path.join(self.gd, "G-1.onkontrol.json")
        with open(yol, "rb") as f:
            once = f.read()
        self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        with open(yol, "rb") as f:
            self.assertEqual(f.read(), once)

    # kart kilidi
    def test_kart_kilit_altinda_yazilir(self):
        self.kart(); self.taban()
        cagri = []
        orijinal = OK.L.kilit

        def izle(yol, *a, **k):
            cagri.append(str(yol))
            return orijinal(yol, *a, **k)

        OK.L.kilit = izle
        try:
            self.kos("kontrol", "G-1", "--ciktilar", self.dosya)
        finally:
            OK.L.kilit = orijinal
        self.assertTrue(any(c.replace("\\", "/").endswith("gorevler/G-1.json") for c in cagri))
        self.assertEqual(len(self.kayitlar()), 1)


if __name__ == "__main__":
    unittest.main()
