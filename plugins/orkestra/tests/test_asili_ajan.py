"""Asılı ajan görünürlüğü: `python -m unittest discover -s plugins/orkestra/tests -v`

subagent_start açık ajan kaydı yazar, subagent_stop siler; ozet.asili_ajanlar eşiği (30 dk) ve temizliği (24 saat) uygular.
Hepsi geçici bir projede çalışır; gerçek ~/.claude ya da proje durum dizinine yazılmaz.
"""
import contextlib
import datetime
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
import ozet  # noqa: E402


def dk_once(dk, simdi=None):
    simdi = simdi or datetime.datetime.now().astimezone()
    return (simdi - datetime.timedelta(minutes=dk)).isoformat(timespec="seconds")


class AsiliAjan(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_asili_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        # Niyet defteri (ev dizininde, süreçler arası ortak) geçici dizine alınır: yoksa user_prompt_submit gerçek
        # niyet.jsonl'a "t-oturum" kaydı sızdırır, asili_ajanlar da o kaydı okuyup oturumu sessiz/ölü sayar.
        genel = os.path.join(self.proje, "genel")
        os.makedirs(genel)
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", os.path.join(genel, "niyet.jsonl")),
                   mock.patch.object(niyet, "GENEL_DIZIN", genel),
                   mock.patch.dict(os.environ, {}, clear=False)]
        for p in self._p:
            p.start()
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.environ.pop("ORKESTRA_RUYA", None)
        os.environ.pop("ORKESTRA_PERSPEKTIF", None)

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def calistir(self, fn, girdi):
        """Hook işlevini süreç içinde çalıştırır; gec() SystemExit'ini yakalar, stdout'u döner."""
        g = {"session_id": "t-oturum", "cwd": self.proje, "transcript_path": os.path.join(self.proje, "yok.jsonl")}
        g.update(girdi)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            fn(g)
        return buf.getvalue()

    def yol(self, aid):
        return os.path.join(self.sd, "oturumlar", f"acik_ajan_{aid}.json")

    def kayit_yaz(self, aid, dk, **ek):
        d = {"zaman": dk_once(dk), "oturum": "t-oturum", "agent_id": aid, "ajan": "orkestra:isci-t2", "gorev": "G-001", "surec": "is"}
        d.update(ek)
        with open(self.yol(aid), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def test_baslat_kayit_yazar(self):
        self.calistir(hook.subagent_start, {"agent_id": "a1", "agent_type": "orkestra:isci-t2"})
        with open(self.yol("a1"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["agent_id"], "a1")
        self.assertEqual(d["ajan"], "orkestra:isci-t2")
        self.assertEqual(d["oturum"], "t-oturum")
        for alan in ("zaman", "gorev", "surec"):
            self.assertIn(alan, d)

    def test_baslat_bitir_siler(self):
        self.calistir(hook.subagent_start, {"agent_id": "a2", "agent_type": "Explore"})
        self.assertTrue(os.path.exists(self.yol("a2")))
        self.calistir(hook.subagent_stop, {"agent_id": "a2", "agent_type": "Explore"})
        self.assertFalse(os.path.exists(self.yol("a2")))

    def test_bitir_kayit_yoksa_hata_yok(self):
        self.calistir(hook.subagent_stop, {"agent_id": "yok", "agent_type": "Explore"})

    def test_otuz_dakika_esigi(self):
        self.kayit_yaz("eski", 31)
        self.kayit_yaz("yeni", 5)
        a = ozet.asili_ajanlar(self.sd)
        self.assertEqual([x["agent_id"] for x in a], ["eski"])
        self.assertGreaterEqual(a[0]["dakika"], 31)
        self.assertEqual(a[0]["gorev"], "G-001")
        self.assertTrue(os.path.exists(self.yol("yeni")))  # eşik altı silinmez

    def test_yirmi_bes_saatlik_temizlenir(self):
        self.kayit_yaz("kalinti", 25 * 60)
        self.assertEqual(ozet.asili_ajanlar(self.sd), [])
        self.assertFalse(os.path.exists(self.yol("kalinti")))

    def test_kartsiz_ajan_kaydedilir(self):
        self.calistir(hook.subagent_start, {"agent_id": "k1", "agent_type": "Explore"})
        with open(self.yol("k1"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["gorev"], "-")

    def test_ozet_json_alani(self):
        self.kayit_yaz("asili", 40)
        o = ozet.yaz(self.sd, self.proje)
        self.assertIsNotNone(o)
        with open(os.path.join(self.sd, "ozet.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual([x["agent_id"] for x in d["asili_ajanlar"]], ["asili"])

    def test_uyari_satiri_yalniz_asili_varken(self):
        bos = self.calistir(hook.session_start, {"source": "startup"})
        self.assertNotIn("bitmeyen ajan", bos)
        self.kayit_yaz("asili", 45)
        dolu = json.loads(self.calistir(hook.session_start, {"source": "startup"}))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("bitmeyen ajan", dolu)
        self.assertIn("orkestra:isci-t2 G-001 (45 dk)", dolu)
        self.assertIn("TaskStop", dolu)
        self.assertIn("Orkestra bu projede açık", dolu)  # mevcut içerik korunur
        up = json.loads(self.calistir(hook.user_prompt_submit, {"prompt": "merhaba"}))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("bitmeyen ajan", up)


if __name__ == "__main__":
    unittest.main()
