"""Sessizlik saati (G-094): ajan başına son araç çağrısı, takılı ajan ve sahipsiz kayıt tespiti."""
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


def dk_once(dk):
    return (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=dk)).isoformat(timespec="seconds")


class SessizlikSaati(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_sessiz_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.genel = os.path.join(self.proje, "genel")
        os.makedirs(self.genel)
        self.niyet_yolu = os.path.join(self.genel, "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", self.niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", self.genel),
                   mock.patch.object(ozet, "_transkript_son_dokunus", return_value=None),
                   mock.patch.dict(os.environ, {}, clear=False)]
        for p in self._p:
            p.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_SESSIZLIK_DK"):
            os.environ.pop(k, None)

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def yol(self, aid):
        return os.path.join(self.sd, "oturumlar", f"acik_ajan_{aid}.json")

    def kayit(self, aid, yas_dk, son_arac_dk=None, oturum="o-1"):
        d = {"zaman": dk_once(yas_dk), "oturum": oturum, "agent_id": aid, "ajan": "orkestra:isci-t2", "gorev": "G-001", "surec": "is"}
        if son_arac_dk is not None:
            d["son_arac"] = dk_once(son_arac_dk)
        with open(self.yol(aid), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def niyet_yaz(self, oturum, tur, dk):
        with open(self.niyet_yolu, "a", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": dk_once(dk), "oturum": oturum, "proje": self.proje, "tur": tur}) + "\n")

    def post(self, girdi):
        g = {"session_id": "o-1", "cwd": self.proje, "tool_name": "Bash", "tool_input": {}}
        g.update(girdi)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            hook.post_tool_use(g)

    # --- Kriter 1
    def test_post_tool_use_agent_id_son_arac_zamanini_kaydeder(self):
        self.kayit("a", 40)
        self.post({"agent_id": "a"})
        with open(self.yol("a"), encoding="utf-8") as f:
            d = json.load(f)
        z = ozet.A._zaman(d.get("son_arac"))
        self.assertIsNotNone(z)
        self.assertLess((datetime.datetime.now().astimezone() - z).total_seconds(), 60)
        self.assertEqual(d["gorev"], "G-001")  # kaydın öteki alanları korunur

    def test_agent_id_yoksa_ya_da_kayit_yoksa_dosya_olusmaz(self):
        self.kayit("a", 40)
        self.post({})
        with open(self.yol("a"), encoding="utf-8") as f:
            self.assertNotIn("son_arac", json.load(f))
        self.post({"agent_id": "yok"})
        self.assertFalse(os.path.exists(self.yol("yok")))

    # --- Kriter 2
    def test_esikten_uzun_sessiz_ajan_takili_raporlanir(self):
        self.kayit("a", 40, son_arac_dk=20)
        a = ozet.asili_ajanlar(self.sd)
        self.assertEqual([x["agent_id"] for x in a], ["a"])
        self.assertEqual(a[0]["sessiz_dk"], 20)
        self.assertIn("20 dk sessiz", hook.asili_uyari(self.sd))

    def test_yakin_zamanda_arac_cagiran_uzun_sureli_ajan_raporlanmaz(self):
        self.kayit("a", 120, son_arac_dk=2)
        self.assertEqual(ozet.asili_ajanlar(self.sd), [])
        self.assertTrue(os.path.exists(self.yol("a")))
        self.assertEqual(hook.asili_uyari(self.sd), "")

    # --- Kriter 3
    def test_oturumu_kapanmis_ajan_kaydi_sahipsiz_isaretlenir(self):
        self.kayit("olu", 45, oturum="o-1")
        self.kayit("canli", 45, oturum="o-2")
        self.niyet_yaz("o-1", "kapandi", 40)
        self.niyet_yaz("o-2", "niyet", 1)
        s = ozet.sahipsiz_ajanlar(self.sd)
        self.assertEqual([x["agent_id"] for x in s], ["olu"])
        self.assertTrue(s[0]["sahipsiz"])
        self.assertTrue(os.path.exists(self.yol("olu")))  # salt okuma

    # --- Kriter 4
    def test_esik_sabit_ve_ortam_degiskeniyle_ayarlanir(self):
        self.assertEqual(ozet.ASILI_SESSIZLIK_DK, 15)
        self.assertEqual(ozet._sessizlik_esigi_dk(), 15)
        self.kayit("a", 60, son_arac_dk=10)
        self.assertEqual(ozet.asili_ajanlar(self.sd), [])
        with mock.patch.dict(os.environ, {"ORKESTRA_SESSIZLIK_DK": "5"}):
            self.assertEqual(ozet._sessizlik_esigi_dk(), 5)
            self.assertEqual([x["agent_id"] for x in ozet.asili_ajanlar(self.sd)], ["a"])
        with mock.patch.dict(os.environ, {"ORKESTRA_SESSIZLIK_DK": "bozuk"}):
            self.assertEqual(ozet._sessizlik_esigi_dk(), 15)

    def test_son_arac_olmayan_kayit_eski_yas_kuraliyla_calisir(self):
        self.kayit("yeni", 10)
        self.kayit("eski", 45)
        self.assertEqual([x["agent_id"] for x in ozet.asili_ajanlar(self.sd)], ["eski"])


if __name__ == "__main__":
    unittest.main()
