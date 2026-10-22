"""Claude içi bant yalnız arka plan işi için çıkar: ozet.arka_plan_oturumlari sohbet başına açık görev sayısını verir.

`python -m unittest discover -s plugins/orkestra/tests -v`; geçici projede çalışır, gerçek niyet defterine dokunmaz.
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import niyet  # noqa: E402
import ozet  # noqa: E402

SIMDI = datetime.datetime.now().astimezone()


def dk_once(dk):
    return (SIMDI - datetime.timedelta(minutes=dk)).isoformat(timespec="seconds")


class ArkaPlanOturumlari(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_arka_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.defter = os.path.join(self.proje, "niyet.jsonl")
        self.p = mock.patch.object(niyet, "NIYET_YOLU", self.defter)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def oturum(self, oid, gorevler, guncelleme=None):
        d = {"ofset": 1, "guncelleme": guncelleme or dk_once(1)}
        if gorevler is not None:
            d["acik_gorevler"] = gorevler
        with open(os.path.join(self.sd, "oturumlar", f"{oid}.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def olay(self, oid, tur, dk):
        with open(self.defter, "a", encoding="utf-8") as f:
            f.write(json.dumps({"oturum": oid, "tur": tur, "zaman": dk_once(dk)}) + "\n")

    def test_acik_gorevi_olan_oturum_sayilir_gorevsiz_olmaz(self):
        self.oturum("a", ["t1", "t2"])
        self.oturum("b", None)
        self.oturum("c", [])
        self.olay("a", "tur", 2)
        self.assertEqual(ozet.arka_plan_oturumlari(self.sd, SIMDI), {"a": 2})

    def test_kapanan_ya_da_zaman_asimina_ugrayan_oturum_sayilmaz(self):
        self.oturum("kapali", ["t1"])
        self.olay("kapali", "kapandi", 1)
        self.oturum("eski", ["t1"])
        self.olay("eski", "tur", niyet.ARKA_PLAN_ZAMAN_ASIMI_DK + 5)
        self.oturum("taze", ["t1"])
        self.olay("taze", "tur", niyet.ARKA_PLAN_ZAMAN_ASIMI_DK - 5)
        self.assertEqual(ozet.arka_plan_oturumlari(self.sd, SIMDI), {"taze": 1})

    def test_niyet_kaydi_olmayan_oturum_guncelleme_zamanina_bakar(self):
        self.oturum("yeni", ["t1"], dk_once(5))
        self.oturum("bayat", ["t1"], dk_once(niyet.ARKA_PLAN_ZAMAN_ASIMI_DK + 5))
        self.assertEqual(ozet.arka_plan_oturumlari(self.sd, SIMDI), {"yeni": 1})

    def test_ajan_ve_is_yan_dosyalari_atlanir_oturum_dizini_yoksa_bos(self):
        for ad in ("acik_ajan_x.json", "is_a.json"):
            with open(os.path.join(self.sd, "oturumlar", ad), "w", encoding="utf-8") as f:
                json.dump({"acik_gorevler": ["t1"]}, f)
        self.assertEqual(ozet.arka_plan_oturumlari(self.sd, SIMDI), {})
        self.assertEqual(ozet.arka_plan_oturumlari(os.path.join(self.proje, "yok"), SIMDI), {})


if __name__ == "__main__":
    unittest.main()
