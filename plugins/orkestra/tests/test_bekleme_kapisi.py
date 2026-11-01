"""I-326 (ADR-0138): sınırsız bekleme döngüsü kapısı (scripts/bekleme_kapisi.py), hook bağlantısı, mod ve kapatma.
`PYTHONUTF8=1 py -3.13 -m pytest -q plugins/orkestra/tests/test_bekleme_kapisi.py`
Kalıplar testte sabitlenmez; ayardan okunur. Hepsi geçici projede koşar.
"""
import ast
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import bekleme_kapisi as BK  # noqa: E402

MODUL = os.path.join(KOK, "scripts", "bekleme_kapisi.py")
OTURUM = "bekleme1234-oturum"

POZITIF = [
    "until grep -q '^exit=' /tmp/x.out; do sleep 5; done",  # I-325 komutu
    "while true; do sleep 5; done",
    "until [ -s /tmp/x.out ]; do sleep 2; done",
    "until [ $(wc -c < /tmp/x.out) -gt 0 ]; do sleep 1; done",
    "while [ ! -f /tmp/ok ]; do sleep 3; done; cat /tmp/ok",
    "cd /tmp && until test -e a.txt; do sleep 1; done",
    "while ! curl -s localhost:8000 >/dev/null; do sleep 1; done",
    "until [ -s /tmp/o.txt ] && ! pgrep -f test_paralel >/dev/null; do sleep 5; done",  # dosya hiç gelmezse süreç sınırı yetmez
    "i=0; until [ -f /tmp/x ]; do i=$((i+1)); sleep 1; done",  # artırım var, karşılaştırma yok: sınır değil
]
NEGATIF = [
    "timeout 120 bash -c 'until grep -q x f; do sleep 5; done'",
    "i=0; until [ -f /tmp/x ] || [ $i -ge 30 ]; do i=$((i+1)); sleep 5; done",
    "n=0; while [ $n -lt 10 ]; do n=$((n+1)); sleep 1; done",
    "while ((i<10)); do ((i++)); sleep 1; done",
    "while kill -0 $PID 2>/dev/null; do sleep 2; done",
    "until ! pgrep -f servis >/dev/null; do sleep 2; done",
    "while pgrep -f servis >/dev/null; do sleep 2; done",
    "start=$SECONDS; until [ -f x ] || [ $((SECONDS-start)) -gt 60 ]; do sleep 1; done",
    "for i in 1 2 3; do sleep 1; done",
    "for i in $(seq 1 30); do [ -f x ] && break; sleep 1; done",
    "while read l; do echo $l; done < dosya.txt",  # sleep yok
    "until grep -q x f; do echo bekle; done",  # sleep yok
    "echo 'until x; do sleep 5; done'",  # yalnız tırnak içi metin
    "python -c \"print('while true; do sleep 1; done')\"",
    "cat <<'EOF'\nwhile true; do sleep 1; done\nEOF",
    "sleep 5",
    "ls -la",
    "",
    None,
]


# Gerçek oturum komutlarından (01.11.2026 derlemi, 144 komut: 106 sınırsız, 38 geçen) yol/oturum kimliği silinerek alınmış örnekler.
GERCEK_POZITIF = [
    "until grep -q \"cikis=\" /tmp/taban_test.txt 2>/dev/null; do sleep 10; done; tail -15 /tmp/taban_test.txt",
    "until [ $(ls *.jsonl | wc -l) -ge 6 ]; do sleep 5; done; sleep 20; wc -l *.jsonl; date +%H:%M",
    "F=/tmp/s/test_out.txt; until grep -q '^exit=' $F; do sleep 5; done; tail -40 $F | cut -c1-220",
    "until [ -s /tmp/o.output ] && ! tasklist | grep -qi pytest; do sleep 5; done; tail -5 /tmp/o.output",
    "until grep -qiE \"passed|failed\" /tmp/tum.txt 2>/dev/null && ! pgrep -f test_paralel >/dev/null 2>&1; do sleep 5; done; tail -15 /tmp/tum.txt",
    "cd /c/x && until [ $(grep -c tamam v1.txt) -ge 6 ] || grep -q \"HATA\" v1.txt; do sleep 5; done; cat v1.txt",
]
GERCEK_NEGATIF = [
    "timeout 570 bash -c 'until grep -q \"tamam\" /tmp/s10.log; do sleep 15; done'; date +%H:%M:%S; tail -3 /tmp/s10.log",
    "until grep -qiE \"passed|toplam\" $D/test.out 2>/dev/null || [ $SECONDS -gt 420 ]; do sleep 5; done; tail -5 $D/test.out",
    "L=/tmp/b.txt; i=0; until [ $i -ge 360 ] || grep -q ok $L; do i=$((i+1)); sleep 1; done",
    "while tasklist 2>/dev/null | grep -q pytest; do sleep 5; done; tail -3 /tmp/p.txt",
    "py -3.13 -c \"\nimport time\nwhile time.time()-t<60:\n    time.sleep(1)\n\"",
    "cat > t.py <<'EOF'\nwhile True:\n    time.sleep(1)\nEOF\npython t.py",
]


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_bekleme_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_BEKLEME_KAPISI", None)
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp
        os.environ["ORKESTRA_SIRA_KAPISI"] = "0"
        os.environ["ORKESTRA_ONAY_KAPISI"] = "0"

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def proje_ayari(self, d):
        with open(os.path.join(self.sd, "bekleme_kapisi.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.isfile(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def kayitlar(self, tur):
        return [g for g in self.gunluk() if g.get("tur") == tur and "bekleme_kapisi" in json.dumps(g)]

    def pre(self, komut, arac="Bash", girdi_ek=None):
        girdi = {"command": komut}
        girdi.update(girdi_ek or {})
        g = {"tool_name": arac, "cwd": self.tmp, "session_id": OTURUM, "tool_input": girdi}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(g)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        return json.loads(ham.splitlines()[-1]) if ham else {}


class TestDosyalarVeAyar(unittest.TestCase):
    def test_ayar(self):
        a = BK.ayar_oku()
        for k in ("mod", "dongu_kaliplari", "bekleme_kaliplari", "sinir_kaliplari", "sayac_artirim_kaliplari",
                  "sayac_karsilastirma_kaliplari", "ret_metni", "uyari_metni"):
            self.assertIn(k, a)
        self.assertEqual(a["mod"], "golge")  # P-028: ihlal geçişi ölçümden sonra ayrı ADR ile

    def test_ret_metni_dogru_yolu_soyler(self):
        a = BK.ayar_oku()
        for k in ("ret_metni", "uyari_metni"):
            self.assertIn("run_in_background", a[k])

    def test_modulde_kalip_sabiti_yok(self):
        with open(MODUL, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        belge = {id(n.value) for n in ast.walk(agac) if isinstance(n, ast.Expr)}
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str) and id(d) not in belge:
                for w in ("sleep", "timeout", "until", "pgrep", "kill"):
                    self.assertNotIn(w, d.value.lower(), f"modülde kalıp sabiti: {d.value[:60]!r}")


class TestKaliplar(_Proje):
    def test_pozitif(self):
        a = BK.ayar_oku()
        for k in POZITIF:
            with self.subTest(k=k):
                self.assertTrue(BK.sinirsiz_donguler(k, a), k)

    def test_negatif(self):
        a = BK.ayar_oku()
        for k in NEGATIF:
            with self.subTest(k=k):
                self.assertEqual(BK.sinirsiz_donguler(k, a), [], k)

    def test_gercek_komutlar(self):
        a = BK.ayar_oku()
        for k in GERCEK_POZITIF:
            with self.subTest(poz=k[:60]):
                self.assertTrue(BK.sinirsiz_donguler(k, a), k)
        for k in GERCEK_NEGATIF:
            with self.subTest(neg=k[:60]):
                self.assertEqual(BK.sinirsiz_donguler(k, a), [], k)

    def test_karar_golge_varsayilan(self):
        s = BK.karar(POZITIF[0], self.tmp)
        self.assertIsNotNone(s)
        self.assertEqual(s[0], "golge")
        self.assertIn("run_in_background", s[1])

    def test_karar_ihlal_modu(self):
        self.proje_ayari({"mod": "ihlal"})
        s = BK.karar(POZITIF[0], self.tmp)
        self.assertEqual(s[0], "ihlal")
        self.assertIn("run_in_background", s[1])

    def test_kapatma(self):
        os.environ["ORKESTRA_BEKLEME_KAPISI"] = "0"
        self.assertIsNone(BK.karar(POZITIF[0], self.tmp))

    def test_bozuk_proje_ayari_varsayilana_duser(self):
        with open(os.path.join(self.sd, "bekleme_kapisi.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertIsNotNone(BK.karar(POZITIF[0], self.tmp))

    def test_negatif_karar_none(self):
        for k in NEGATIF:
            with self.subTest(k=k):
                self.assertIsNone(BK.karar(k, self.tmp))


class TestHookBaglantisi(_Proje):
    def test_golge_engellemez_kayit_ve_uyari(self):
        cikti = self.pre(POZITIF[0])
        ho = cikti.get("hookSpecificOutput", {})
        self.assertNotEqual(ho.get("permissionDecision"), "deny")
        self.assertIn("run_in_background", ho.get("additionalContext", ""))
        self.assertEqual(len(self.kayitlar("kapi_golge")), 1)

    def test_ihlal_reddeder_ve_kaydeder(self):
        self.proje_ayari({"mod": "ihlal"})
        cikti = self.pre(POZITIF[0])
        ho = cikti.get("hookSpecificOutput", {})
        self.assertEqual(ho.get("permissionDecision"), "deny")
        self.assertIn("run_in_background", ho.get("permissionDecisionReason", ""))
        self.assertEqual(len(self.kayitlar("kapi_ret")), 1)

    def test_run_in_background_alani_siniri_degistirmez(self):
        # Alan hook girdisinde olsa da olmasa da sınırsız döngü yakalanır (ret metni bu yolu söyler).
        self.proje_ayari({"mod": "ihlal"})
        cikti = self.pre(POZITIF[0], girdi_ek={"run_in_background": True})
        self.assertEqual(cikti.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_sinirli_komut_kayit_uretmez(self):
        self.proje_ayari({"mod": "ihlal"})
        for k in NEGATIF[:3]:
            cikti = self.pre(k)
            self.assertNotEqual(cikti.get("hookSpecificOutput", {}).get("permissionDecision"), "deny", k)
        self.assertEqual(self.kayitlar("kapi_ret") + self.kayitlar("kapi_golge"), [])

    def test_kapatma_ortam_degiskeni(self):
        self.proje_ayari({"mod": "ihlal"})
        os.environ["ORKESTRA_BEKLEME_KAPISI"] = "0"
        cikti = self.pre(POZITIF[0])
        self.assertNotEqual(cikti.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_kapi_hatasi_komutu_bozmaz(self):
        self.proje_ayari({"mod": "ihlal"})
        with mock.patch.object(BK, "karar", side_effect=RuntimeError("x")):
            cikti = self.pre(POZITIF[0])
        self.assertNotEqual(cikti.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")


if __name__ == "__main__":
    unittest.main()
