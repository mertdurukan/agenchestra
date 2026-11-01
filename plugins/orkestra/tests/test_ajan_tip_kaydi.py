"""Alt ajan tipi kaydı (I-316): `python -m unittest tests.test_ajan_tip_kaydi -v` (plugins/orkestra altında)

subagent_start tipi görev etiketi olmasa da ajan_<id>.json'a yazar; maliyet tur satırı tipi oradan ya da
başka proje dizinindeki transkript meta'sından okur; okunamazsa kapi_golge düşer.
Hepsi geçici projede çalışır; gerçek ~/.claude ve durum dizinine yazılmaz.
"""
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
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402


class AjanTipKaydi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_tip_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        genel = os.path.join(self.proje, "genel")
        os.makedirs(genel)
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", os.path.join(genel, "niyet.jsonl")),
                   mock.patch.object(niyet, "GENEL_DIZIN", genel),
                   mock.patch.dict(os.environ, {}, clear=False)]
        for p in self._p:
            p.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def baslat(self, aid, tip):
        g = {"session_id": "t-oturum", "cwd": self.proje, "agent_id": aid, "agent_type": tip,
             "transcript_path": os.path.join(self.proje, "yok.jsonl")}
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            hook.subagent_start(g)

    def onbellek(self, aid):
        with open(os.path.join(self.sd, "oturumlar", f"ajan_{aid}.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_s1_gorevsiz_ajan_tipi_yazilir(self):
        self.baslat("g1", "orkestra:denetci")
        d = self.onbellek("g1")
        self.assertEqual(d["ajan"], "orkestra:denetci")
        self.assertEqual(d["surec"], "denetim")
        self.assertEqual(d["gorev"], "-")

    def test_s1_var_olan_onbellek_ezilmez(self):
        yol = os.path.join(self.sd, "oturumlar", "ajan_g2.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"gorev": "G-001", "surec": "is", "ajan": "orkestra:isci-t2"}, f)
        self.baslat("g2", "orkestra:isci-t2")
        self.assertEqual(self.onbellek("g2")["gorev"], "G-001")

    def test_s1_tip_yoksa_dosya_yazilmaz(self):
        self.baslat("g3", None)
        self.assertFalse(os.path.exists(os.path.join(self.sd, "oturumlar", "ajan_g3.json")))

    # ---- S2/S4: maliyet tur yedek arama ve gölge kapı
    def _tur(self, aid, ev):
        import argparse
        from komutlar import maliyet as M
        a = argparse.Namespace(oturum="t-oturum", agent_id=aid, model="m", giris=1, cikis=1, onb_okuma=0, onb_yazma=0, sure_ms=1)
        for ad, v in (("tur", 1), ("arac_cagrisi", 0), ("istek_id", None)):
            setattr(a, ad, v)
        with mock.patch.object(L, "durum_dizini", return_value=self.sd),                 mock.patch.object(L, "proje_dizini", return_value=self.proje),                 mock.patch.object(L, "proje_oturum_dizini", return_value=os.path.join(self.proje, "yok-dizin")),                 mock.patch.object(L, "alt_ajan_transkripti_ara", return_value=ev),                 mock.patch.object(M, "tur_satiri_yaz") as yaz:
            M.cmd_maliyet_tur(a)
        return yaz.call_args[0][1]

    def test_s2_baska_proje_dizinindeki_transkriptten_tip(self):
        tr = os.path.join(self.proje, "wt", "agent-w1.jsonl")
        os.makedirs(os.path.dirname(tr))
        with open(tr, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
        with open(tr[:-6] + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"agentType": "orkestra:denetci"}, f)
        r = self._tur("w1", tr)
        self.assertEqual(r["ajan"], "orkestra:denetci")
        self.assertEqual(r["surec"], "denetim")

    def test_s4_tip_okunamazsa_golge_kaydi(self):
        r = self._tur("w2", None)
        self.assertEqual(r["surec"], "tip-okunamadi")
        g = [json.loads(x) for x in open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8")]
        self.assertTrue(any(x.get("tur") == "kapi_golge" and x.get("kapi") == "ajan_tipi" for x in g))

    # ---- S3: geçmiş onarım
    def test_s3_yeniden_tip_satir(self):
        from komutlar import maliyet as M
        bul = lambda o, a: "orkestra:denetci" if a == "x1" else None
        self.assertEqual(M.yeniden_tip_satir({"surec": "tip-okunamadi", "ajan": "?", "agent_id": "x1", "oturum": "o"}, bul)["surec"], "denetim")
        self.assertEqual(M.yeniden_tip_satir({"surec": "bilinmiyor", "ajan": "general-purpose"}, bul)["surec"], "genel-ajan")
        r = {"surec": "tip-okunamadi", "ajan": "?", "agent_id": "yok", "oturum": "o"}
        self.assertIs(M.yeniden_tip_satir(r, bul), r)
        r2 = {"surec": "is", "ajan": "?"}
        self.assertIs(M.yeniden_tip_satir(r2, bul), r2)

    def test_s3_komut_yedek_alir_ve_yazar(self):
        import argparse
        from komutlar import maliyet as M
        yol = os.path.join(self.sd, "maliyet.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            f.write(json.dumps({"surec": "bilinmiyor", "ajan": "orkestra:test-yazari", "maliyet_usd": 1}) + "\n")
            f.write(json.dumps({"surec": "tip-okunamadi", "ajan": "?", "agent_id": "yok", "oturum": "o"}) + "\n")
        with mock.patch.object(M, "sd_gerekli", return_value=self.sd), mock.patch.object(L, "alt_ajan_transkripti_ara", return_value=None),                 contextlib.redirect_stdout(io.StringIO()):
            M.cmd_maliyet_yeniden_tip(argparse.Namespace(uygula=False))
            self.assertEqual(json.loads(open(yol, encoding="utf-8").readline())["surec"], "bilinmiyor")
            M.cmd_maliyet_yeniden_tip(argparse.Namespace(uygula=True))
        satir = [json.loads(x) for x in open(yol, encoding="utf-8")]
        self.assertEqual(satir[0]["surec"], "test-yaz")
        self.assertEqual(satir[1]["surec"], "tip-okunamadi")
        self.assertTrue([f for f in os.listdir(self.sd) if f.startswith("maliyet.jsonl.yedek-")])


if __name__ == "__main__":
    unittest.main()
