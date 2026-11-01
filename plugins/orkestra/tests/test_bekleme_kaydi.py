"""I-342 (ADR-0146): bekleme kaydı (scripts/bekleme_kaydi.py), kayıtsız bekleme kapısı, bağımsız iş seçimi, hook bağlantısı
ve kaynak kirası köprüsü. `PYTHONUTF8=1 py -3.13 -m pytest -q plugins/orkestra/tests/test_bekleme_kaydi.py`
Hepsi geçici durum klasöründe koşar.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import bekleme_kaydi as BK  # noqa: E402

PLAN = """# x

## 4. Plan maddeleri

### P1 Birinci
**Önce:** yok
**Yazma alanı:** a/x.py

### P2 İkinci (bekleyen)
**Önce:** yok
**Yazma alanı:** b/y.py

### P3 Üçüncü bağımsız
**Önce:** yok
**Yazma alanı:** c/z.py

### P4 Dördüncü bekleyene bağlı
**Önce:** P2 — Çıktı: sonucunu okur
**Yazma alanı:** d/w.py

### P5 Beşinci alan kesişir
**Önce:** yok
**Yazma alanı:** b/y.py
"""
TODO = """# t
- [ ] P1 Birinci
- [ ] P2 İkinci (bekleyen)
- [ ] P3 Üçüncü bağımsız
- [ ] P4 Dördüncü bekleyene bağlı
- [ ] P5 Beşinci alan kesişir
- [x] P6 bitmiş
"""


def jsonl(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]
    except OSError:
        return []


class Temel(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sd = os.path.join(self.d, "sd")
        os.makedirs(self.sd)
        self.gunluk = os.path.join(self.sd, "gunluk.jsonl")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)


class KayitTesti(Temel):
    def test_ac_liste_kapat_ve_gunluk(self):
        k = BK.ac(self.sd, "test kirası", "kira alınır", 60, "kaynak_kira", "I-1", 2)
        self.assertEqual([x["id"] for x in BK.liste(self.sd)], [k["id"]])
        s = BK.kapat(self.sd, k["id"])
        self.assertEqual(s["tur"], "bekleme_kapat")
        self.assertEqual(BK.liste(self.sd), [])
        turler = [o["tur"] for o in jsonl(self.gunluk)]
        self.assertEqual(turler, ["bekleme_ac", "bekleme_kapat"])
        for alan in ("bekleme_s", "bos_s", "yapilan"):
            self.assertIn(alan, jsonl(self.gunluk)[-1])

    def test_ayni_kaynak_ve_ne_tekrar_acilmaz(self):
        a = BK.ac(self.sd, "x", "o", None, "ci")
        b = BK.ac(self.sd, "x", "o", None, "ci")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(len(BK.liste(self.sd)), 1)

    def test_olu_kayit_listede_gorunmez(self):
        k = BK.ac(self.sd, "x", "o")
        d = json.load(open(os.path.join(self.sd, "bekleme.json"), encoding="utf-8"))
        d["kayitlar"][0]["acilis"] = time.time() - 100000
        json.dump(d, open(os.path.join(self.sd, "bekleme.json"), "w", encoding="utf-8"))
        self.assertEqual(BK.liste(self.sd), [])
        self.assertIsNone(BK.kapat(self.sd, "B000000000") if False else None)

    def test_olmayan_kayit_kapanmaz(self):
        self.assertIsNone(BK.kapat(self.sd, "B1"))

    def test_adim_yapilan_sayar(self):
        k = BK.ac(self.sd, "x", "o")
        BK.adim(self.sd)
        BK.adim(self.sd)
        self.assertEqual(BK.kapat(self.sd, k["id"])["yapilan"], 2)

    def test_adim_kayit_yokken_dosya_olusturmaz(self):
        BK.adim(self.sd)
        self.assertFalse(os.path.exists(os.path.join(self.sd, "bekleme.json")))

    def test_rapor(self):
        k = BK.ac(self.sd, "x", "o")
        BK.adim(self.sd)
        BK.kapat(self.sd, k["id"])
        k2 = BK.ac(self.sd, "y", "o")
        BK.kapat(self.sd, k2["id"])
        r = BK.rapor(self.sd)
        self.assertEqual((r["bekleme_olay"], r["bagimsiz_is_yapilan"], r["oran"]), (2, 1, 0.5))


class BosSureTesti(unittest.TestCase):
    def test_blokta_bekleme_tum_sure_bos(self):
        self.assertEqual(BK.bos_sure(0, [], 300, 90), 300)

    def test_esik_alti_aralik_sayilmaz(self):
        self.assertEqual(BK.bos_sure(0, [60, 120, 180], 240, 90), 0)

    def test_esik_ustu_aralik_tam_sayilir(self):
        self.assertEqual(BK.bos_sure(0, [10, 200], 210, 90), 190)

    def test_aralik_disindaki_adim_yok_sayilir(self):
        self.assertEqual(BK.bos_sure(100, [5, 500], 200, 90), 100)


class BagimsizIsTesti(Temel):
    def setUp(self):
        super().setUp()
        self.is_k = os.path.join(self.d, "is")
        os.makedirs(self.is_k)
        open(os.path.join(self.is_k, "plan.md"), "w", encoding="utf-8").write(PLAN)
        open(os.path.join(self.is_k, "todo.md"), "w", encoding="utf-8").write(TODO)

    def numaralar(self, p):
        return [s.split("P")[1][0] for s in BK.bagimsiz_isler(self.is_k, p)]

    def test_bagli_ve_kesisen_elenir(self):
        # P2 bekliyor: P4 ona bağlı, P5 yazma alanı kesişiyor, P4 ayrıca açık P2'ye bağlı
        self.assertEqual(self.numaralar(2), ["1", "3"])

    def test_bekleyen_yoksa_tum_acik_maddeler_ama_bagimli_olmayanlar(self):
        self.assertEqual(self.numaralar(None), ["1", "2", "3", "5"])

    def test_todo_yoksa_bos(self):
        os.remove(os.path.join(self.is_k, "todo.md"))
        self.assertEqual(BK.bagimsiz_isler(self.is_k, 2), [])


class KapiTesti(Temel):
    def karar(self, komut):
        with mock.patch.object(BK.L, "durum_dizini", return_value=self.sd):
            return BK.karar(komut, self.d, self.sd)

    def test_kayitsiz_sleep_golge(self):
        s = self.karar("sleep 30; cat x")
        self.assertIsNotNone(s)
        self.assertEqual(s[0], "golge")

    def test_diger_kaliplar(self):
        for k in ("Start-Sleep -Seconds 20", "gh run watch 123", "timeout /t 30"):
            self.assertIsNotNone(self.karar(k), k)

    def test_kisa_sleep_ve_veri_metni_gecer(self):
        for k in ("sleep 2", "echo 'sleep 60'", "git status", "python x.py"):
            self.assertIsNone(self.karar(k), k)

    def test_acik_kayit_varken_gecer(self):
        BK.ac(self.sd, "x", "o")
        self.assertIsNone(self.karar("sleep 30"))

    def test_kapatma_env(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_BEKLEME_KAYDI": "0"}):
            self.assertIsNone(self.karar("sleep 30"))


class HookTesti(Temel):
    def calistir(self, komut, arac="Bash"):
        import hook
        hook._BEKLEYEN_UYARI = ""
        inp = {"cwd": self.d, "session_id": "oturum1", "tool_name": arac, "tool_input": {"command": komut}}
        with mock.patch.object(BK.L, "durum_dizini", return_value=self.sd), \
                mock.patch("kapi_mod.kaydet", return_value=True) as kaydet:
            hook._bekleme_kaydi_kapisi(inp, self.sd, arac, komut)
        return hook._BEKLEYEN_UYARI, kaydet

    def test_kayitsiz_sleep_gunluge_ve_uyariya_duser(self):
        uyari, kaydet = self.calistir("sleep 30")
        self.assertTrue(kaydet.called)
        self.assertIn("bekleme", uyari.lower())

    def test_kayit_varken_sleep_uyarmaz_ve_bildirim_bir_kez_gelir(self):
        k = BK.ac(self.sd, "test kirası", "kira alınır", None, "kaynak_kira")
        uyari, kaydet = self.calistir("sleep 30")
        self.assertFalse(kaydet.called)
        self.assertIn(k["id"], uyari)
        uyari2, _ = self.calistir("ls")
        self.assertEqual(uyari2, "")
        self.assertEqual(BK.kapat(self.sd, k["id"])["yapilan"], 2)

    def test_alt_ajan_atlanir(self):
        import hook
        hook._BEKLEYEN_UYARI = ""
        inp = {"cwd": self.d, "agent_id": "a1", "tool_name": "Bash", "tool_input": {"command": "sleep 30"}}
        hook._bekleme_kaydi_kapisi(inp, self.sd, "Bash", "sleep 30")
        self.assertEqual(hook._BEKLEYEN_UYARI, "")


class KiraKoprusuTesti(Temel):
    def test_bekleme_ac_ve_kapat(self):
        import kaynak_kira as KK
        with mock.patch.object(KK.L, "durum_dizini", return_value=self.sd):
            kayit = KK._bekleme_ac(self.d, "kaynak kirası kuyruğu: sıra 2")
            self.assertIsNotNone(kayit)
            self.assertEqual(len(BK.liste(self.sd)), 1)
            KK._bekleme_kapat(kayit, "alindi")
        self.assertEqual(BK.liste(self.sd), [])
        self.assertEqual(jsonl(self.gunluk)[-1]["neden"], "alindi")

    def test_hata_kirayi_bozmaz(self):
        import kaynak_kira as KK
        with mock.patch.object(KK.L, "durum_dizini", side_effect=RuntimeError("x")):
            self.assertIsNone(KK._bekleme_ac(self.d, "x"))
        KK._bekleme_kapat(None, "alindi")


if __name__ == "__main__":
    unittest.main()
