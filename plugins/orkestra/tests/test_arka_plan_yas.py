"""ADR-0123 (G3): Stop arka plan satırına görev yaşı ve find.exe eki (scripts/arka_plan_yas.py).
`python -m pytest -q plugins/orkestra/tests/test_arka_plan_yas.py`
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import arka_plan_yas as Y  # noqa: E402

SIMDI = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dk_once):
    return (SIMDI - timedelta(minutes=dk_once)).isoformat().replace("+00:00", "Z")


class AlanYaslari(unittest.TestCase):
    def test_iso_epoch_ve_milisaniye(self):
        t = SIMDI.timestamp()
        g = [{"started_at": _iso(12)}, {"start_time": t - 300}, {"created_at": (t - 60) * 1000}, {"ad": "alansız"}, "metin"]
        yaslar = sorted(Y.alan_yaslari(g, t))
        self.assertEqual([round(y) for y in yaslar], [60, 300, 720])

    def test_bozuk_deger_atlanir(self):
        self.assertEqual(Y.alan_yaslari([{"started_at": "dün"}, {"started_at": None}], SIMDI.timestamp()), [])


class EkMetin(unittest.TestCase):
    def test_12_dk_gorev_esik_ustu(self):
        m = Y.ek_metin([{"started_at": _iso(12)}], simdi=SIMDI.timestamp(), cocuklar=[])
        self.assertIn("en eski 12 dk", m)
        self.assertIn("10 dk üstü", m)

    def test_3_dk_gorev_esik_altinda(self):
        m = Y.ek_metin([{"started_at": _iso(3)}], simdi=SIMDI.timestamp(), cocuklar=[])
        self.assertIn("en eski 3 dk", m)
        self.assertNotIn("üstü", m)

    def test_cocuk_surec_listelenir(self):
        m = Y.ek_metin([{"started_at": _iso(1)}], simdi=SIMDI.timestamp(), cocuklar=[(4242, 780.0)])
        self.assertIn("find.exe PID 4242 (13 dk)", m)

    def test_veri_yoksa_bos(self):
        self.assertEqual(Y.ek_metin([{"id": "x"}], transkript=None, simdi=SIMDI.timestamp(), cocuklar=[]), "")


class TranskriptYasi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_yas_")
        self.yol = os.path.join(self.tmp, "t.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _yaz(self, satirlar):
        with open(self.yol, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")

    def _arac(self, kimlik, dk_once, arka=True):
        return {"type": "assistant", "timestamp": _iso(dk_once),
                "message": {"content": [{"type": "tool_use", "id": kimlik, "name": "Bash",
                                         "input": {"command": "x", "run_in_background": arka}}]}}

    def test_acik_arka_plan_araci_yasi(self):
        self._yaz([self._arac("t1", 12), self._arac("t2", 2), self._arac("t3", 30, arka=False)])
        yaslar = Y.transkript_yaslari(self.yol, SIMDI.timestamp())
        self.assertEqual([round(y / 60) for y in yaslar], [12, 2])

    def test_biten_gorev_dusulur(self):
        bildirim = {"type": "user", "timestamp": _iso(1), "message": {"content":
                    "<task-notification><tool-use-id>t1</tool-use-id><status>completed</status></task-notification>"}}
        self._yaz([self._arac("t1", 12), self._arac("t2", 2), bildirim])
        self.assertEqual([round(y / 60) for y in Y.transkript_yaslari(self.yol, SIMDI.timestamp())], [2])

    def test_ek_metin_transkriptten(self):
        self._yaz([self._arac("t1", 15)])
        with mock.patch.object(Y, "datetime", wraps=datetime) as d:
            d.now.return_value = SIMDI
            m = Y.ek_metin([{"id": "x"}], transkript=self.yol, simdi=SIMDI.timestamp(), cocuklar=[])
        self.assertIn("en eski 15 dk", m)

    def test_olmayan_dosya_sessiz(self):
        self.assertEqual(Y.transkript_yaslari(os.path.join(self.tmp, "yok.jsonl"), SIMDI.timestamp()), [])


class CocukSurec(unittest.TestCase):
    def test_cikti_ayrisir(self):
        cikti = "4242 " + (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat() + "\nbozuk satır\n"
        with mock.patch.object(Y.sys, "platform", "win32"):
            s = Y.cocuk_surecler(calistir=lambda c: cikti)
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0][0], 4242)
        self.assertAlmostEqual(s[0][1] / 60, 5, delta=0.2)

    def test_windows_disinda_bos(self):
        with mock.patch.object(Y.sys, "platform", "linux"):
            self.assertEqual(Y.cocuk_surecler(calistir=lambda c: "1 2026-01-01T00:00:00+00:00"), [])

    def test_hata_sessiz(self):
        def patla(c):
            raise OSError("yok")
        with mock.patch.object(Y.sys, "platform", "win32"):
            self.assertEqual(Y.cocuk_surecler(calistir=patla), [])


class HookBaglantisi(unittest.TestCase):
    def test_satira_yas_eklenir(self):
        import hook
        g = [{"description": "tarama", "started_at": (datetime.now(timezone.utc) - timedelta(minutes=12, seconds=5)).isoformat()}]
        with mock.patch.object(Y, "cocuk_surecler", return_value=[]):
            satir = hook.arka_plan_satiri(tempfile.gettempdir(), g)
        self.assertIn("Arka planda sürüyor (1): tarama", satir)
        self.assertIn("en eski 12 dk", satir)

    def test_gorevsiz_satir_degismez(self):
        import hook
        self.assertEqual(hook.arka_plan_satiri(tempfile.gettempdir(), None), "")


if __name__ == "__main__":
    unittest.main()
