"""`orkestra durum devral`: worktree durum kopyasındaki kayıtları ana klasöre ekler (ADR-0032, I-156 P3).

Her test tempfile altında kendi git deposunu kurar; gerçek depoya dokunmaz.
`py -3.13 -m pytest plugins/orkestra/tests/test_durum_devral.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402
import durum_devral as DD  # noqa: E402


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)


def oku(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read()


def isler(sayac, **kayitlar):
    return json.dumps({"sayac": sayac, "isler": kayitlar}, ensure_ascii=False)


class DurumDevral(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_dd_"))
        self.ana = os.path.join(self.taban, "depo")
        os.makedirs(os.path.join(self.ana, ".claude", "orkestra"))
        git(self.ana, "init", "-q", "-b", "main")
        git(self.ana, "config", "user.name", "Test")
        git(self.ana, "config", "user.email", "test@example.invalid")
        yaz(os.path.join(self.ana, ".gitignore"), ".claude/orkestra/\n.claude/worktrees/\n")
        yaz(os.path.join(self.ana, "a.txt"), "bir\n")
        git(self.ana, "add", ".")
        git(self.ana, "commit", "-q", "-m", "ilk")
        self.wt = os.path.join(self.ana, ".claude", "worktrees", "oturum-ab12cd")
        git(self.ana, "worktree", "add", "-q", "-b", "claude/oturum-ab12cd", self.wt)
        self.hedef = os.path.join(self.ana, ".claude", "orkestra")
        self.kaynak = os.path.join(self.wt, ".claude", "orkestra")
        os.makedirs(self.kaynak)
        for k in ("CLAUDE_PROJECT_DIR", L.DURUM_YEREL_ORTAM):
            os.environ.pop(k, None)

    def tearDown(self):
        subprocess.run(["git", "-C", self.ana, "worktree", "remove", "--force", self.wt], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)

    def kos(self, args, cwd):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="dd-oturum", PYTHONUTF8="1")
        env.pop("CLAUDE_PROJECT_DIR", None)
        env.pop(L.DURUM_YEREL_ORTAM, None)
        return subprocess.run([sys.executable, CLI] + args, cwd=cwd, env=env, capture_output=True, text=True,
                              encoding="utf-8")

    def _veri(self):
        yaz(os.path.join(self.hedef, "isler.json"), isler(2, **{"I-001": {"klasor": "A/001-x"}, "I-002": {"klasor": "A/002-y"}}))
        yaz(os.path.join(self.kaynak, "isler.json"),
            isler(4, **{"I-001": {"klasor": "A/001-x"}, "I-003": {"klasor": "A/003-z"}, "I-004": {"klasor": "A/004-w"},
                        "I-009": {"klasor": "A/002-y"}}))
        yaz(os.path.join(self.hedef, "gunluk.jsonl"), '{"a":1}\n{"a":2}\n')
        yaz(os.path.join(self.kaynak, "gunluk.jsonl"), '{"a":1}\n{"a":3}\n{"a":4}\n')
        yaz(os.path.join(self.kaynak, "onaylar", "O-1.json"), "{}")
        yaz(os.path.join(self.hedef, "onaylar", "O-2.json"), "{}")

    def test_kuru_kosu_hedefte_olmayani_sayar_yazmaz(self):  # K: dry-run N bildirir
        self._veri()
        plan = DD.planla(self.kaynak, self.hedef)
        self.assertEqual(plan["jsonl"]["gunluk.jsonl"], ['{"a":3}', '{"a":4}'])
        self.assertEqual([i for i, _ in plan["isler"]], ["I-003", "I-004"])  # I-009 klasörü I-002 ile aynı: atlanır
        self.assertEqual(plan["dosyalar"], [("onaylar", "O-1.json")])
        self.assertEqual(plan["sayac"], 4)
        self.assertEqual(plan["cakisma"], [])
        self.assertEqual(oku(os.path.join(self.hedef, "gunluk.jsonl")), '{"a":1}\n{"a":2}\n')

    def test_uygula_sonra_sifir_kalir_yedek_ve_damga(self):  # K: --uygula sonra 0, yedek, damga
        self._veri()
        sonuc = DD.uygula(self.kaynak, self.hedef, DD.planla(self.kaynak, self.hedef))
        self.assertGreater(sonuc["eklenen"], 0)
        self.assertEqual(DD.say(DD.planla(self.kaynak, self.hedef)), 0)
        self.assertTrue(os.path.isfile(os.path.join(sonuc["yedek"], "isler.json")))
        self.assertTrue(os.path.isfile(os.path.join(sonuc["yedek"], "boyutlar.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.kaynak, DD.DAMGA)))
        self.assertTrue(os.path.isfile(os.path.join(self.kaynak, "gunluk.jsonl")))  # kaynak silinmez
        veri = json.loads(oku(os.path.join(self.hedef, "isler.json")))
        self.assertEqual(sorted(veri["isler"]), ["I-001", "I-002", "I-003", "I-004"])
        self.assertEqual(veri["sayac"], 4)
        self.assertEqual(oku(os.path.join(self.hedef, "gunluk.jsonl")), '{"a":1}\n{"a":2}\n{"a":3}\n{"a":4}\n')

    def test_ikinci_uygulama_tekrar_eklemez(self):
        self._veri()
        DD.uygula(self.kaynak, self.hedef, DD.planla(self.kaynak, self.hedef))
        once = oku(os.path.join(self.hedef, "gunluk.jsonl"))
        DD.uygula(self.kaynak, self.hedef, DD.planla(self.kaynak, self.hedef))
        self.assertEqual(oku(os.path.join(self.hedef, "gunluk.jsonl")), once)

    def test_kimlik_cakismasi_raporlanir_yazilmaz(self):  # K: çakışma
        yaz(os.path.join(self.hedef, "isler.json"), isler(1, **{"I-001": {"klasor": "A/001-x"}}))
        yaz(os.path.join(self.kaynak, "isler.json"), isler(1, **{"I-001": {"klasor": "B/001-baska"}}))
        plan = DD.planla(self.kaynak, self.hedef)
        self.assertEqual(len(plan["cakisma"]), 1)
        self.assertEqual(plan["isler"], [])
        DD.uygula(self.kaynak, self.hedef, plan)
        veri = json.loads(oku(os.path.join(self.hedef, "isler.json")))
        self.assertEqual(veri["isler"]["I-001"]["klasor"], "A/001-x")

    def test_onay_dosyasi_farkli_icerik_cakisma(self):
        yaz(os.path.join(self.hedef, "onaylar", "O-1.json"), '{"d":"a"}')
        yaz(os.path.join(self.kaynak, "onaylar", "O-1.json"), '{"d":"b"}')
        plan = DD.planla(self.kaynak, self.hedef)
        self.assertEqual(len(plan["cakisma"]), 1)

    def test_gorulen_isaretleri_birlesir_cakisma_sayilmaz(self):
        yaz(os.path.join(self.hedef, "onaylar", "gorulen.json"), '{"a": "t1"}')
        yaz(os.path.join(self.kaynak, "onaylar", "gorulen.json"), '{"a": "t0", "b": "t2"}')
        plan = DD.planla(self.kaynak, self.hedef)
        self.assertEqual(plan["cakisma"], [])
        self.assertEqual(plan["gorulen"], {"b": "t2"})
        DD.uygula(self.kaynak, self.hedef, plan)
        self.assertEqual(json.loads(oku(os.path.join(self.hedef, "onaylar", "gorulen.json"))), {"a": "t1", "b": "t2"})
        self.assertEqual(DD.say(DD.planla(self.kaynak, self.hedef)), 0)

    def test_kaynaklar_ana_agacta_bos_worktree_te_dolu(self):
        self.assertEqual(DD.kaynaklar(self.hedef, cwd=self.ana), [])
        self.assertEqual([os.path.normcase(x) for x in DD.kaynaklar(self.hedef, cwd=self.wt)],
                         [os.path.normcase(os.path.join(self.wt, ".claude", "orkestra"))])
        tum = DD.kaynaklar(self.hedef, cwd=self.ana, tum=True)
        self.assertEqual(len(tum), 1)

    def test_cli_kuru_kosu_ve_uygula(self):
        self._veri()
        r = self.kos(["durum", "devral"], self.wt)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hedefte olmayan", r.stdout)
        self.assertIn("kuru koşu", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.kaynak, DD.DAMGA)))
        r = self.kos(["durum", "devral", "--uygula"], self.wt)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("uygulandı", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.kaynak, DD.DAMGA)))
        r = self.kos(["durum", "devral", "--json"], self.wt)
        self.assertEqual(json.loads(r.stdout)[0]["eklenecek"], 0)

    def test_cli_ana_agacta_bilgi_verir(self):
        r = self.kos(["durum", "devral"], self.ana)
        self.assertEqual(r.returncode, 1)
        self.assertIn("devralınacak", r.stderr)


if __name__ == "__main__":
    unittest.main()
