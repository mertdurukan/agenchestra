"""G-125: büyük bağlamda iş değişimi uyarısı (engellemez, bir kez).
`python -m unittest plugins/orkestra/tests/test_is_degisimi_uyari.py`
"""
import contextlib
import datetime as D
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
import is_kaydi  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import soguk_onbellek as S  # noqa: E402

OTURUM = "isdeg1234567890-oturum"


def asistan(baglam):
    z = D.datetime.now(D.timezone.utc).isoformat().replace("+00:00", "Z")
    return {"type": "assistant", "isSidechain": False, "timestamp": z,
            "message": {"model": "claude-opus-5-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": baglam - 10,
                                                             "cache_creation_input_tokens": 0}}}


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_isdeg_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        self.baglam(200_000)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def baglam(self, n):
        with open(self.tr, "w", encoding="utf-8") as f:
            f.write(json.dumps(asistan(n)) + "\n")


class Saf(_Ortak):
    def test_buyuk_baglam_farkli_is_uyarir(self):
        m = S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", "I-2")
        self.assertIsNotNone(m)
        self.assertIn("orkestra is devam I-2", m)
        self.assertIn("200k", m)
        self.assertIn("170k", m)  # 200K - 30K tahmini tasarruf

    def test_uyarmayan_durumlar(self):
        self.assertIsNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", "I-1"))  # öneri aynı
        self.assertIsNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, None, "I-2"))  # bağlı iş yok
        self.assertIsNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", None))  # öneri yok
        self.baglam(100_000)
        self.assertIsNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", "I-2"))  # bağlam küçük
        self.baglam(200_000)
        with open(os.path.join(self.sd, "onbellek_kapisi.json"), "w", encoding="utf-8") as f:
            json.dump({"is_degisimi": False}, f)
        self.assertIsNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", "I-2"))  # ayar kapalı

    def test_ayni_oturum_hedef_icin_bir_kez(self):
        self.assertIsNotNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", "I-2"))
        self.assertIsNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", "I-2"))
        self.assertIsNotNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", "I-3"))  # başka hedef yine uyarır
        self.assertIsNotNone(S.is_degisimi_uyarisi(self.sd, "o2", self.tr, "I-1", "I-2"))  # başka oturum

    def test_hata_sessiz_gecer(self):
        with mock.patch.object(S, "son_cagri", side_effect=RuntimeError("x")):
            self.assertIsNone(S.is_degisimi_uyarisi(self.sd, "o1", self.tr, "I-1", "I-2"))


class HookCikti(_Ortak):
    def setUp(self):
        super().setUp()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        yol = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", yol), mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(yol)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()
        self.fatura = is_kaydi.is_ac(self.sd, "Fatura raporlama entegrasyonu", os.path.join(self.proje, "001-fatura"))
        self.kampanya = is_kaydi.is_ac(self.sd, "Kampanya takvimi düzenleme", os.path.join(self.proje, "002-kampanya"))
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": self.fatura["id"], "is_baglanma": L.simdi()}, f)

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        super().tearDown()

    def kos(self, metin="kampanya takvimi düzenleme yapalım"):
        buf = io.StringIO()
        kod = None
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr, "prompt": metin}
        with contextlib.redirect_stdout(buf):
            try:
                hook.user_prompt_submit(g)
            except SystemExit as e:
                kod = e.code
        return buf.getvalue(), (0 if kod is None else kod)

    def test_uyari_system_message_olarak_engellemez(self):
        cikti, kod = self.kos()
        self.assertEqual(kod, 0)
        d = json.loads(cikti)
        self.assertIn(f"orkestra is devam {self.kampanya['id']}", d["systemMessage"])
        self.assertNotIn("decision", d)
        # ikinci istek: bir kez uyarıldı, systemMessage yok
        cikti2, _ = self.kos()
        self.assertNotIn("systemMessage", json.loads(cikti2) if cikti2.strip() else {})

    def test_baglam_kucukse_uyari_yok(self):
        self.baglam(100_000)
        cikti, kod = self.kos()
        self.assertEqual(kod, 0)
        self.assertNotIn("systemMessage", json.loads(cikti) if cikti.strip() else {})

    def test_islev_istisna_atarsa_hook_0_doner(self):
        with mock.patch.object(S, "is_degisimi_uyarisi", side_effect=RuntimeError("patladi")):
            cikti, kod = self.kos()
        self.assertEqual(kod, 0)
        self.assertNotIn("systemMessage", json.loads(cikti) if cikti.strip() else {})
        with mock.patch.object(hook, "_is_degisimi_uyarisi", side_effect=RuntimeError("patladi")):
            try:
                self.kos()
            except RuntimeError:
                self.fail("hook istisnayı yutmalı")


if __name__ == "__main__":
    unittest.main()
