"""I-319 P6: çıktı bütçesi üç kollu deneyi (scripts/cikti_deney.py) ve hook bağlantısı.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_cikti_deney.py`
Hepsi geçici projede koşar; sınırlar ayardan okunur.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from collections import Counter

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import cikti_butce as CB  # noqa: E402
import cikti_deney as CD  # noqa: E402
import hook  # noqa: E402


def _satir(tur, **kw):
    return json.dumps({"type": tur, **kw}, ensure_ascii=False)


def _transkript(yol, metinler, kutu_sonrasi=None, istek="iş yap"):
    s = [_satir("user", message={"content": istek})]
    for m in metinler:
        s.append(_satir("assistant", message={"content": [{"type": "text", "text": m}]}))
    if kutu_sonrasi is not None:
        s.append(_satir("assistant", message={"content": [{"type": "tool_use", "name": "mcp__ccd_turn__wrap_up", "input": {}}]}))
        s.append(_satir("assistant", message={"content": [{"type": "text", "text": kutu_sonrasi}]}))
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(s) + "\n")


class _Env:
    def __init__(self, ad, deger):
        self.ad, self.deger = ad, deger

    def __enter__(self):
        self.eski = os.environ.get(self.ad)
        os.environ[self.ad] = self.deger

    def __exit__(self, *a):
        if self.eski is None:
            os.environ.pop(self.ad, None)
        else:
            os.environ[self.ad] = self.eski


class CiktiDeneyTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sd = os.path.join(self.d, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.d, "t.jsonl")
        self.ayar = CD.ayar_oku()
        self.oid = {}
        i = 0
        while len(self.oid) < 3:  # her kol için bir sentetik oturum kimliği
            oid = f"deney-oturum-{i}"
            self.oid.setdefault(CD.kol(oid, self.ayar), oid)
            i += 1

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def _stop(self, oid):
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            hook._cikti_butce_yanit(self.sd, oid, {"transcript_path": self.tr})
        return cikti.getvalue()

    def test_ayar_golge_ve_esit_oran(self):
        self.assertEqual(self.ayar["mod"], "golge")
        self.assertEqual(set(self.ayar["oranlar"].values()), {1})
        self.assertEqual(self.ayar["hedef_kol_tur"], 376)

    def test_ayni_oturum_ayni_kol(self):
        for i in range(200):
            oid = f"sabit-{i}"
            self.assertEqual(len({CD.kol(oid, self.ayar) for _ in range(5)}), 1)
        self.assertEqual(CD.kol("x", self.ayar), CD.kol("x", CD.ayar_oku()))

    def test_dagilim_kabaca_esit(self):
        c = Counter(CD.kol(f"sentetik-{i:04d}", self.ayar) for i in range(1000))
        self.assertEqual(set(c), set(CD.KOLLAR))
        for k in CD.KOLLAR:
            self.assertTrue(250 <= c[k] <= 420, (k, c[k]))

    def test_kontrol_kolunda_ek_baglam_yok(self):
        oid = self.oid["kontrol"]
        _transkript(self.tr, ["x" * 2000], kutu_sonrasi="y" * 1200)
        self.assertEqual(self._stop(oid), "")
        self.assertEqual(CD.bildirim(self.sd, oid, "nedir bu?", self.ayar), "")
        self.assertEqual(CD.bildirim(self.sd, oid, "şunu yap", self.ayar), "")
        self.assertFalse(os.listdir(os.path.join(self.sd, "oturumlar")))

    def test_geri_bildirim_onceki_asimi_bildirir(self):
        oid = self.oid["geri_bildirim"]
        _transkript(self.tr, ["x" * 1500])
        self.assertEqual(self._stop(oid), "")  # aşım engellenmez
        m = CD.bildirim(self.sd, oid, "devam", self.ayar)
        self.assertIn("1500/800", m)
        self.assertLessEqual(len(m), 200)
        self.assertEqual(CD.bildirim(self.sd, oid, "devam", self.ayar), "")  # tek sefer tüketilir

    def test_geri_bildirim_asim_yoksa_sessiz(self):
        oid = self.oid["geri_bildirim"]
        _transkript(self.tr, ["x" * 1500])
        self._stop(oid)
        _transkript(self.tr, ["kısa"])
        self._stop(oid)  # sonraki kısa tur eski aşımı siler
        self.assertEqual(CD.bildirim(self.sd, oid, "devam", self.ayar), "")

    def test_kalibre_tur_tipine_gore_sinir(self):
        oid = self.oid["kalibre"]
        m = CD.bildirim(self.sd, oid, "şu dosyayı düzelt", self.ayar)
        self.assertIn("≤800", m)
        self.assertIn("≤400", m)
        self.assertIn("≤300", m)
        self.assertLessEqual(len(m), 200)
        self.assertTrue(CD.kalibre_asim({"toplam": 600, "kapanis": 100}, "gorev", self.ayar))  # kutu öncesi 500 > 400
        self.assertFalse(CD.kalibre_asim({"toplam": 750, "kapanis": None}, "gorev", self.ayar))
        self.assertTrue(CD.kalibre_asim({"toplam": 750, "kapanis": None}, "soru", self.ayar))

    def test_kol_olcum_ve_golge_satirinda(self):
        for k, oid in self.oid.items():
            _transkript(self.tr, ["x" * 1500])
            self.assertEqual(self._stop(oid), "")  # gölge: ret yok, çıktı yok
        g = self._gunluk()
        olcum = [x for x in g if x["tur"] == "cikti_olcum"]
        golge = [x for x in g if x["tur"] == "kapi_golge"]
        self.assertEqual({x["kol"] for x in olcum}, set(CD.KOLLAR))
        self.assertEqual({x["kol"] for x in golge}, set(CD.KOLLAR))
        self.assertFalse(any(x["tur"] in ("kapi_ret", "kapi_ihlal") for x in g))
        self.assertTrue(all("kalibre_asim" in x and "tip" in x for x in olcum))

    def test_env_ile_kapanir(self):
        with _Env("ORKESTRA_CIKTI_DENEY", "0"):
            self.assertIsNone(CD.kol(self.oid["kalibre"], self.ayar))
            self.assertEqual(CD.bildirim(self.sd, self.oid["kalibre"], "şunu yap", self.ayar), "")
            _transkript(self.tr, ["x" * 1500])
            self._stop(self.oid["geri_bildirim"])
            g = self._gunluk()
            self.assertTrue(g)
            self.assertFalse(any("kol" in x for x in g))  # ölçüm sürer, deney alanı yok
            self.assertEqual(CD.bildirim(self.sd, self.oid["geri_bildirim"], "devam", self.ayar), "")

    def test_mod_kapali_kol_yok(self):
        self.assertIsNone(CD.kol(self.oid["kalibre"], {**self.ayar, "mod": "kapali"}))

    def test_hook_user_prompt_kontrol_ve_kalibre(self):
        """Gerçek UserPromptSubmit akışı: kontrol kolunda deney satırı bağlama girmez, kalibre kolunda girer."""
        for k in ("kontrol", "kalibre"):
            cikti = io.StringIO()
            inp = {"cwd": self.d, "session_id": self.oid[k], "prompt": "şu dosyayı düzelt",
                   "transcript_path": self.tr}
            with contextlib.redirect_stdout(cikti), contextlib.suppress(SystemExit):
                hook.user_prompt_submit(inp)
            metin = cikti.getvalue()
            if k == "kontrol":
                self.assertNotIn("bu tur bütçesi", metin)
            else:
                self.assertIn("bu tur bütçesi", metin)
        bild = [x for x in self._gunluk() if x["tur"] == "cikti_deney_bildirim"]
        self.assertEqual([x["kol"] for x in bild], ["kalibre"])


if __name__ == "__main__":
    unittest.main()
