"""G-173: `orkestra is anlati` alt komutu (kimlik, all, --gun, --json, --audit, --denetle, --yaz).

Sahte proje geçici dizinde kurulur; CLI ic_kos ile süreç içinde koşar.
"""
import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, AD)
sys.path.insert(0, SCRIPTS)

import ic_kos  # noqa: E402

TEMIZ = (
    "**Ne yaptım?** Müşteri raporlarında satış toplamları ekrandan ekrana farklı çıkıyordu ve ekip hangi rakama, hangi ekrana ve hangi güne güvenmesi gerektiğini "
    "net biçimde bilmiyordu. Bunun için tek bir hesap kaynağı belirledim, eski hesapları ona bağladım ve bütün "
    "ekranları aynı veriden okur hale getirdim. Böylece raporlar artık birbiriyle tutarlı çıkıyor.\n\n"
    "**Nasıl yaptım?** Önce her ekranın toplamı nereden aldığını tek tek izledim, farkın iki ayrı süzme "
    "kuralından geldiğini gördüm. Süzme kuralını ortak bir işleve taşıdım, eski kopyaları sildim ve karşılaştırma "
    "testleriyle üç örnek müşteride sonucu sınadım. Test sonuçları birbirini tuttuğu için işi tamamlamış sayıyorum."
)
ABARTILI = TEMIZ.replace("tutarlı çıkıyor", "çözdüm ve tutarlı çıkıyor")
IHLALLI = "Tek paragraf, etiketsiz ve kısa."


def jyaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)


def kur(kok, adet=2, eski=None):
    """kok/.claude/orkestra altında `adet` işlik sahte durum. eski: {iş no: gün önce} (güncelleme tarihi)."""
    sd = os.path.join(kok, ".claude", "orkestra")
    os.makedirs(sd, exist_ok=True)
    kayitlar = {}
    simdi = datetime.datetime.now().astimezone()
    for n in range(1, adet + 1):
        i = f"I-{n:03d}"
        klasor = os.path.join(kok, "isler", f"{n:03d}-is-{n}")
        os.makedirs(klasor, exist_ok=True)
        with open(os.path.join(klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("# T\n- [x] P1: bir madde — kanıt: pytest 0 failed\n")
        t = (simdi - datetime.timedelta(days=(eski or {}).get(n, 0), minutes=n)).isoformat()
        kayit = {"id": i, "baslik": f"Is {n}", "durum": "acik", "klasor": klasor, "olusturma": t,
                 "guncelleme": t, "kartlar": [], "oturumlar": []}
        jyaz(os.path.join(klasor, "is.json"), kayit)
        kayitlar[i] = {k: kayit[k] for k in ("klasor", "baslik", "durum", "olusturma")}
        kayitlar[i]["guncelleme"] = t
    jyaz(os.path.join(sd, "isler.json"), {"sayac": adet, "isler": kayitlar})
    return sd


def cli(kok, *args):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=kok, PYTHONUTF8="1")
    return ic_kos.kos([ORKESTRA, "is", "anlati", *args], cwd=kok, env=env)


class Temel(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.kok = self._t.name

    def tearDown(self):
        self._t.cleanup()

    def taslak(self, metin):
        yol = os.path.join(self.kok, "taslak.md")
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)
        return yol


class Yardim(Temel):  # kriter 1
    def test_help_cikis_0_ve_secenekler(self):
        p = cli(self.kok, "--help")
        self.assertEqual(p.returncode, 0, p.stderr)
        for s in ("kimlik", "all", "--gun", "--json", "--audit", "--denetle", "--yaz"):
            self.assertIn(s, p.stdout)


class Kimlik(Temel):  # kriter 2
    def test_tek_eslesme_paket_metni(self):
        kur(self.kok, 2)
        p = cli(self.kok, "I-001")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("# I-001", p.stdout)
        self.assertIn("GÜÇLÜ FİİL İZNİ", p.stdout)
        self.assertNotIn("I-002", p.stdout)

    def test_birden_cok_eslesme_listeler_cikis_2(self):
        kur(self.kok, 2)
        for n in (1, 2):  # iki işin başlığına aynı Jira anahtarı
            yol = os.path.join(self.kok, ".claude", "orkestra", "isler.json")
            with open(yol, encoding="utf-8") as f:
                v = json.load(f)
            v["isler"][f"I-{n:03d}"]["baslik"] = f"PE-77 is {n}"
            jyaz(yol, v)
            ij = os.path.join(v["isler"][f"I-{n:03d}"]["klasor"], "is.json")
            with open(ij, encoding="utf-8") as f:
                k = json.load(f)
            k["baslik"] = f"PE-77 is {n}"
            jyaz(ij, k)
        p = cli(self.kok, "PE-77")
        self.assertEqual(p.returncode, 2, p.stdout + "|" + p.stderr)
        self.assertIn("I-001", p.stdout)
        self.assertIn("I-002", p.stdout)

    def test_olmayan_is_hata(self):
        kur(self.kok, 2)
        p = cli(self.kok, "I-999")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("iş yok: I-999", p.stderr)


class Toplu(Temel):  # kriter 3
    def test_all_gun_7_en_cok_8_satir(self):
        kur(self.kok, 10, eski={9: 30, 10: 30})
        p = cli(self.kok, "all", "--gun", "7")
        self.assertEqual(p.returncode, 0, p.stderr)
        satirlar = [s for s in p.stdout.splitlines() if s.strip()]
        self.assertEqual(len(satirlar), 8)
        self.assertNotIn("I-009", p.stdout)
        self.assertNotIn("I-010", p.stdout)


class Denetle(Temel):  # kriter 4
    def test_ihlalde_cikis_1_ve_kod_satirlari(self):
        kur(self.kok, 1)
        p = cli(self.kok, "--denetle", self.taslak(IHLALLI))
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertRegex(p.stdout, r"(?m)^A\d\d: ")

    def test_temizde_cikis_0(self):
        kur(self.kok, 1)
        p = cli(self.kok, "--denetle", self.taslak(TEMIZ))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("temiz", p.stdout)

    def test_guclu_fiil_izni_isin_paketinden(self):
        kur(self.kok, 1)
        yol = self.taslak(ABARTILI)
        p = cli(self.kok, "--denetle", yol)  # kimliksiz: izin yok
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("A07", p.stdout)
        p = cli(self.kok, "I-001", "--denetle", yol)  # izinsiz iş
        self.assertEqual(p.returncode, 1, p.stdout)
        import is_anlati
        with mock.patch.object(is_anlati, "guclu_fiil_izni", lambda paket: True):
            p = cli(self.kok, "I-001", "--denetle", yol)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("temiz", p.stdout)


class Yaz(Temel):  # kriter 5
    def test_ihlalde_dosya_yazilmaz(self):
        kur(self.kok, 1)
        p = cli(self.kok, "I-001", "--yaz", self.taslak(IHLALLI))
        self.assertEqual(p.returncode, 1, p.stderr)
        klasor = os.path.join(self.kok, "isler", "001-is-1")
        self.assertEqual([f for f in os.listdir(klasor) if f.startswith("anlati_")], [])

    def test_temizde_yazar_ve_baglanti_basar(self):
        kur(self.kok, 1)
        p = cli(self.kok, "I-001", "--yaz", self.taslak(TEMIZ))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        ad = f"anlati_{datetime.date.today():%Y%m%d}.md"
        yol = os.path.join(self.kok, "isler", "001-is-1", ad)
        self.assertTrue(os.path.isfile(yol))
        with open(yol, encoding="utf-8") as f:
            self.assertIn("**Ne yaptım?**", f.read())
        self.assertIn(f"anlati: [{ad}](", p.stdout)
        self.assertIn(f"isler/001-is-1/{ad})", p.stdout.replace("\\", "/"))

    def test_kimliksiz_yaz_hata(self):
        kur(self.kok, 1)
        p = cli(self.kok, "--yaz", self.taslak(TEMIZ))
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
