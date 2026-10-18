"""041 P3: `orkestra bakim` — eski lock, eski oturum kaydı, defter özeti, boş açık işler; varsayılan kuru koşu."""
import json
import os
import time
import unittest

import test_cekirdek as TC

ANA = {"ajan_id": "ana", "ajan_tipi": "ana"}
GUN = 86400


class Bakim(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def dosya(self, goreli, icerik="x", yas_gun=0):
        yol = os.path.join(self.sd, *goreli.split("/"))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik)
        if yas_gun:
            t = time.time() - yas_gun * GUN
            os.utime(yol, (t, t))
        return yol

    def bakim(self, *args):
        r = self.cli("bakim", "--json", *args, **ANA)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_kuru_varsayilan_listeler_degistirmez(self):
        eski = self.dosya("gorevler/G-900.json.lock", yas_gun=40)
        oturum = self.dosya("oturumlar/eski-oturum.json", "{}", yas_gun=60)
        r = self.bakim()
        self.assertEqual(r["mod"], "kuru")
        self.assertIn("gorevler/G-900.json.lock", r["lock"])
        self.assertIn("oturumlar/eski-oturum.json", r["oturum"])
        self.assertTrue(os.path.exists(eski))
        self.assertTrue(os.path.exists(oturum))
        self.assertEqual((r["silinen_lock"], r["arsivlenen_oturum"]), (0, 0))

    def test_uygula_eski_lock_siler_taze_ve_kullanimdakine_dokunmaz(self):
        eski = self.dosya("gorevler/G-900.json.lock", yas_gun=40)
        taze = self.dosya("gorevler/G-901.json.lock", yas_gun=1)
        kullanimda = self.dosya("ortak_x.md.lock", yas_gun=40)  # lock eski ama kaynak yeni: canlı sayılır
        self.dosya("ortak_x.md", "yeni")
        r = self.bakim("--uygula")
        self.assertFalse(os.path.exists(eski))
        self.assertTrue(os.path.exists(taze))
        self.assertTrue(os.path.exists(kullanimda))
        self.assertEqual(r["silinen_lock"], 1)

    def test_uygula_eski_oturumu_arsivler_taze_ve_kendi_oturumuna_dokunmaz(self):
        eski = self.dosya("oturumlar/eski-oturum.json", "{}", yas_gun=60)
        taze = self.dosya("oturumlar/taze-oturum.json", "{}", yas_gun=2)
        benim = self.dosya(f"oturumlar/{TC.OTURUM}.json", "{}", yas_gun=90)
        r = self.bakim("--uygula")
        self.assertEqual(r["arsivlenen_oturum"], 1)
        self.assertFalse(os.path.exists(eski))
        arsiv = [os.path.join(k, a) for k, _, ad in os.walk(os.path.join(self.sd, "oturumlar_arsiv")) for a in ad]
        self.assertEqual([os.path.basename(x) for x in arsiv], ["eski-oturum.json"])
        self.assertTrue(os.path.exists(taze))
        self.assertTrue(os.path.exists(benim))

    def test_defter_ozeti_aylik_yazilir_defter_degismez(self):
        satirlar = [{"zaman": "2026-09-01T10:00:00+03:00"}, {"zaman": "2026-10-02T10:00:00+03:00"}, {"zaman": "2026-10-05T10:00:00+03:00"}]
        yol = self.dosya("ortak_defter.jsonl", "".join(json.dumps(s) + "\n" for s in satirlar))
        once = open(yol, "rb").read()
        r = self.bakim("--uygula")
        self.assertEqual(r["defter"]["satir"], 3)
        self.assertEqual(r["defter"]["aylik"], {"2026-09": 1, "2026-10": 2})
        with open(os.path.join(self.sd, "ortak_defter_ozet.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["aylik"], {"2026-09": 1, "2026-10": 2})
        self.assertEqual(open(yol, "rb").read(), once)

    def is_ac(self, ad, eski_saat=48, todo=None):
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
        import datetime
        d["isler"][i]["olusturma"] = (datetime.datetime.now().astimezone() - datetime.timedelta(hours=eski_saat)).isoformat(timespec="seconds")
        with open(merkez, "w", encoding="utf-8") as f:
            json.dump(d, f)
        return i

    def test_bos_isler_listelenir_dolu_taze_ve_kartli_olmaz(self):
        bos = self.is_ac("001-bos")
        self.is_ac("002-taze", eski_saat=1)
        self.is_ac("003-todolu", todo="# T\n\n- [ ] madde\n")
        kartli = self.is_ac("004-kartli")
        self.kart("--is", kartli)
        r = self.bakim()
        self.assertEqual([g["id"] for g in r["bos_isler"]], [bos])

    def test_kapat_yalniz_uygula_ile_ozetsiz_nedenle_kapatir(self):
        bos = self.is_ac("001-bos")
        self.bakim("--kapat")  # kuru: kapatmaz
        self.assertEqual(json.load(open(os.path.join(self.sd, "isler.json"), encoding="utf-8"))["isler"][bos]["durum"], "acik")
        r = self.bakim("--uygula", "--kapat")
        self.assertEqual(r["kapatilan_is"], [bos])
        self.assertEqual(json.load(open(os.path.join(self.sd, "isler.json"), encoding="utf-8"))["isler"][bos]["durum"], "kapandi")

    def test_kuru_ve_uygula_birlikte_verilemez(self):
        r = self.cli("bakim", "--kuru", "--uygula", **ANA)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
