"""kanit_kapisi.py testleri (K-001/K-002 kayıtlı ön kontroller). Geçici dizinde; ağ/model yok."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import kanit_kapisi as KK  # noqa: E402


def kart(n=3, **ek):
    d = {"kabul_kriterleri": ["K%d: kriter" % i for i in range(1, n + 1)], "sinif": "kod"}
    d.update(ek)
    return d


class Taban(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sd = os.path.join(self.tmp.name, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "kurallar"))
        self.cfg = KK.ayar_yukle()["kontroller"]

    def tearDown(self):
        self.tmp.cleanup()

    def yaz(self, yol, metin):
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)

    def kural(self, durum, kontrol, kid="K-001"):
        self.yaz(os.path.join(self.sd, "kurallar", "kurallar.json"),
                 json.dumps({"kurallar": [{"id": kid, "durum": durum, "kontrol": kontrol}]}))


class Ayar(Taban):
    def test_k1_varsayilan(self):
        a = KK.ayar_yukle()
        for kim, mod in (("kanit-satiri", "ihlal"), ("sayi-tutarli", "golge")):  # ADR-0082
            c = a["kontroller"][kim]
            self.assertEqual(c["mod"], mod)
            self.assertFalse(c["her_zaman"])
            self.assertTrue(c["neden_kodlari"])
        self.assertEqual(KK.neden_kontrol("sayi-tutarsiz"), "sayi-tutarli")
        self.assertIsNone(KK.neden_kontrol("yok"))

    def test_k2_ezme(self):
        self.yaz(os.path.join(self.sd, "on_kontrol.json"),
                 json.dumps({"kontroller": {"kanit-satiri": {"mod": "ihlal"}}}))
        a = KK.ayar_yukle(self.sd)["kontroller"]
        v = KK.ayar_yukle()["kontroller"]
        self.assertEqual(a["kanit-satiri"]["mod"], "ihlal")
        self.assertEqual(a["kanit-satiri"]["satir_kalibi"], v["kanit-satiri"]["satir_kalibi"])
        self.assertEqual(a["sayi-tutarli"], v["sayi-tutarli"])

    def test_k2_bozuk(self):
        self.yaz(os.path.join(self.sd, "on_kontrol.json"), "{bozuk")
        self.assertEqual(KK.ayar_yukle(self.sd), KK.ayar_yukle())


class Etkin(Taban):
    def test_etkin_kural(self):
        self.kural("etkin", "kanit-satiri")
        e = KK.etkin_kontroller(self.sd)
        self.assertEqual(e, {"kanit-satiri": {"mod": "ihlal", "kaynak": "kural K-001"}})

    def test_etkin_degil(self):
        for d in ("oneri", "kaldirildi", "reddedildi"):
            self.kural(d, "kanit-satiri")
            self.assertEqual(KK.etkin_kontroller(self.sd), {})

    def test_her_zaman(self):
        self.yaz(os.path.join(self.sd, "on_kontrol.json"),
                 json.dumps({"kontroller": {"sayi-tutarli": {"her_zaman": True}}}))
        self.assertEqual(KK.etkin_kontroller(self.sd)["sayi-tutarli"]["kaynak"], "her_zaman")

    def test_bilinmeyen_ve_dosya_yok(self):
        self.kural("etkin", "yok-kontrol")
        self.assertEqual(KK.etkin_kontroller(self.sd), {})
        os.remove(os.path.join(self.sd, "kurallar", "kurallar.json"))
        self.assertEqual(KK.etkin_kontroller(self.sd), {})


class Kanit(Taban):
    def k(self, kt, ozet, kan=""):
        return KK.kanit_kontrol(kt, ozet, kan, self.cfg["kanit-satiri"])

    def test_gecti(self):
        r = self.k(kart(), "K1: dosya:12 kanıtı\nK2: komut çıktısı 5\n- K3: sayı 42 doğrulandı")
        self.assertTrue(r["gecti"])
        self.assertEqual(r["n"], 3)

    def test_eksik(self):
        r = self.k(kart(), "K1: dosya:12 kanıtı\nK3: sayı 42 doğrulandı")
        self.assertEqual(r["eksik"], ["K2"])
        self.assertFalse(r["gecti"])

    def test_kisa(self):
        r = self.k(kart(), "K1: ok\nK2: komut çıktısı 5\nK3: sayı 42 doğrulandı")
        self.assertEqual(r["kisa"], ["K1"])
        self.assertEqual(r["eksik"], [])

    def test_kismen(self):
        self.assertTrue(self.k(kart(1), "K1: KISMEN")["gecti"])

    def test_metin_ici_sayilmaz(self):
        r = self.k(kart(2), "K1: dosya:12 kanıtı\nayrıntı için bkz K2: uzun açıklama burada")
        self.assertEqual(r["eksik"], ["K2"])

    def test_kriter_etiketi(self):
        kt = {"kabul_kriterleri": ["K5: bir şey", "başka bir şey"], "sinif": "kod"}
        r = self.k(kt, "K5: dosya:1 kanıt var\nK2: ikinci kriter kanıtı")
        self.assertTrue(r["gecti"])
        r = self.k(kt, "K5: dosya:1 kanıt var")
        self.assertEqual(r["eksik"], ["K2"])

    def test_sifir_kriter(self):
        r = self.k({"kabul_kriterleri": [], "sinif": "kod"}, "")
        self.assertTrue(r["gecti"])
        self.assertEqual(r["n"], 0)


class Sayi(Taban):
    def md(self, ad, metin):
        y = os.path.join(self.tmp.name, ad)
        self.yaz(y, metin)
        return y

    def calis(self, yollar):
        return KK.sayi_tutarlilik(yollar, self.tmp.name, self.cfg["sayi-tutarli"])

    def test_tutarsiz(self):
        r = self.calis([self.md("a.md", "Toplam kart: 12\n\nsonra\nToplam kart: 14\n")])
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["degerler"], ["12", "14"])

    def test_tutarli(self):
        self.assertEqual(self.calis([self.md("a.md", "12 kart işlendi\nToplam kart: 12\n")]), [])

    def test_kod_citi(self):
        self.assertEqual(self.calis([self.md("a.md", "Toplam kart: 12\n```\nToplam kart: 14\n```\n")]), [])

    def test_haric_yollar_yonerge_belgesi(self):
        # gölge koşusunda 3 yanlış pozitif: KURALLAR.md / agents/*.md içindeki "madde 3", "madde 5" atıfları
        icerik = "3 madde\n5 madde\n"
        self.assertEqual(self.calis([self.md("a.md", icerik)])[0]["degerler"], ["3", "5"])
        os.makedirs(os.path.join(self.tmp.name, "agents"))
        self.assertEqual(self.calis([self.md("KURALLAR.md", icerik)]), [])
        self.assertEqual(self.calis([self.md(os.path.join("agents", "x.md"), icerik)]), [])

    def test_uzanti_ve_boyut(self):
        icerik = "Toplam kart: 12\nToplam kart: 14\n"
        self.assertEqual(self.calis([self.md("a.txt", icerik)]), [])
        cfg = dict(self.cfg["sayi-tutarli"], azami_bayt=10)
        self.assertEqual(KK.sayi_tutarlilik([self.md("b.md", icerik)], self.tmp.name, cfg), [])


class Kapi(Taban):
    def test_golge(self):
        self.kural("etkin", "kanit-satiri")
        self.yaz(os.path.join(self.sd, "on_kontrol.json"),
                 json.dumps({"kontroller": {"kanit-satiri": {"mod": "golge"}}}))
        r = KK.kapi(self.sd, self.tmp.name, kart(2), "K1: yeterli kanıt var", [], [])
        self.assertFalse(r["ihlal"])
        self.assertTrue(r["mesajlar"][0].startswith("UYARI (gölge)"))
        self.assertEqual(r["kayit"]["kanit"], "eksik:K2")
        self.assertEqual(r["kayit"]["kanit_mod"], "golge")

    def test_ihlal(self):
        self.kural("etkin", "kanit-satiri")
        r = KK.kapi(self.sd, self.tmp.name, kart(2), "K1: yeterli kanıt var", [], [])
        self.assertTrue(r["ihlal"])
        self.assertIn("K2", r["mesajlar"][0])
        self.assertIn('--kanit "K2: ', r["mesajlar"][0])

    def test_ihlal_sayi_tutarsiz_rapor(self):
        # ihlal modunda tutarsız sayılı rapor kapıyı kapatır (varsayılan sayı kontrolü gölgede, ADR-0082)
        self.kural("etkin", "sayi-tutarli")
        self.yaz(os.path.join(self.sd, "on_kontrol.json"),
                 json.dumps({"kontroller": {"sayi-tutarli": {"mod": "ihlal"}}}))
        y = os.path.join(self.tmp.name, "rapor.md")
        self.yaz(y, "Toplam kart: 12\n\nToplam kart: 14\n")
        r = KK.kapi(self.sd, self.tmp.name, kart(1), "K1: yeterli kanıt var", [], [y])
        self.assertTrue(r["ihlal"])
        self.assertIn("rapor.md kart=12/14", r["mesajlar"][0])
        self.assertFalse(r["mesajlar"][0].startswith("UYARI (gölge)"))
        self.yaz(y, "Toplam kart: 12\n\nToplam kart: 12\n")
        self.assertFalse(KK.kapi(self.sd, self.tmp.name, kart(1), "K1: yeterli kanıt var", [], [y])["ihlal"])

    def test_etkin_degil(self):
        r = KK.kapi(self.sd, self.tmp.name, kart(2), "", [], [])
        self.assertEqual(r["sonuclar"], {})
        self.assertFalse(r["ihlal"])

    def test_bozuk_kart(self):
        self.kural("etkin", "kanit-satiri")
        r = KK.kapi(self.sd, self.tmp.name, {"kabul_kriterleri": 5}, "x", [], [])
        self.assertFalse(r["ihlal"])
        self.assertTrue(r["kayit"]["hata"])


class Cli(Taban):
    def durum(self):
        p = subprocess.run([sys.executable, os.path.join(KOK, "scripts", "kanit_kapisi.py"), "durum", "--sd", self.sd],
                           capture_output=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_durum(self):
        d = self.durum()
        self.assertFalse(d["kanit-satiri"]["etkin"])
        self.assertFalse(d["sayi-tutarli"]["etkin"])
        self.kural("etkin", "sayi-tutarli", "K-002")
        d = self.durum()
        self.assertTrue(d["sayi-tutarli"]["etkin"])
        self.assertEqual(d["sayi-tutarli"]["kaynak"], "kural K-002")
        self.assertFalse(d["kanit-satiri"]["etkin"])


if __name__ == "__main__":
    unittest.main()
