"""G-050: `orkestra maliyet tur` (kaynak=tur) satırında iş kimliği (T-05 boşluğu).

`py -3.13 -m pytest plugins/orkestra/tests/test_maliyet_tur_is.py -q -p no:cacheprovider`

- K1 ana ajan turu: satırın 'is'i oturumun bağlı işi.
- K2 alt ajan turu: gorev kartı varsa kartın 'is'i (oturumun işinden önceliklidir).
- K3 bağlı iş / kart is alanı yok, kart ya da oturum dosyası bozuk: satır yazılır, is None, çıkış 0.
- K4 diğer alanlar değişmez.
Hepsi geçici projede, gerçek CLI süreciyle koşar.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORK = os.path.join(KOK, "scripts", "orkestra.py")
OTURUM = "tur-is-oturum"
AID = "ajan-tur-is-1"


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_turis_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        os.makedirs(os.path.join(self.sd, "gorevler"))

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def _yaz(self, *parca, icerik):
        yol = os.path.join(self.sd, *parca)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(icerik if isinstance(icerik, str) else json.dumps(icerik))

    def oturum_bagla(self, is_id):
        self._yaz("oturumlar", f"{OTURUM}.json", icerik={"is": is_id})

    def kart(self, gid, **alan):
        self._yaz("gorevler", f"{gid}.json", icerik=dict({"id": gid}, **alan))

    def ajan_onbellek(self, gorev, surec="is", ajan="orkestra:isci"):
        self._yaz("oturumlar", f"ajan_{AID}.json", icerik={"gorev": gorev, "surec": surec, "ajan": ajan})

    def tur(self, agent_id=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.proje)
        for k in ("ORKESTRA_PERSPEKTIF", "ORKESTRA_RUYA"):
            env.pop(k, None)
        kom = [sys.executable, ORK, "maliyet", "tur", "--oturum", OTURUM, "--model", "claude-sonnet-5-5",
               "--giris", "100", "--cikis", "50", "--onb-okuma", "30", "--onb-yazma", "20", "--sure-ms", "1234"]
        if agent_id:
            kom += ["--agent-id", agent_id]
        p = ic_kos.kos(kom[1:], env=env, cwd=self.proje)
        self.assertEqual(p.returncode, 0, p.stderr)
        yol = os.path.join(self.sd, "maliyet.jsonl")
        self.assertTrue(os.path.exists(yol), "maliyet satırı yazılmadı")
        with open(yol, encoding="utf-8") as f:
            satirlar = [json.loads(s) for s in f if s.strip()]
        self.assertEqual(len(satirlar), 1)
        return satirlar[0]


class TestAnaAjanTuru(_Ortak):
    def test_k1_oturum_isi_satira_yazilir(self):
        self.oturum_bagla("I-007")
        r = self.tur()
        self.assertEqual(r["is"], "I-007")
        self.assertEqual(r["kaynak"], "tur")
        self.assertIsNone(r["agent_id"])

    def test_k3_bagli_is_yok_null(self):
        r = self.tur()
        self.assertIn("is", r)
        self.assertIsNone(r["is"])

    def test_k3_oturum_dosyasi_bozuk_null(self):
        self._yaz("oturumlar", f"{OTURUM}.json", icerik="{bozuk json")
        r = self.tur()
        self.assertIn("is", r)
        self.assertIsNone(r["is"])

    def test_k3_oturum_is_alani_bos_null(self):
        self.oturum_bagla(None)
        r = self.tur()
        self.assertIn("is", r)
        self.assertIsNone(r["is"])


class TestAltAjanTuru(_Ortak):
    def test_k2_kart_isi_oturum_isinden_oncelikli(self):
        self.oturum_bagla("I-001")
        self.kart("G-200", **{"is": "I-009"})
        self.ajan_onbellek("G-200")
        r = self.tur(AID)
        self.assertEqual(r["is"], "I-009")
        self.assertEqual(r["gorev"], "G-200")

    def test_k2_kart_isi_oturum_baglisi_yokken(self):
        self.kart("G-201", **{"is": "I-004"})
        self.ajan_onbellek("G-201")
        self.assertEqual(self.tur(AID)["is"], "I-004")

    def test_k3_kartta_is_yok_null(self):
        self.kart("G-202")
        self.ajan_onbellek("G-202")
        r = self.tur(AID)
        self.assertIn("is", r)
        self.assertIsNone(r["is"])

    def test_k3_kart_dosyasi_bozuk_null(self):
        self._yaz("gorevler", "G-203.json", icerik="{bozuk")
        self.ajan_onbellek("G-203")
        r = self.tur(AID)
        self.assertIn("is", r)
        self.assertIsNone(r["is"])

    def test_k3_kart_dosyasi_yok_null(self):
        self.ajan_onbellek("G-204")
        r = self.tur(AID)
        self.assertIn("is", r)
        self.assertIsNone(r["is"])

    def test_alt_ajan_gorev_tire_oturum_isine_duser(self):
        self.oturum_bagla("I-003")
        self.ajan_onbellek("-", surec="bilinmiyor", ajan="?")
        self.assertEqual(self.tur(AID)["is"], "I-003")


class TestDigerAlanlarDegismez(_Ortak):
    def test_k4_alanlar_ve_degerler(self):
        self.oturum_bagla("I-002")
        r = self.tur()
        beklenen = {"oturum", "gorev", "surec", "ajan", "agent_id", "model", "giris", "cikis",
                    "onbellek_okuma", "onbellek_yazma", "maliyet_usd", "sure_ms", "kaynak", "tarife", "zaman", "is", "v"}
        self.assertEqual(set(r), beklenen)
        self.assertEqual((r["oturum"], r["gorev"], r["surec"], r["ajan"]), (OTURUM, "-", "orkestrasyon", "ana-ajan"))
        self.assertEqual((r["giris"], r["cikis"], r["onbellek_okuma"], r["onbellek_yazma"], r["sure_ms"]),
                         (100, 50, 30, 20, 1234))
        self.assertEqual(r["model"], "claude-sonnet-5-5")
        self.assertGreater(r["maliyet_usd"], 0)

    def test_k4_alt_ajan_alanlari(self):
        self.kart("G-205", **{"is": "I-005"})
        self.ajan_onbellek("G-205", surec="is", ajan="orkestra:isci")
        r = self.tur(AID)
        self.assertEqual((r["gorev"], r["surec"], r["ajan"], r["agent_id"]), ("G-205", "is", "orkestra:isci", AID))
        self.assertEqual(r["kaynak"], "tur")


if __name__ == "__main__":
    unittest.main()
