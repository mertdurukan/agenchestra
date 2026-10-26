"""ADR-0085 P2: `orkestra kanit olc` / `ana-olcu` ve scripts/kanit_olcum.py. Sentetik dökümle; gerçek döküm okunmaz.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_kanit_olc.py`
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402
import kanit_olcum as K  # noqa: E402
import soru_sinif  # noqa: E402

SORU = "fallback ne demek?"
IS = "şunu düzelt"


def _simdi_z():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def tur(istem, yanit, cagrilar=(), zaman=None):
    """Bir kullanıcı turunun döküm satırları: kullanıcı mesajı + her araç çağrısı + son metin yanıtı."""
    z = zaman or _simdi_z()
    s = [{"type": "user", "timestamp": z, "message": {"content": istem}}]
    for ad, girdi in cagrilar:
        s.append({"type": "assistant", "timestamp": z, "message": {"content": [{"type": "tool_use", "name": ad, "input": girdi}]}})
    s.append({"type": "assistant", "timestamp": z, "message": {"content": [{"type": "text", "text": yanit}]}})
    return s


def yaz(yol, *turlar, ekstra=()):
    with open(yol, "w", encoding="utf-8") as f:
        for t in turlar:
            for satir in t:
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")
        for satir in ekstra:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")


class OlcumCekirdek(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_kanit_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.r = K.rubrik_oku(None)
        self.yol = os.path.join(self.tmp, "a.jsonl")

    def olc(self, *turlar, **kw):
        yaz(self.yol, *turlar, **kw)
        return K.olc([self.yol], soru_sinif.tur, self.r, "2000-01-01T00:00")

    def test_rubrik_ayardan_gelir(self):
        for k in ("etiketler", "pozitif_etiket", "iddia_kalibi", "okuma_araclari", "ilgisiz_kabuk_kalibi"):
            self.assertIn(k, self.r)
        self.assertEqual(set(self.r["etiketler"]), {"A", "B", "C", "D"})

    def test_cerceve_ici_ve_disi(self):
        say, ic, dis, _ = self.olc(
            tur(SORU, "Dosya yok."),                                       # kanıtsız + iddia → çerçeve içi
            tur(SORU, "Dosya yok.", [("Read", {"file_path": "x"})]),       # kanıtlı → çerçeve dışı
            tur(SORU, "Bu bir tanımdır, kural gibi düşünülür."),           # iddia sözcüğü yok → çerçeve dışı
        )
        self.assertEqual(say["notsuz:soru"], 3)
        self.assertEqual(say["notsuz:kanitsiz_iddiali"], 1)
        self.assertEqual((len(ic), len(dis)), (1, 2))
        self.assertEqual(ic[0]["katman"], "ic")
        self.assertTrue(all(d["katman"] == "dis" for d in dis))

    def test_ilgisiz_arac_kanit_sayilmaz(self):
        for cagri in (("Skill", {"skill": "x"}), ("TodoWrite", {}), ("mcp__ccd_turn__update_plan", {}),
                      ("Bash", {"command": "orkestra niyet yaz x"}), ("PowerShell", {"command": "orkestra is todo I-1 --bitti 1"})):
            with self.subTest(cagri=cagri[0]):
                _, ic, _, _ = self.olc(tur(SORU, "Dosya yok.", [cagri]))
                self.assertEqual(len(ic), 1)

    def test_gercek_arac_kanit_sayilir(self):
        for cagri in (("Grep", {}), ("Bash", {"command": "ls"}), ("mcp__x__get_thing", {}), ("WebSearch", {})):
            with self.subTest(cagri=cagri[0]):
                _, ic, dis, _ = self.olc(tur(SORU, "Dosya yok.", [cagri]))
                self.assertEqual((len(ic), len(dis)), (0, 1))

    def test_is_kapanisi_calistirmasiz(self):
        yaz_ = ("Edit", {"file_path": "a.py"})
        say, _, _, kap = self.olc(
            tur(IS, "Düzeltildi, bitti.", [yaz_]),                                           # çalıştırmasız
            tur(IS, "Düzeltildi, bitti.", [yaz_, ("Bash", {"command": "pytest"})]),          # yazımdan sonra çalıştırma
            tur(IS, "Düzeltildi, bitti.", []),                                               # yazım yok → sayılmaz
        )
        self.assertEqual(say["notsuz:is_kapanis_yazimli"], 2)
        self.assertEqual(say["notsuz:is_kapanis_calistirmasiz"], 1)
        self.assertEqual(len(kap), 1)

    def test_pencere_ve_yan_zincir(self):
        eski = tur(SORU, "Dosya yok.", zaman="1999-01-01T00:00:00Z")
        yan = [dict(s, isSidechain=True) for s in tur(SORU, "Dosya yok.")]
        say, ic, _, _ = self.olc(eski, yan, tur(SORU, "Dosya yok."))
        self.assertEqual((say["notsuz:soru"], len(ic)), (1, 1))

    def test_donem_ayrimi(self):
        yaz(self.yol, tur(SORU, "Dosya yok.", zaman="2026-10-19T10:00:00Z"), tur(SORU, "Dosya yok.", zaman="2026-10-21T10:00:00Z"))
        say, _, _, _ = K.olc([self.yol], soru_sinif.tur, self.r, "2000-01-01T00:00", "2026-10-20T13:06")
        self.assertEqual((say["notsuz:soru"], say["notlu:soru"]), (1, 1))

    def test_sistem_iletisi_ve_arac_sonucu_tur_acmaz(self):
        sonuc = {"type": "user", "timestamp": _simdi_z(), "message": {"content": [{"type": "tool_result", "content": "x"}]}}
        sistem = {"type": "user", "timestamp": _simdi_z(), "message": {"content": "<task-notification>x</task-notification>"}}
        say, _, _, _ = self.olc(tur(SORU, "Dosya yok."), ekstra=(sonuc, sistem))
        self.assertEqual(say["notsuz:soru"], 1)

    def test_ornek_tohumla_yeniden_uretilir(self):
        havuz = [{"oturum": "o", "zaman": f"t{i:03d}", "istem": str(i)} for i in range(50)]
        a = K.ornekle(havuz, 10, 42)
        self.assertEqual(a, K.ornekle(list(reversed(havuz)), 10, 42))
        self.assertNotEqual(a, K.ornekle(havuz, 10, 7))
        self.assertEqual(len(K.ornekle(havuz[:3], 10, 42)), 3)


class Istatistik(unittest.TestCase):
    def test_jeffreys_katmanli_taban_degerleri(self):
        # P-030 güç hesabı: w=219/557, (4/120, 0/60) → nokta %1,31, üst %4,30; (4/120, 1/100) → %1,92, %4,68
        n, u = K.jeffreys_ust(4, 120, 219 / 557, 0, 60)
        self.assertAlmostEqual(n * 100, 1.31, delta=0.01)
        self.assertAlmostEqual(u * 100, 4.30, delta=0.25)
        n, u = K.jeffreys_ust(4, 120, 219 / 557, 1, 100)
        self.assertAlmostEqual(n * 100, 1.92, delta=0.01)
        self.assertAlmostEqual(u * 100, 4.68, delta=0.25)

    def test_sifir_sayili_katmanda_ust_sinir_sifir_degil(self):
        _, u = K.jeffreys_ust(0, 60)
        self.assertGreater(u, 0.01)

    def test_ana_olcu_formulu(self):
        # w = ic_toplam / soru; nokta = w·a/n + (1−w)·a2/n2
        n, _ = K.ana_olcu(6, 120, 2, 100, soru_n=500, ic_toplam=200)
        self.assertAlmostEqual(n, 0.4 * 6 / 120 + 0.6 * 2 / 100, places=9)
        with self.assertRaises(ValueError):
            K.ana_olcu(1, 10, 0, 0, 100, 40)

    def test_wilson(self):
        alt, ust = K.wilson(10, 60)
        self.assertAlmostEqual(alt, 0.093, delta=0.002)   # taban: Wilson %9,3 – %28,0
        self.assertAlmostEqual(ust, 0.280, delta=0.002)
        self.assertEqual(K.wilson(0, 0), (0.0, 1.0))


class Cli(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kanitcli_")
        self.addCleanup(shutil.rmtree, self.proje, ignore_errors=True)
        self.dok = os.path.join(self.proje, "dokum")
        os.makedirs(self.dok)
        self.assertEqual(self.cli("baslat").returncode, 0)

    def cli(self, *args):
        env = dict(os.environ, PYTHONUTF8="1", CLAUDE_PROJECT_DIR=self.proje, CLAUDE_CODE_SESSION_ID="kanit-oturum")
        return ic_kos.kos([CLI, *args, "--ajan-id", "ana", "--ajan-tipi", "ana"], cwd=self.proje, env=env)

    def test_olc_sayar_ve_ornegi_yazar(self):
        turlar = [tur(SORU, "Dosya yok.") for _ in range(6)] + [tur(SORU, "Dosya yok.", [("Read", {})]) for _ in range(4)]
        yaz(os.path.join(self.dok, "a.jsonl"), *turlar)
        cikti = os.path.join(self.proje, "ornek.jsonl")
        r = self.cli("kanit", "olc", "--gun", "1", "--desen", os.path.join(self.dok, "*.jsonl"),
                     "--ornek", "4", "--dis-ornek", "3", "--cikti", cikti)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("soru=10 cerceve_ic=6 cerceve_dis=4", r.stdout)
        satirlar = [json.loads(s) for s in open(cikti, encoding="utf-8")]
        self.assertEqual(satirlar[0]["_meta"]["soru"], 10)
        self.assertEqual([s["katman"] for s in satirlar[1:]].count("ic"), 4)
        self.assertEqual([s["katman"] for s in satirlar[1:]].count("dis"), 3)
        # aynı tohum → aynı örnek
        cikti2 = os.path.join(self.proje, "ornek2.jsonl")
        self.cli("kanit", "olc", "--gun", "1", "--desen", os.path.join(self.dok, "*.jsonl"),
                 "--ornek", "4", "--dis-ornek", "3", "--cikti", cikti2)
        self.assertEqual(open(cikti, encoding="utf-8").read().split("\n", 1)[1], open(cikti2, encoding="utf-8").read().split("\n", 1)[1])

    def test_ana_olcu_etiketli_dosyadan(self):
        dosya = os.path.join(self.proje, "etiketli.jsonl")
        satirlar = [{"_meta": {"soru": 500, "ic_toplam": 200, "dis_toplam": 300}}]
        satirlar += [{"katman": "ic", "etiket": "A" if i < 6 else "D"} for i in range(120)]
        satirlar += [{"katman": "dis", "etiket": "A" if i < 2 else "D"} for i in range(100)]
        with open(dosya, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")
        r = self.cli("kanit", "ana-olcu", dosya, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertAlmostEqual(d["ana_olcu_nokta"], 0.4 * 6 / 120 + 0.6 * 2 / 100, places=9)
        self.assertGreater(d["ana_olcu_ust95"], d["ana_olcu_nokta"])
        self.assertEqual((d["ic"], d["dis"]), ({"a": 6, "n": 120}, {"a": 2, "n": 100}))

    def test_ana_olcu_meta_yoksa_hata(self):
        dosya = os.path.join(self.proje, "e.jsonl")
        open(dosya, "w", encoding="utf-8").write(json.dumps({"katman": "ic", "etiket": "A"}) + "\n")
        self.assertNotEqual(self.cli("kanit", "ana-olcu", dosya).returncode, 0)


if __name__ == "__main__":
    unittest.main()
