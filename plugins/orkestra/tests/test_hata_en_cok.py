"""G-176: scripts/hata_en_cok.py (birlestir, esik_satiri), `orkestra hata en-cok|liste` ve SessionStart HATA satırı."""
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(AD, "..", "scripts"))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, AD)

import ork_lib as L  # noqa: E402
import hata_en_cok as HE  # noqa: E402
import kural_aday as KA  # noqa: E402
import hook  # noqa: E402
import ic_kos  # noqa: E402


def yaz(sd, ad, satirlar):
    with open(os.path.join(sd, ad), "w", encoding="utf-8") as f:
        for s in satirlar:
            f.write((s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)) + "\n")


def simdi_oncesi(sn=0):
    import datetime
    return (datetime.datetime.now().astimezone() - datetime.timedelta(seconds=sn)).isoformat(timespec="seconds")


def kart(sd, kid, sinif, retler, durum="teslim"):
    os.makedirs(os.path.join(sd, "gorevler"), exist_ok=True)
    den = [{"zaman": simdi_oncesi(), "sira": i + 1, "karar": "ret", "neden": n} for i, n in enumerate(retler)]
    with open(os.path.join(sd, "gorevler", f"{kid}.json"), "w", encoding="utf-8") as f:
        json.dump({"id": kid, "sinif": sinif, "basamak": "T2", "durum": durum, "denetimler": den}, f)


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.proje = self.t.name
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)


class Birlestir(Temel):
    def test_kaynaklar_imza_ve_alanlar(self):
        z = simdi_oncesi()
        yaz(self.sd, "hata.jsonl", [
            {"kaynak": "cli", "tur": "CliHata", "ileti": "kart 12 yok", "zaman": z},
            {"kaynak": "cli", "tur": "CliHata", "ileti": "kart 34 yok", "zaman": z},
            {"kaynak": "ozet", "tur": "PermissionError", "ileti": "[WinError 5] Erisim engellendi: 'C:\\a\\.tmp_x1'", "zaman": z}])
        yaz(self.sd, "gunluk.jsonl", [{"zaman": z, "tur": "kural_ihlal", "kural": "belge_bicim", "dosya": "a.md"}])
        kart(self.sd, "G-001", "kod", ["kanit-yok"])
        s = {(r["kaynak"], r["imza"]): r for r in HE.birlestir(self.sd, 0)}
        self.assertEqual(s[("cli", "CliHata: kart N yok")]["sayi"], 2)
        self.assertEqual(s[("kural", "kural:belge_bicim")]["ornek"], "a.md")
        self.assertEqual(s[("kart", "kart:kod:kanit-yok")]["ornek"], "G-001")
        self.assertIn(("ozet", "PermissionError: [WinError 5] Erisim engellendi: '<yol>'"), s)
        for r in s.values():
            self.assertEqual(set(r), {"imza", "kaynak", "sayi", "son_zaman", "ornek"})

    def test_hook_cift_sayim_yok_eski_satir_tek(self):
        z = simdi_oncesi()
        # yeni: gunluk + hata.jsonl (aynı olay) = 1; eski: yalnız gunluk = 1
        yaz(self.sd, "gunluk.jsonl", [
            {"zaman": z, "tur": "hook-hatasi", "olay": "SessionStart", "hata": "OSError: [Errno 22] Invalid argument: 'C:\\x\\.tmp_a'"},
            {"zaman": simdi_oncesi(86400 * 3), "tur": "hook-hatasi", "olay": "Stop", "hata": "OSError: [Errno 22] Invalid argument: 'C:\\y\\.tmp_b'"}])
        yaz(self.sd, "hata.jsonl", [{"kaynak": "hook", "tur": "OSError", "ileti": "[Errno 22] Invalid argument: 'C:\\x\\.tmp_a'",
                                      "zaman": z, "baglam": {"yer": "SessionStart"}}])
        hook_satirlari = [r for r in HE.birlestir(self.sd, 0) if r["kaynak"] == "hook"]
        self.assertEqual(len(hook_satirlari), 1)
        self.assertEqual(hook_satirlari[0]["sayi"], 2)
        self.assertTrue(hook_satirlari[0]["imza"].startswith("OSError: [Errno 22]"))

    def test_gun_ve_kaynak_suzgeci(self):
        yaz(self.sd, "gunluk.jsonl", [
            {"zaman": simdi_oncesi(86400 * 30), "tur": "hook-hatasi", "olay": "A", "hata": "KeyError: 'a'"},
            {"zaman": simdi_oncesi(), "tur": "hook-hatasi", "olay": "B", "hata": "KeyError: 'b'"},
            {"zaman": simdi_oncesi(), "tur": "kural_ihlal", "kural": "k1"}])
        self.assertEqual([r["imza"] for r in HE.birlestir(self.sd, 7, "hook")], ["KeyError: 'b'"])
        self.assertEqual(len(HE.birlestir(self.sd, 0, "hook")), 2)
        self.assertEqual([r["kaynak"] for r in HE.birlestir(self.sd, 0, "kural")], ["kural"])

    def test_siralama_sayiya_gore(self):
        yaz(self.sd, "hata.jsonl", [{"kaynak": "cli", "tur": "T", "ileti": m, "zaman": simdi_oncesi()} for m in ("a", "b", "b", "b", "c", "c")])
        self.assertEqual([r["sayi"] for r in HE.birlestir(self.sd, 0)], [3, 2, 1])


class Toplamlar(Temel):
    def test_kart_ret_toplami_kural_aday_ile_ayni(self):
        kart(self.sd, "G-001", "kod", ["kanit-yok", "kanit-yok", "kapsam-eksik"])
        kart(self.sd, "G-002", "arastirma", ["kanit-yok", "bilinmeyen-kod"])
        kart(self.sd, "G-003", "kod", ["kapsam-eksik"])
        kartlar = L.kartlar(self.sd)
        beklenen = sum(a["sayi"] for a in KA.kural_adaylari(kartlar, esik=1))
        self.assertEqual(beklenen, 7)
        self.assertEqual(sum(r["sayi"] for r in HE.birlestir(self.sd, 0, "kart")), beklenen)

    def test_kural_ihlali_toplami_gunluk_satir_sayisi(self):
        satirlar = [{"zaman": simdi_oncesi(), "tur": "kural_ihlal", "kural": k, "mod": "ihlal"} for k in ["a"] * 4 + ["b"] * 3]
        satirlar += [{"zaman": simdi_oncesi(), "tur": "istek"}] * 5
        yaz(self.sd, "gunluk.jsonl", satirlar)
        ihlal = sum(1 for s in satirlar if s["tur"] == "kural_ihlal")
        self.assertEqual(sum(r["sayi"] for r in HE.birlestir(self.sd, 0, "kural")), ihlal)
        self.assertEqual(ihlal, 7)


class Komut(Temel):
    def kos(self, *a):
        return ic_kos.kos([os.path.join(SCRIPTS, "orkestra.py"), *a], cwd=self.proje)

    def test_en_cok_ve_liste_cikis_0_salt_okur(self):
        yaz(self.sd, "hata.jsonl", [{"kaynak": "cli", "imza": "x", "tur": "CliHata", "ileti": "m", "zaman": simdi_oncesi()}] * 2)
        once = sorted(os.listdir(self.sd))
        r = self.kos("hata", "en-cok", "--gun", "365")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[cli] CliHata: m", r.stdout)
        r = self.kos("hata", "en-cok", "--kaynak", "cli", "--ilk", "1", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)[0]["sayi"], 2)
        r = self.kos("hata", "liste")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(os.listdir(self.sd)), once)


class Uyari(Temel):
    def hook_satirlari(self, n):
        return [{"zaman": simdi_oncesi(), "tur": "hook-hatasi", "olay": "O", "hata": "KeyError: 'x'"}] * n

    def test_esigin_altinda_satir_yok(self):
        yaz(self.sd, "gunluk.jsonl", self.hook_satirlari(2))
        self.assertEqual(HE.esik_satiri(self.sd), "")
        self.assertFalse(any(u.startswith("HATA:") for u in hook._ss_uyarilar(self.sd, {})[0]))

    def test_esigin_ustunde_tek_satir(self):
        yaz(self.sd, "gunluk.jsonl", self.hook_satirlari(3))
        s = HE.esik_satiri(self.sd)
        self.assertEqual(s, "HATA: KeyError: 'x' 3 kez (orkestra hata en-cok)")
        self.assertLessEqual(len(s), 120)
        self.assertEqual([u for u in hook._ss_uyarilar(self.sd, {})[0] if u.startswith("HATA:")], [s])
        yaz(self.sd, "gunluk.jsonl", [dict(h, hata="ValueError: " + "u" * 300) for h in self.hook_satirlari(3)])
        self.assertLessEqual(len(HE.esik_satiri(self.sd)), 120)

    def test_bozuk_dosya_hook_dusmez(self):
        yaz(self.sd, "gunluk.jsonl", ["{bozuk", "[1, 2]", "null", json.dumps({"tur": "hook-hatasi", "zaman": 5, "hata": None})])
        yaz(self.sd, "hata.jsonl", ["\x00\x01 yarım {", '"metin"'])
        os.makedirs(os.path.join(self.sd, "gorevler"))
        with open(os.path.join(self.sd, "gorevler", "G-001.json"), "w") as f:
            f.write("{kırık")
        self.assertEqual(HE.esik_satiri(self.sd), "")
        self.assertEqual(HE.esik_satiri(os.path.join(self.proje, "yok_dizin")), "")
        hook._ss_uyarilar(self.sd, {})   # istisna fırlatmamalı


if __name__ == "__main__":
    unittest.main()
