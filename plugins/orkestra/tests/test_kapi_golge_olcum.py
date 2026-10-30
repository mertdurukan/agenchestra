"""I-284 P4: gölge kayıtlarını transkriptle yeniden sınıflayan ölçüm betiği."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import kapi_golge_olcum as KO  # noqa: E402

OT = "oturum-1"


def _kullanici(zt, m="yap"):
    return {"type": "user", "timestamp": zt, "message": {"role": "user", "content": m}}


def _asistan(zt, icerik):
    return {"type": "assistant", "timestamp": zt, "message": {"role": "assistant", "content": icerik}}


class TestOlcum(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_olcum_")
        self.kok = os.path.join(self.tmp, "projects")
        os.makedirs(os.path.join(self.kok, "p"))
        self.gunluk = os.path.join(self.tmp, "gunluk.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def yaz(self, satirlar, kayitlar):
        with open(os.path.join(self.kok, "p", OT + ".jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(s) for s in satirlar) + "\n")
        with open(self.gunluk, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(k) for k in kayitlar) + "\n")

    def test_salt_recap_ihlal_degil_ask_butonsuz_ihlal(self):
        edit = {"type": "tool_use", "id": "1", "name": "Edit", "input": {"file_path": "a"}}
        recap = {"type": "tool_use", "id": "2", "name": "mcp__ccd_turn__wrap_up", "input": {"recap": "bitti"}}
        ask = {"type": "tool_use", "id": "3", "name": "mcp__ccd_turn__wrap_up", "input": {"recap": "r", "ask": "Karar?"}}
        satirlar = [_kullanici("2026-10-30T10:00:00Z"), _asistan("2026-10-30T10:00:05Z", [edit, recap, {"type": "text", "text": "Bitti."}]),
                    _kullanici("2026-10-30T10:10:00Z"), _asistan("2026-10-30T10:10:05Z", [edit, ask, {"type": "text", "text": "Hazır."}])]
        kayit = lambda z: {"tur": "kural_ihlal", "kural": "secim_ekrani_yapisal", "oturum": OT, "zaman": z, "tetik": "degisiklik"}
        self.yaz(satirlar, [kayit("2026-10-30T13:00:06+03:00"), kayit("2026-10-30T13:10:06+03:00")])
        s = KO.olc(self.gunluk, self.kok)
        self.assertEqual(s["toplam"], 2)
        self.assertEqual(s["yeni_tetik"], {"degisiklik": 1, "ask_butonsuz": 1})
        self.assertEqual(s["gercek_ihlal"], 1)

    def test_transkript_yoksa_bulunamadi(self):
        with open(self.gunluk, "w", encoding="utf-8") as f:
            f.write(json.dumps({"tur": "kural_ihlal", "kural": "secim_ekrani_yapisal", "oturum": "yok", "zaman": "2026-10-30T13:00:00+03:00"}) + "\n")
        s = KO.olc(self.gunluk, self.kok)
        self.assertEqual((s["toplam"], s["bulunamadi"]), (0, 1))
        self.assertEqual(KO.esik_raporu(s, 0.1), "ölçülecek kayıt yok")


if __name__ == "__main__":
    unittest.main()
