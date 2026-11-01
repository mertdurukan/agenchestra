"""I-052: panel verisinin tek kaynak/tek kural olması (takma ad, selamlama, alan listesi, iş devri)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as IK  # noqa: E402
import ork_lib as L  # noqa: E402
import soru_sinif as S  # noqa: E402


class TakmaAd(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.sd, "gorevler"))
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump({"sayac": 2, "isler": {"I-002": {"klasor": "k", "baslik": "yeni", "durum": "acik", "olusturma": "x"}},
                       "takma": {"I-001": "I-002"}}, f)
        L.kart_yaz(self.sd, {"id": "G-001", "is": "I-001"})
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"zaman": "2026-10-15T10:00:00+03:00", "oturum": "o1", "gorev": "-", "is": "I-001",
                                "kaynak": "hook", "model": "m", "agent_id": None, "maliyet_usd": 2.5}) + "\n")
        L._MALIYET_ONBELLEK.clear()

    def test_kart_ve_maliyet_yeni_kimlik_altinda(self):
        self.assertEqual([k["is"] for k in L.kartlar(self.sd)], ["I-002"])
        self.assertEqual([r["is"] for r in L.maliyet_kayitlari(self.sd)], ["I-002"])

    def test_ham_kart_dosyasi_degismez(self):
        ham = json.load(open(os.path.join(self.sd, "gorevler", "G-001.json"), encoding="utf-8"))
        self.assertEqual(ham["is"], "I-001")

    def test_zincir_cozulur(self):
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump({"isler": {}, "takma": {"I-001": "I-002", "I-002": "I-003"}}, f)
        self.assertEqual(L.takma_haritasi(self.sd)["I-001"], "I-003")


class IsDevri(unittest.TestCase):
    def test_is_ac_eski_is_json_kimligini_takma_adlar_ve_oturumlari_devralir(self):
        sd = tempfile.mkdtemp()
        klasor = os.path.join(tempfile.mkdtemp(), "001-eski")
        os.makedirs(klasor)
        with open(os.path.join(klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-009", "baslik": "eski", "oturumlar": [{"oturum": "abc", "baglanma": "z"}]}, f)
        yeni = IK.is_ac(sd, "yeni is", klasor, devral=True)  # ADR-0037: devralma yalnız açık bayrakla
        takma = json.load(open(os.path.join(sd, "isler.json"), encoding="utf-8")).get("takma")
        self.assertEqual(takma, {"I-009": yeni["id"]})
        self.assertEqual([o["oturum"] for o in yeni["oturumlar"]], ["abc"])


class Selamlama(unittest.TestCase):
    def test_selamlama_is_acmaz(self):
        for m in ("merhaba", "Merhaba!", "selam", "teşekkürler", "test"):
            self.assertEqual(S.tur(m), "devam", m)
        self.assertEqual(S.tur("merhaba, düzelt şu hatayı"), "is")


class AlanListesi(unittest.TestCase):
    def test_test_ve_worktree_klasorleri_elenir(self):
        import re
        # ork_lib.calisma_alanlari süzgeci ile aynı desen (gerçek ~/.claude/projects taranmaz)
        kaynak = open(os.path.join(os.path.dirname(L.__file__), "ork_lib.py"), encoding="utf-8").read()
        m = re.search(r're\.search\(r"([^"]*worktrees[^"]*)", yol, re\.I\)', kaynak)
        self.assertTrue(m)
        desen = re.compile(m.group(1), re.I)
        for yol in (r"C:\ork_tmp_p11x\ork_canli_1", r"C:\Work\DemoRoot\.claude\worktrees\ab", r"C:\Users\x\AppData\Local\Temp\z"):
            self.assertTrue(desen.search(yol + "\\"), yol)
        self.assertFalse(desen.search(r"C:\Work\DemoRoot" + "\\"))


class SonEtkinlik(unittest.TestCase):
    def test_is_json_ve_todo_degisikligi_son_zamani_ileri_alir(self):
        kl = tempfile.mkdtemp()
        with open(os.path.join(kl, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"guncelleme": "2026-10-17T18:18:00+03:00"}, f)
        g = {"klasor": kl, "olusturma": "2026-10-15T15:27:00+03:00"}
        son = IK.is_son_etkinlik(g, [], "2026-10-17T18:20:00+03:00")
        self.assertGreaterEqual(son, "2026-10-17T18:20:00+03:00")  # todo.md yoksa en geç: harcama


if __name__ == "__main__":
    unittest.main()
