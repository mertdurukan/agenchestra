"""I-138 Kart C: SessionStart boş iş listesi (P6), beklemedeki kartın yaşı/engeli (P7), bilinmeyen hook olayı (P12)."""
import datetime
import json
import os
import subprocess
import sys
import unittest

import test_cekirdek as TC

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402

ANA = {"ajan_id": "ana", "ajan_tipi": "ana"}


class BosIsSatiri(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def is_ac(self, ad, eski_saat, todo=None):
        klasor = os.path.join(self.proje, "isler", ad)
        r = self.cli("is", "ac", "Otomatik iş " + ad, "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        i = r.stdout.split()[0]
        if todo:
            with open(os.path.join(klasor, "todo.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(todo)
        merkez = os.path.join(self.sd, "isler.json")
        with open(merkez, encoding="utf-8") as f:
            d = json.load(f)
        d["isler"][i]["olusturma"] = (datetime.datetime.now().astimezone() - datetime.timedelta(hours=eski_saat)).isoformat(timespec="seconds")
        with open(merkez, "w", encoding="utf-8") as f:
            json.dump(d, f)
        return i

    def durumlar(self):
        with open(os.path.join(self.sd, "isler.json"), encoding="utf-8") as f:
            return {k: v["durum"] for k, v in json.load(f)["isler"].items()}

    def test_p6_49_saatlik_listelenir_todolu_ve_47_saatlik_listelenmez_durum_degismez(self):
        bos = self.is_ac("001-bos", 49)
        self.is_ac("002-todolu", 49, todo="# T\n\n- [ ] madde\n")
        self.is_ac("003-taze", 47)
        once = self.durumlar()
        satir = hook._bos_is_satiri(self.sd)
        self.assertIn(f"boş iş 1 (48 saatten eski): {bos}", satir)
        self.assertIn("kapatmak için orkestra bakim --kapat --uygula", satir)
        self.assertEqual(self.durumlar(), once)

    def test_p6_bos_is_yoksa_satir_bos(self):
        self.is_ac("001-taze", 47)
        self.assertEqual(hook._bos_is_satiri(self.sd), "")

    def test_p7_teslim_bagimlilikli_kart_engeli_teslim_digeri_yasla(self):
        simdi = datetime.datetime.now().astimezone()
        teslim = {"id": "G-1", "durum": "teslim"}
        acik = {"id": "G-2", "durum": "isleniyor"}
        eski = (simdi - datetime.timedelta(days=6, hours=1)).isoformat(timespec="seconds")
        engelsiz = {"id": "G-3", "durum": "beklemede", "bagimliliklar": ["G-1"], "gecmis": [{"olay": "beklemede", "zaman": eski}]}
        yasli = {"id": "G-4", "durum": "beklemede", "bagimliliklar": ["G-2"], "gecmis": [{"olay": "beklemede", "zaman": eski}]}
        tum = {k["id"]: k for k in (teslim, acik, engelsiz, yasli)}
        self.assertIn("engeli G-1 teslim", hook._bekleyen_notu(engelsiz, tum))
        n = hook._bekleyen_notu(yasli, tum)
        self.assertIn("6 gün", n)
        self.assertIn("G-2 bekliyor", n)
        self.assertNotIn("teslim", n)

    def test_p12_bilinmeyen_olay_cikis_0_hook_hatasi_yok(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.proje)
        r = subprocess.run([sys.executable, os.path.join(KOK, "scripts", "hook.py"), "session_start"],
                           input=json.dumps({"cwd": self.proje, "session_id": "x"}), capture_output=True, text=True,
                           encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        gunluk = os.path.join(self.sd, "gunluk.jsonl")
        if os.path.exists(gunluk):
            self.assertNotIn("hook-hatasi", open(gunluk, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
