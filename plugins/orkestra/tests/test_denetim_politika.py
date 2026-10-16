"""Denetim politikası (L5) testleri: grup tablosu, karar, örnekleme, geçit, kaydet, CLI."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import denetim_politika as D  # noqa: E402
import ork_lib as L  # noqa: E402

BETIK = os.path.join(KOK, "scripts", "denetim_politika.py")
AYAR = os.path.join(KOK, "ayarlar", "denetim_politikasi.json")
SEMA = ["surum", "mod", "grup_anahtari", "min_ornek", "max_ilk_ret_orani", "tdd_haric", "yuksek_risk_haric",
        "risk_degerleri", "ornekleme_orani", "ornekleme_tuzu", "gecit"]


def kart(i, sinif="kod", basamak="T2", ilk="onay", ek=(), **kw):
    k = {"id": f"G-{i:03d}", "sinif": sinif, "basamak": basamak}
    if ilk is not None:
        k["denetimler"] = [{"karar": ilk}] + [{"karar": x} for x in ek]
    k.update(kw)
    return k


def cfg_ver(**kw):
    c = D.ayar_yukle()
    c.update(kw)
    return c


class K1Ayar(unittest.TestCase):
    def test_dosya_gecerli_ve_tam_mod(self):
        with open(AYAR, encoding="utf-8") as f:
            v = json.load(f)
        self.assertEqual(v["mod"], "tam")
        for a in SEMA:
            self.assertIn(a, v)
        self.assertEqual(v["gecit"], {"min_denetim": 50, "min_kanit_kart": 20})

    def test_proje_ezmesi_ve_bozuk_json(self):
        with tempfile.TemporaryDirectory() as sd:
            yol = os.path.join(sd, "denetim_politikasi.json")
            with open(yol, "w", encoding="utf-8") as f:
                json.dump({"mod": "golge", "min_ornek": 3}, f)
            c = D.ayar_yukle(sd)
            self.assertEqual((c["mod"], c["min_ornek"], c["ornekleme_orani"]), ("golge", 3, 0.2))
            with open(yol, "w", encoding="utf-8") as f:
                f.write("{bozuk")
            self.assertEqual(D.ayar_yukle(sd), D.ayar_yukle())
            self.assertEqual(D.ayar_yukle(sd)["mod"], "tam")


class K2Tablo(unittest.TestCase):
    def test_oran(self):
        ks = [kart(i, ilk="ret" if i < 2 else "onay") for i in range(12)]
        g = D.grup_tablosu(ks, cfg_ver())["kod|T2"]
        self.assertEqual((g["n"], g["ilk_ret"]), (12, 2))
        self.assertAlmostEqual(g["oran"], 0.1667, places=3)

    def test_sonraki_denetimler_etkilemez(self):
        ks = [kart(1, ilk="onay", ek=["ret", "ret"]), kart(2, ilk="ret", ek=["onay"])]
        g = D.grup_tablosu(ks, cfg_ver())["kod|T2"]
        self.assertEqual((g["n"], g["ilk_ret"]), (2, 1))

    def test_kod_duzenleme_ve_denetimsiz(self):
        ks = [kart(1, sinif="kod-duzenleme"), kart(2, sinif="kod"), kart(3, ilk=None), kart(4, sinif="")]
        t = D.grup_tablosu(ks, cfg_ver())
        self.assertEqual(t["kod|T2"]["n"], 2)
        self.assertEqual(t["belirsiz|T2"]["n"], 1)
        self.assertEqual(sum(v["n"] for v in t.values()), 3)


def dusuk_tablo(n=20, ret=0):
    return D.grup_tablosu([kart(i, ilk="ret" if i < ret else "onay") for i in range(n)], cfg_ver())


def atlayan_kart(cfg):
    for i in range(1000, 1500):
        k = kart(i)
        if D._ornekleme_degeri(cfg["ornekleme_tuzu"], k["id"]) >= cfg["ornekleme_orani"]:
            return k
    raise AssertionError("örneklenmeyen kart bulunamadı")


class K3Karar(unittest.TestCase):
    def test_tam(self):
        c = cfg_ver(mod="tam")
        r = D.karar(atlayan_kart(c), dusuk_tablo(), c)
        self.assertEqual((r["karar"], r["neden"], r["uygulanir"]), ("denetle", "politika-tam", False))

    def test_golge_atla_uygulanmaz(self):
        c = cfg_ver(mod="golge")
        r = D.karar(atlayan_kart(c), dusuk_tablo(), c, gecit_acik=True)
        self.assertEqual((r["karar"], r["neden"], r["uygulanir"]), ("atla", "dusuk-risk-grup", False))

    def test_tdd(self):
        c = cfg_ver(mod="golge")
        k = atlayan_kart(c)
        k["tdd"] = True
        self.assertEqual(D.karar(k, dusuk_tablo(), c)["neden"], "tdd")

    def test_yuksek_risk(self):
        c = cfg_ver(mod="golge")
        k = atlayan_kart(c)
        k["risk"] = "yuksek"
        r = D.karar(k, dusuk_tablo(), c)
        self.assertEqual((r["karar"], r["neden"]), ("denetle", "yuksek-risk"))

    def test_yetersiz_veri(self):
        c = cfg_ver(mod="golge")
        r = D.karar(atlayan_kart(c), dusuk_tablo(n=5), c)
        self.assertEqual((r["karar"], r["neden"]), ("denetle", "yetersiz-veri"))

    def test_ret_orani_yuksek(self):
        c = cfg_ver(mod="golge")
        r = D.karar(atlayan_kart(c), dusuk_tablo(n=20, ret=5), c)
        self.assertEqual((r["karar"], r["neden"]), ("denetle", "ret-orani-yuksek"))


class K4Ornekleme(unittest.TestCase):
    def test_deterministik(self):
        c = cfg_ver(mod="golge")
        k, t = kart(7), dusuk_tablo()
        self.assertEqual(len({json.dumps(D.karar(k, t, c), sort_keys=True) for _ in range(5)}), 1)

    def test_oran_yaklasik(self):
        c = cfg_ver(mod="golge")
        t = dusuk_tablo()
        n = sum(D.karar(kart(i), t, c)["orneklenmis"] for i in range(1000))
        self.assertLess(abs(n / 1000 - c["ornekleme_orani"]), 0.05)

    def test_sifir_ve_bir(self):
        t = dusuk_tablo()
        c0 = cfg_ver(mod="golge", ornekleme_orani=0)
        c1 = cfg_ver(mod="golge", ornekleme_orani=1.0)
        self.assertFalse(any(D.karar(kart(i), t, c0)["orneklenmis"] for i in range(200)))
        r = [D.karar(kart(i), t, c1) for i in range(200)]
        self.assertTrue(all(x["orneklenmis"] and x["neden"] == "ornekleme" for x in r))


def gecitli(denetim, kanit):
    ks = []
    for i in range(denetim):
        k = kart(i)
        if i < kanit:
            k["is_turlari"] = [{"kapi": {"kanit": {"gecti": True}}}]
        ks.append(k)
    return ks


class K5Gecit(unittest.TestCase):
    def test_kapali_eksik_dolu(self):
        r = D.gecit_kontrol(gecitli(10, 2), cfg_ver())
        self.assertFalse(r["acik"])
        self.assertEqual((r["denetim"], r["kanit_kart"]), (10, 2))
        self.assertEqual(len(r["eksik"]), 2)

    def test_acik(self):
        r = D.gecit_kontrol(gecitli(60, 25), cfg_ver())
        self.assertTrue(r["acik"])
        self.assertEqual(r["eksik"], [])

    def test_etkin_gecit_kapaliyken_uygulanmaz(self):
        c = cfg_ver(mod="etkin")
        k, t = atlayan_kart(c), dusuk_tablo()
        kapali = D.gecit_kontrol(gecitli(10, 2), c)["acik"]
        r = D.karar(k, t, c, kapali)
        self.assertEqual((r["karar"], r["uygulanir"]), ("atla", False))
        acik = D.gecit_kontrol(gecitli(60, 25), c)["acik"]
        self.assertTrue(D.karar(k, t, c, acik)["uygulanir"])


class K6Kaydet(unittest.TestCase):
    def test_iki_cagri_iki_kayit(self):
        with tempfile.TemporaryDirectory() as sd:
            L.kart_yaz(sd, {"id": "G-001", "baslik": "x"})
            s = {"karar": "denetle", "neden": "politika-tam", "orneklenmis": False, "grup": "kod|T2",
                 "uygulanir": False}
            self.assertTrue(D.kaydet(sd, "G-001", s, "tam"))
            self.assertTrue(D.kaydet(sd, "G-001", s, "tam"))
            kk = L.kart_oku(sd, "G-001")["politika_kararlari"]
            self.assertEqual(len(kk), 2)
            for a in ("zaman", "karar", "neden", "orneklenmis", "mod", "uygulanir", "grup"):
                self.assertIn(a, kk[0])

    def test_kart_yok_ve_kilit_hatasi(self):
        with tempfile.TemporaryDirectory() as sd:
            self.assertFalse(D.kaydet(sd, "G-404", {"karar": "denetle"}))
            L.kart_yaz(sd, {"id": "G-001"})
            with mock.patch.object(L, "kilit", side_effect=OSError("kilit")):
                self.assertFalse(D.kaydet(sd, "G-001", {"karar": "denetle"}))


def ozet(dizin):
    o = {}
    for kok, _, dosyalar in os.walk(dizin):
        for d in dosyalar:
            y = os.path.join(kok, d)
            o[y] = (os.path.getsize(y), os.path.getmtime(y))
    return o


class K7Cli(unittest.TestCase):
    def kos(self, *args):
        return subprocess.run([sys.executable, BETIK, *args], capture_output=True, text=True,
                              encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"))

    def test_tablo_json_dosya_yazmaz_ve_karar_kaydet(self):
        with tempfile.TemporaryDirectory() as sd:
            for i in range(12):
                L.kart_yaz(sd, kart(i + 1, ilk="onay"))
            once = ozet(sd)
            p = self.kos("tablo", "--json", "--sd", sd)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)["kod|T2"]["n"], 12)
            self.assertEqual(ozet(sd), once)
            self.assertEqual(self.kos("tablo", "--sd", sd).returncode, 0)
            self.assertEqual(ozet(sd), once)
            g = self.kos("gecit", "--sd", sd)
            self.assertFalse(json.loads(g.stdout)["acik"])
            self.assertEqual(ozet(sd), once)
            p = self.kos("karar", "G-001", "--sd", sd, "--kaydet")
            self.assertEqual(p.returncode, 0, p.stderr)
            r = json.loads(p.stdout)
            self.assertEqual(r["neden"], "politika-tam")
            self.assertTrue(r["kaydedildi"])
            self.assertEqual(len(L.kart_oku(sd, "G-001")["politika_kararlari"]), 1)


if __name__ == "__main__":
    unittest.main()
