"""teknik.py: deterministik teknik çıkarım ve 7 blok derleyici (G-135, K1-K7). Geçici dizinlerde koşar."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import teknik  # noqa: E402
import test_cekirdek as TC  # noqa: E402

BLOKLAR = {"ne", "neden", "nasil", "degisen", "dogrulama", "maliyet_sure", "ogrenilen"}


def git(cwd, *args, tarih=None):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    if tarih:
        env["GIT_COMMITTER_DATE"] = tarih
        env["GIT_AUTHOR_DATE"] = tarih
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.t", "-c", "commit.gpgsign=false",
                        "-C", cwd, *args], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class Temel(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_teknik_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "gorevler"))

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def kart_yaz(self, **alan):
        k = {"id": "G-001", "baslik": "Deneme kartı", "soru": "Bu çalışır mı?", "sinif": "kod", "basamak": "T2",
             "durum": "isleniyor", "kabul_kriterleri": ["K1: x"], "ciktilar": [], "denetimler": [], "test_kosulari": [],
             "gecmis": [{"zaman": "2026-01-02T00:00:00+00:00", "olay": "olusturuldu"},
                        {"zaman": "2026-01-02T00:00:00+00:00", "olay": "isleniyor"}]}
        k.update(alan)
        yol = os.path.join(self.sd, "gorevler", k["id"] + ".json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False)
        return k

    def dosya(self, ad, metin):
        yol = os.path.join(self.proje, ad)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
        return yol


class K1Bloklar(Temel):
    def test_yedi_blok_ve_eksik(self):
        self.kart_yaz()
        d = teknik.derle(self.sd, "G-001")
        self.assertTrue(BLOKLAR <= set(d))
        self.assertIsInstance(d["eksik"], list)
        self.assertEqual(set(d), BLOKLAR | {"eksik"})
        for b in ("nasil", "degisen", "dogrulama", "maliyet_sure", "ogrenilen"):
            self.assertIn(b, d["eksik"])
        self.assertNotIn("ne", d["eksik"])

    def test_olmayan_kart_hata_doner(self):
        d = teknik.derle(self.sd, "G-999")
        self.assertIn("hata", d)
        self.assertNotIn("ne", d)
        self.assertIn("hata", teknik.derle(self.sd, "../kotu"))


class K2Import(Temel):
    def test_py_ayrimi(self):
        self.dosya("yerelmod.py", "x = 1\n")
        y = self.dosya("a.py", "import os, sys\nimport requests\nfrom yerelmod import x\nfrom . import kardes\n"
                               "import numpy.linalg\ndef f():\n    import json\n")
        r = teknik.import_coz(y, open(y, encoding="utf-8").read(), self.proje)
        self.assertEqual(sorted(r["stdlib"]), ["json", "os", "sys"])
        self.assertEqual(sorted(r["ucuncu_taraf"]), ["numpy", "requests"])
        self.assertIn("yerelmod", r["yerel"])
        self.assertIn(".kardes", r["yerel"])
        self.assertIsNone(r["uyari"])

    def test_js_ts_regex(self):
        kaynak = ("import fs from 'node:fs';\nimport path from \"path\";\nimport React from 'react';\n"
                  "import {a} from '@scope/pkg/alt';\nimport './yerel.js';\nconst x = require('lodash');\n"
                  "const y = require('child_process');\nconst z = await import('../ust');\n")
        for ad in ("a.js", "b.ts", "c.mjs"):
            y = self.dosya(ad, kaynak)
            r = teknik.import_coz(y, kaynak, self.proje)
            self.assertEqual(sorted(r["stdlib"]), ["child_process", "fs", "path"], ad)
            self.assertEqual(sorted(r["ucuncu_taraf"]), ["@scope/pkg", "lodash", "react"], ad)
            self.assertEqual(sorted(r["yerel"]), ["../ust", "./yerel.js"], ad)

    def test_sozdizimi_hatasi_istisna_firlatmaz(self):
        y = self.dosya("bozuk.py", "import os\ndef (:\n")
        self.kart_yaz(ciktilar=[y])
        r = teknik.import_coz(y, open(y, encoding="utf-8").read(), self.proje)
        self.assertEqual((r["stdlib"], r["ucuncu_taraf"], r["yerel"]), ([], [], []))
        self.assertTrue(r["uyari"])
        d = teknik.derle(self.sd, "G-001")
        oto = d["nasil"]["otomatik"]
        self.assertEqual(oto["kutuphaneler"], {"stdlib": [], "ucuncu_taraf": [], "yerel": []})
        self.assertTrue(oto["uyarilar"])


class GitTemel(Temel):
    def hazirla(self):
        git(self.proje, "init", "-q")
        self.dosya("helper.py", "y = 2\n")
        y = self.dosya("m.py", "import os\n")
        git(self.proje, "add", "-A")
        git(self.proje, "commit", "-q", "-m", "bir", tarih="2026-01-01T10:00:00+00:00")
        self.dosya("m.py", "import os\nimport json\nimport requests\nimport helper\n")
        git(self.proje, "add", "-A")
        git(self.proje, "commit", "-q", "-m", "iki", tarih="2026-01-03T10:00:00+00:00")
        self.kart_yaz(ciktilar=[y])
        return y


class K3YeniBagimlilik(GitTemel):
    def test_yalniz_yeni_eklenen(self):
        self.hazirla()
        yeni = teknik.derle(self.sd, "G-001")["nasil"]["otomatik"]["yeni_bagimlilik"]
        self.assertEqual(sorted(yeni), ["m.py: helper", "m.py: json", "m.py: requests"])
        self.assertFalse(any(x.endswith(": os") for x in yeni))


class K4Degisen(GitTemel):
    def test_git_satir_ve_hash(self):
        y = self.hazirla()
        d = teknik.derle(self.sd, "G-001")["degisen"]
        self.assertEqual(d["kaynak"], "git")
        (f,) = d["dosyalar"]
        self.assertEqual((f["ekle"], f["sil"]), (3, 0))
        self.assertEqual(f["son_commit"], git(self.proje, "rev-parse", "HEAD"))
        self.assertEqual(f["temel"], git(self.proje, "rev-parse", "HEAD~1"))
        self.assertEqual(d["son_commit"], f["son_commit"])

    def test_git_yok(self):
        disi = tempfile.mkdtemp(prefix="ork_gityok_")
        try:
            y = os.path.join(disi, "x.py")
            with open(y, "w", encoding="utf-8") as f:
                f.write("import os\n")
            self.kart_yaz(ciktilar=[y])
            d = teknik.derle(self.sd, "G-001")["degisen"]
            self.assertEqual(d["kaynak"], "git-yok")
            self.assertEqual(d["dosyalar"][0]["kaynak"], "git-yok")
        finally:
            shutil.rmtree(disi, ignore_errors=True)


class K5MaliyetDogrulama(Temel):
    def test_token_alani_kullanilmaz_defter_toplami_eslesir(self):
        satirlar = [
            {"zaman": "2026-01-02T00:01:00+00:00", "oturum": "o", "gorev": "G-001", "ajan": "isci", "model": "m1",
             "kaynak": "hook", "maliyet_usd": 0.25},
            {"zaman": "2026-01-02T00:02:00+00:00", "oturum": "o", "gorev": "G-001", "ajan": "isci", "model": "m1",
             "kaynak": "hook", "maliyet_usd": 0.5},
            {"zaman": "2026-01-02T00:03:00+00:00", "oturum": "o", "gorev": "G-001", "ajan": "denetci", "model": "m2",
             "kaynak": "hook", "maliyet_usd": 1.0},
            {"zaman": "2026-01-02T00:04:00+00:00", "oturum": "o", "gorev": "G-002", "ajan": "isci", "model": "m1",
             "kaynak": "hook", "maliyet_usd": 99.0},
        ]
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")
        self.kart_yaz(token={"giris": 10**9, "cikis": 10**9, "usd": 12345.0}, tokens=10**12, denetimler=[
            {"sira": 1, "karar": "ret", "neden": "kanit-yok", "kok": "kanit",
             "gerekce": "Eksikler:\n- K1: kanıt yok\nK3: sayı tutarsız\nilgisiz satır", "talimat": "kanıt ekle"},
            {"sira": 2, "karar": "onay", "gerekce": "tamam"}],
            test_kosulari=[{"asama": "yesil", "gecti": True, "cikis_kodu": 0, "zaman": "z"}],
            onkontrol_kosulari=[{"gecti": True, "ihlal_turleri": [], "zaman": "z"}])
        d = teknik.derle(self.sd, "G-001")
        m = d["maliyet_sure"]
        self.assertEqual(m["toplam_usd"], 1.75)
        self.assertEqual({(x["ajan"], x["model"]): x["usd"] for x in m["maliyet"]},
                         {("isci", "m1"): 0.75, ("denetci", "m2"): 1.0})
        self.assertNotIn("maliyet_sure", d["eksik"])
        dg = d["dogrulama"]
        self.assertEqual(dg["denetimler"][0]["karar"], "ret")
        self.assertEqual(dg["denetimler"][0]["neden"], "kanit-yok")
        self.assertEqual(dg["denetimler"][0]["k_satirlari"], ["K1: kanıt yok", "K3: sayı tutarsız"])
        self.assertEqual(dg["denetimler"][0]["gerekce"], "Eksikler:\n- K1: kanıt yok\nK3: sayı tutarsız\nilgisiz satır")
        self.assertEqual(dg["denetimler"][1]["gerekce"], "tamam")
        self.assertEqual(len(dg["test_kosulari"]), 1)
        self.assertEqual(len(dg["onkontrol_kosulari"]), 1)
        self.assertEqual(d["maliyet_sure"]["sureler"].get("kuyruk_sn"), 0.0)


class K7SaltOkuma(GitTemel):
    def test_kart_dosyasi_degismez_ve_ag_yok(self):
        self.hazirla()
        yol = os.path.join(self.sd, "gorevler", "G-001.json")
        h = lambda: hashlib.sha256(open(yol, "rb").read()).hexdigest()  # noqa: E731
        once = h()
        import socket
        asil = socket.socket.connect
        socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ağ çağrısı"))
        try:
            teknik.derle(self.sd, "G-001")
            teknik.derle(self.sd, "G-001")
        finally:
            socket.socket.connect = asil
        self.assertEqual(once, h())

    def test_kaynakta_ag_ve_llm_yok(self):
        kaynak = open(teknik.__file__, encoding="utf-8").read()
        for yasak in ("urllib", "requests", "socket", "http.client", "anthropic", "openai"):
            self.assertNotIn("import " + yasak, kaynak)


class K6Cli(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def kart_degistir(self, gid, **alan):
        yol = os.path.join(self.sd, "gorevler", gid + ".json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        k.update(alan)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False)

    def test_goster_json(self):
        g = self.kart()
        self.kart_degistir(g, teknik={"yaklasim": "Y" * 25, "neden_bu_yol": "N" * 25, "alternatifler": [],
                                      "entegrasyon": [], "riskler": ["bir risk"]})
        r = self.cli("teknik", "goster", g, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertTrue(BLOKLAR <= set(d))
        self.assertEqual(d["nasil"]["teknik"]["riskler"], ["bir risk"])
        self.assertNotIn("nasil", d["eksik"])
        self.assertIn(g, self.cli("teknik", "goster", g).stdout)
        self.assertNotEqual(self.cli("teknik", "goster", "G-999").returncode, 0)

    def test_md_yaz_sira_ve_maske(self):
        klasor = os.path.join(self.proje, "is1")
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        is_id = r.stdout.strip()
        a, b, c = self.kart(), self.kart(), self.kart()
        # oluşturma sırası: b < c < a (kimlik sırası değil)
        self.kart_degistir(a, olusturma="2026-01-03T00:00:00+00:00")
        self.kart_degistir(b, olusturma="2026-01-01T00:00:00+00:00",
                           teknik={"yaklasim": "Anahtar api_key=SAHTEANAHTAR123456789 kullanıldı", "neden_bu_yol": "N" * 25,
                                   "alternatifler": [], "entegrasyon": [], "riskler": []})
        self.kart_degistir(c, olusturma="2026-01-02T00:00:00+00:00")
        isj = os.path.join(klasor, "is.json")
        with open(isj, encoding="utf-8") as f:
            kayit = json.load(f)
        kayit["kartlar"] = [a, b, c]
        with open(isj, "w", encoding="utf-8") as f:
            json.dump(kayit, f)
        r = self.cli("teknik", "md", is_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(klasor, "teknik_detay.md")))
        r = self.cli("teknik", "md", is_id, "--yaz")
        self.assertEqual(r.returncode, 0, r.stderr)
        yol = os.path.join(klasor, "teknik_detay.md")
        self.assertTrue(os.path.exists(yol))
        md = open(yol, encoding="utf-8").read()
        self.assertLess(md.index(f"## {b} "), md.index(f"## {c} "))
        self.assertLess(md.index(f"## {c} "), md.index(f"## {a} "))
        self.assertNotIn("SAHTEANAHTAR123456789", md)
        self.assertNotIn("SAHTEANAHTAR123456789", r.stdout)
        j = self.cli("teknik", "goster", b, "--json").stdout
        self.assertNotIn("SAHTEANAHTAR123456789", j)
        self.assertNotEqual(self.cli("teknik", "md", "I-999").returncode, 0)


if __name__ == "__main__":
    unittest.main()
