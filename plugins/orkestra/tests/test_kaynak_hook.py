"""I-309 P6: çıplak test koşusu yönlendirmesi (hook.py PreToolUse) ve panel kaynak uç noktası (/api/kaynaklar).

K1: çıplak `pytest` Bash komutu gunluk.jsonl'a `kapi_golge` (kapi=test_yonlendirme) yazar ve ipucu bağlamı verir;
    `test_paralel.py` komutu ve hedefli çağrı (tek dosya, -k, unittest modülü) yazmaz; ihlal modunda reddedilir.
K2: /api/kaynaklar sahip ve bekleyen kaydını (pid, komut, işçi, süre) döndürür; kaynaklar.js node ile sözdizimi geçer ve
    aynı veriyi çizer.
Hepsi geçici dizinde koşar; gerçek kira dizinine ve proje durum klasörüne yazılmaz.
"""
import contextlib
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(KOK, "scripts")
sys.path.insert(0, SCRIPTS)
import hook  # noqa: E402
import kaynak_kira as KK  # noqa: E402
import ork_lib as L  # noqa: E402
import panel  # noqa: E402

JS = os.path.join(KOK, "assets", "kaynaklar.js")
OTURUM = "kaynakhook1234-oturum"

CIPLAK = ["pytest",
          "pytest -q",
          "python -m pytest tests/",
          "PYTHONUTF8=1 C:/Users/PC/.venvs/x/Scripts/python.exe -m pytest -q plugins/orkestra/tests",
          "cd /c/x && py -3.13 -m pytest -x",
          "python -m unittest",
          "python -m unittest discover -s tests"]
HARIC = ["python scripts/test_paralel.py",
         "PYTHONUTF8=1 python plugins/orkestra/scripts/test_paralel.py -q",
         "pytest tests/test_kaynak_hook.py",
         "python -m pytest -q plugins/orkestra/tests/test_onbellek.py",
         "pytest -k kira",
         "pytest tests/test_x.py::Sinif::test_y",
         "python -m unittest tests.test_kaynak_kira",
         "python -m unittest discover -s tests -p test_kira*.py",
         "pytest --collect-only",
         "pytest --version",
         "grep -rn pytest scripts",
         "echo unittest",
         "python -c \"import pytest; print(pytest.__version__)\"",
         ""]


class TestSiniflama(unittest.TestCase):
    def test_ciplak_yakalanir(self):
        for k in CIPLAK:
            self.assertIsNotNone(hook.ciplak_test_kosusu(k), k)

    def test_kapsam_disi(self):
        for k in HARIC:
            self.assertIsNone(hook.ciplak_test_kosusu(k), k)

    def test_degiskenli_yorumlayici_yakalanir(self):
        for k in ("$PY -m pytest", "\"$PYTHON\" -m pytest -q", "${PY} -m pytest tests/",
                  "PYTHONUTF8=1 $VENV_PY -m unittest discover", "'$PY' -m pytest"):
            self.assertIsNotNone(hook.ciplak_test_kosusu(k), k)
        for k in ("echo $X pytest", "grep pytest $F", "$X pytest", "echo $PY -m pytest", "$PY -m pytest -k kira"):
            self.assertIsNone(hook.ciplak_test_kosusu(k), k)

    def test_test_paralel_yalniz_kendi_parcasini_muaf_tutar(self):
        for k in ("python scripts/test_paralel.py && pytest",
                  "python scripts/test_paralel.py; python -m pytest -q",
                  "python scripts/test_paralel.py || pytest tests/",
                  "pytest | tee x.log; python scripts/test_paralel.py"):
            self.assertIsNotNone(hook.ciplak_test_kosusu(k), k)
        for k in ("python scripts/test_paralel.py && echo pytest",
                  "PYTHONUTF8=1 python plugins/orkestra/scripts/test_paralel.py -q | tail -5"):
            self.assertIsNone(hook.ciplak_test_kosusu(k), k)


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_khook_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for k in ("ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_TEST_YONLENDIRME", "ORKESTRA_KAYNAK_KIRA",
                  KK.SAHIP_ENV):
            os.environ.pop(k, None)
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp
        os.environ["ORKESTRA_SIRA_KAPISI"] = "0"
        os.environ["ORKESTRA_ONAY_KAPISI"] = "0"
        os.environ["ORKESTRA_KAYNAK_KIRA_DIZINI"] = os.path.join(self.tmp, "kira")
        self.ayar = os.path.join(self.tmp, "kira_ayar.json")
        self.kira_ayari({"mod": "golge"})
        os.environ["ORKESTRA_KAYNAK_KIRA_AYAR"] = self.ayar

    def kira_ayari(self, d):
        with open(self.ayar, "w", encoding="utf-8") as f:
            json.dump(d, f)

    def kayit_yaz(self, sahipler=(), bekleyenler=()):
        os.makedirs(KK.dizin(), exist_ok=True)
        with open(os.path.join(KK.dizin(), "test_kosusu.json"), "w", encoding="utf-8") as f:
            json.dump({"sahipler": list(sahipler), "bekleyenler": list(bekleyenler)}, f)

    def pre(self, komut):
        g = {"tool_name": "Bash", "cwd": self.tmp, "session_id": OTURUM, "tool_input": {"command": komut}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(g)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        return json.loads(ham.splitlines()[-1]) if ham else {}

    def golgeler(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.isfile(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [o for o in (json.loads(s) for s in f if s.strip())
                    if o.get("tur") == "kapi_golge" and o.get("kapi") == hook.TEST_YONLENDIRME_KAPI]


def _kayit(pid, komut, isci, gecen_s=5.0):
    t = time.time() - gecen_s
    import datetime
    return {"kimlik": f"{pid}-1", "pid": pid, "komut": komut, "isci": isci, "istenen": isci, "son": time.time(),
            "baslangic": datetime.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")}


class TestHookGolge(_Proje):
    def test_ciplak_pytest_kapi_golge_yazar_ve_ipucu_verir(self):
        self.kayit_yaz(sahipler=[_kayit(os.getpid(), "test_paralel.py -q", 4)])
        c = self.pre("pytest")
        g = self.golgeler()
        self.assertEqual(len(g), 1, g)
        self.assertIn("pytest", g[0]["neden"])
        ek = (c.get("hookSpecificOutput") or {}).get("additionalContext", "")
        self.assertIn("test_paralel.py", ek)
        self.assertIn("1 kiralı test koşusu", ek)
        self.assertIn(f"sahip: {os.getpid()}/test_paralel.py -q", ek)
        self.assertNotEqual((c.get("hookSpecificOutput") or {}).get("permissionDecision"), "deny")

    def test_test_paralel_kayit_uretmez(self):
        c = self.pre("PYTHONUTF8=1 python scripts/test_paralel.py -q")
        self.assertEqual(self.golgeler(), [])
        self.assertNotIn("test_yonlendirme", json.dumps(c, ensure_ascii=False))

    def test_hedefli_cagri_kayit_uretmez(self):
        for k in ("pytest tests/test_x.py", "pytest -k kira", "python -m unittest tests.test_kaynak_kira"):
            self.pre(k)
        self.assertEqual(self.golgeler(), [])

    def test_kira_kapali_ya_da_ortam_sifir_susar(self):
        self.kira_ayari({"mod": "kapali"})
        self.pre("pytest")
        self.assertEqual(self.golgeler(), [])
        self.kira_ayari({"mod": "golge"})
        os.environ["ORKESTRA_TEST_YONLENDIRME"] = "0"
        self.pre("pytest")
        self.assertEqual(self.golgeler(), [])

    def test_ihlal_modu_reddeder(self):
        with open(os.path.join(self.sd, hook.TEST_YONLENDIRME_KAPI + ".json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "ihlal"}, f)
        c = self.pre("python -m pytest -q")
        self.assertEqual(c["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("test_paralel.py", c["hookSpecificOutput"]["permissionDecisionReason"])


class TestPanelUcNoktasi(_Proje):
    def setUp(self):
        super().setUp()
        self.kayit_yaz(sahipler=[_kayit(os.getpid(), "test_paralel.py -q", 4, 12)],
                       bekleyenler=[_kayit(os.getpid(), "test_paralel.py tests", 2, 7)])

    def test_json_sahip_ve_bekleyen(self):
        v = panel._kaynaklar_json(None)
        self.assertTrue(v["acik"])
        self.assertEqual(len(v["sahipler"]), 1)
        self.assertEqual(v["sahipler"][0]["pid"], os.getpid())
        self.assertEqual(v["sahipler"][0]["isci"], 4)
        self.assertGreaterEqual(v["sahipler"][0]["sure_s"], 11)
        self.assertEqual(len(v["bekleyenler"]), 1)
        self.assertGreaterEqual(v["bekleyenler"][0]["bekleme_s"], 6)
        self.assertEqual(v["kullanilan"], 4)
        self.assertNotIn("kimlik", v["sahipler"][0])
        self.assertIsNone(v["kilit"])

    def test_kilit_zaman_asimi_alanla_gelir(self):
        with open(os.path.join(self.sd, "ozet.json.zaman_asimi.log"), "w", encoding="utf-8") as f:
            f.write("2026-10-31T10:00:00 kilit_zaman_asimi pid=1 surec=hook bekleme_ms=20011\n" * 3)
        alan = {"id": "alan-x", "ad": "x", "yol": self.tmp, "orkestra": True}
        with mock.patch.object(L, "calisma_alanlari", return_value=[alan]):
            v = panel._kaynaklar_json("alan-x")
        self.assertEqual(v["kilit"]["ozet_json_zaman_asimi"], 3)
        self.assertEqual(v["kilit"]["kaynaklar"]["ozet.json"]["son_gun"], "2026-10-31")

    def test_http_uc_noktasi_ve_sayfa(self):
        sunucu = panel.http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        self.addCleanup(sunucu.shutdown)
        port = sunucu.server_address[1]
        b = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        b.request("GET", "/api/kaynaklar?alan=*", headers={"Host": f"127.0.0.1:{port}"})
        r = b.getresponse()
        self.assertEqual(r.status, 200)
        v = json.loads(r.read().decode("utf-8"))
        self.assertEqual(v["sahipler"][0]["pid"], os.getpid())
        for yol in ("/kaynaklar", "/kaynaklar.js"):
            b.request("GET", yol, headers={"Host": f"127.0.0.1:{port}"})
            r = b.getresponse()
            r.read()
            self.assertEqual(r.status, 200, yol)


@unittest.skipUnless(shutil.which("node"), "node yok")
class TestKaynaklarJs(unittest.TestCase):
    def test_sozdizimi(self):
        r = subprocess.run(["node", "--check", JS], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_sahip_ve_bekleyeni_cizer(self):
        veri = {"acik": True, "mod": "golge", "butce": 8, "kullanilan": 4,
                "sahipler": [{"pid": 4242, "komut": "test_paralel.py -q", "isci": 4, "sure_s": 75, "canli": True}],
                "bekleyenler": [{"pid": 5151, "komut": "test_paralel.py tests", "isci": 2, "bekleme_s": 7, "canli": True}],
                "kilit": {"kaynaklar": {"ozet.json": {"kayit": 118, "son_gun": "2026-10-31", "ort_bekleme_ms": 20011}},
                          "ozet_json_zaman_asimi": 118}}
        betik = ("const m=require(process.argv[1]);const v=JSON.parse(process.argv[2]);"
                 "process.stdout.write(m.kaynaklarHtml(v));")
        r = subprocess.run(["node", "-e", betik, JS, json.dumps(veri)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        h = r.stdout
        for parca in ("4242", "5151", "1 dk 15 sn", "7 sn", "Kirayı tutanlar", "Bekleyenler", "ozet.json: 118", "4 / 8"):
            self.assertIn(parca, h, parca)


if __name__ == "__main__":
    unittest.main()
