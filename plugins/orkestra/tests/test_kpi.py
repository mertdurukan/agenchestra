"""G-025: scripts/kpi.py `olcum(sd)` ve `orkestra kpi [--json] [--gun N]` (salt okuma KPI ölçümü).

Sözleşme (testin tanımladığı çıktı şeması):
  olcum(sd) -> {
    "tanimlar":      {kpi: {"pay": str, "payda": str}}            # 8 KPI + onkontrol_ret_orani
    "genel":         {kpi: değer}                                  # onay_bekleme_sn = {"medyan":.., "p95":..}
    "ana_ajan_payi": {"maliyet_usd": .., "token": ..}              # gorev='-' satırları, kartlara dağıtılmaz
    "sinif":         {sinif: {kpi: değer}}                         # onay_bekleme_sn hariç
    "basamak":       {son_basamak: {kpi: değer}}                   # onay_bekleme_sn hariç
  }
Kurallar: iptal kartı hiçbir paydaya/paya girmez; pay ya da payda 0 ise değer None; p95 = en yakın sıra
(nearest-rank: sıralı listede ceil(0.95*n). eleman); medyan çift sayıda ortadaki ikinin ortalaması; maliyet
satırları ork_lib.maliyet_kayitlari ile tekilleştirilir; genel onbellek_isabet ana ajan satırlarını da kapsar;
onkontrol: kartın "onkontrol_kosulari": [{"gecti": bool}] alanı (yoksa katkı yok);
kırılımda sinif = kart["sinif"], basamak = kart["basamak"] (son basamak, baslangic_basamak değil).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, SCRIPTS)

KPILER = ["dogrulanmis_basari", "basari_basina_maliyet", "basari_basina_token", "onbellek_isabet",
          "ret_orani", "onkontrol_ret_orani", "yeniden_deneme_carpani", "p95_sure_sn"]
GUNLUK = "2026-03-10"


def z(sa, dk=0, sn=0):
    return f"{GUNLUK}T{sa:02d}:{dk:02d}:{sn:02d}+03:00"


def denetim(*kararlar):
    return [{"zaman": z(23), "sira": i + 1, "karar": k, "ajan": "orkestra:denetci"} for i, k in enumerate(kararlar)]


def kart(gid, sinif, basamak, durum, olusturma, olaylar, isci_sayisi, kararlar, baslangic=None):
    gecmis = [{"zaman": olusturma, "olay": "olusturuldu", "basamak": baslangic or basamak}]
    gecmis += [{"zaman": t, "olay": o} for t, o in olaylar]
    return {"id": gid, "baslik": "x", "sinif": sinif, "basamak": basamak, "baslangic_basamak": baslangic or basamak,
            "durum": durum, "olusturma": olusturma, "gecmis": gecmis,
            "isciler": [f"{gid}-i{i}" for i in range(isci_sayisi)], "denetimler": denetim(*kararlar)}


def mal(gorev, agent_id, giris, cikis, okuma, yazma, usd, kaynak="tur", zaman="2026-03-10T09:00:00+03:00",
        oturum="o1"):
    return {"zaman": zaman, "oturum": oturum, "gorev": gorev, "agent_id": agent_id, "model": "claude-sonnet-5-5",
            "giris": giris, "cikis": cikis, "onbellek_okuma": okuma, "onbellek_yazma": yazma,
            "maliyet_usd": usd, "kaynak": kaynak, "tarife": "1sa"}


KARTLAR = [
    kart("G-001", "kod", "T2", "teslim", z(10), [(z(10, 10), "teslim")], 2, ["ret", "onay"]),
    kart("G-002", "kod", "T3", "onaylandi", z(11), [(z(11, 20), "onaylandi")], 1, ["ret", "onay"], baslangic="T2"),
    kart("G-003", "arastirma", "T1", "teslim", z(12), [(z(12, 1, 40), "teslim")], 1, ["ret", "onay"]),
    kart("G-004", "kod", "T2", "reddedildi", z(13), [], 3, ["ret", "ret"]),
    kart("G-005", "kod", "T2", "iptal", z(14), [(z(14, 5), "iptal")], 4, []),
]

MALIYET = [
    # G-001: a1 birikimli hook satırları -> yalnız sonuncusu; a2 'tur' + atılması gereken hook kopyası
    mal("G-001", "a1", 10, 20, 100, 50, 0.10, "hook", "2026-03-10T10:01:00+03:00"),
    mal("G-001", "a1", 20, 40, 200, 100, 0.20, "hook", "2026-03-10T10:05:00+03:00"),
    mal("G-001", "a2", 5, 10, 0, 0, 0.05, "tur"),
    mal("G-001", "a2", 5, 10, 0, 0, 9.90, "hook", "2026-03-10T10:06:00+03:00"),
    mal("G-002", "a3", 10, 30, 300, 0, 0.40),
    mal("G-003", "a4", 20, 10, 50, 70, 0.15),
    mal("G-004", "a5", 100, 100, 0, 0, 1.00),
    # ana ajan: kartlara dağıtılmaz
    mal("-", None, 40, 60, 400, 100, 2.00, "hook"),
]

ONAYLAR = [  # (olusturma, karar zamanı | None)
    (z(8), z(8, 0, 10)), (z(8, 5), z(8, 5, 30)), (z(8, 10), z(8, 11)), (z(8, 20), z(8, 21, 40)), (z(8, 30), None),
]


def yaz_json(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)


def durum_kur(sd, kartlar=KARTLAR, maliyet=MALIYET, onaylar=ONAYLAR, kontroller=None):
    if kontroller is None:
        kontroller = {"G-001": [False, True], "G-004": [True]}
    os.makedirs(os.path.join(sd, "gorevler"), exist_ok=True)
    os.makedirs(os.path.join(sd, "onaylar"), exist_ok=True)
    for k in kartlar:
        if k["id"] in kontroller:   # ön kontrol koşuları kartın kendisinde tutulur (on_kontrol._kosu_kaydet)
            k = dict(k, onkontrol_kosulari=[{"gecti": g} for g in kontroller[k["id"]]])
        yaz_json(os.path.join(sd, "gorevler", k["id"] + ".json"), k)
        yaz_json(os.path.join(sd, "gorevler", k["id"] + ".denetim.json"), k["denetimler"])
        if k["id"] in kontroller:
            yaz_json(os.path.join(sd, "gorevler", k["id"] + ".onkontrol.json"), {"zaman": z(9), "dosyalar": {}})
    # yalnız taban içeren onkontrol dosyası ret saymamalı
    if any(k["id"] == "G-002" for k in kartlar):
        yaz_json(os.path.join(sd, "gorevler", "G-002.onkontrol.json"), {"zaman": z(9), "dosyalar": {}})
    with open(os.path.join(sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
        for r in maliyet:
            f.write(json.dumps(r) + "\n")
    for i, (ol, karar) in enumerate(onaylar, 1):
        o = {"id": f"O-{i:03d}", "olusturma": ol, "durum": "onaylandi" if karar else "bekliyor",
             "karar": {"sonuc": "onay", "zaman": karar} if karar else None}
        yaz_json(os.path.join(sd, "onaylar", f"O-{i:03d}.json"), o)


def olcum(sd):
    import kpi
    return kpi.olcum(sd)


def cli(proje, *args, cwd=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=proje, PYTHONUTF8="1")
    return ic_kos.kos([ORKESTRA, "kpi", *args], env=env, cwd=cwd or proje)


def agac_goruntusu(kok):
    out = {}
    for d, _, dosyalar in os.walk(kok):
        for f in dosyalar:
            p = os.path.join(d, f)
            out[os.path.relpath(p, kok)] = (os.stat(p).st_mtime_ns, os.path.getsize(p))
    return out


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = self.t.name
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)

    def tearDown(self):
        self.t.cleanup()


class SekizKpiElleHesap(Temel):
    """K1: fixture + elle hesaplanmış beklenen değerler."""

    def setUp(self):
        super().setUp()
        durum_kur(self.sd)
        self.s = olcum(self.sd)
        self.g = self.s["genel"]

    def test_tanimlar_pay_ve_payda_yazili(self):
        for kpi in KPILER:
            with self.subTest(kpi=kpi):
                t = self.s["tanimlar"][kpi]
                self.assertTrue(t["pay"].strip())
                self.assertTrue(t["payda"].strip())
        self.assertIn("onay_bekleme_sn", self.s["tanimlar"])

    def test_1_dogrulanmis_basari(self):
        # onaylı G-001,002,003 / (5 kart - 1 iptal) = 3/4
        self.assertAlmostEqual(self.g["dogrulanmis_basari"], 0.75, places=4)

    def test_2_basari_basina_maliyet_ana_ajan_haric(self):
        # (0.25 + 0.40 + 0.15) / 3; G-001'de a1 yalnız son hook satırı (0.20) + a2 tur (0.05)
        self.assertAlmostEqual(self.g["basari_basina_maliyet"], 0.80 / 3, places=4)

    def test_3_basari_basina_token(self):
        # G-001: 25+50+200+100=375, G-002: 340, G-003: 150 -> 865/3
        self.assertAlmostEqual(self.g["basari_basina_token"], 865 / 3, places=3)

    def test_4_onbellek_isabet_genel(self):
        # giris 195 (25+10+20+100+40), okuma 950 (200+300+50+0+400), yazma 270 -> 950/1415
        self.assertAlmostEqual(self.g["onbellek_isabet"], 950 / 1415, places=4)

    def test_5_ret_orani_ve_onkontrol_ayri(self):
        # denetimler: 2+2+2+2=8, ret 1+1+1+2=5
        self.assertAlmostEqual(self.g["ret_orani"], 5 / 8, places=4)
        # ön kontrol: G-001 [ret, geçti], G-004 [geçti] -> 1/3; taban-yalnız dosya katkısız
        self.assertAlmostEqual(self.g["onkontrol_ret_orani"], 1 / 3, places=4)

    def test_6_yeniden_deneme_carpani(self):
        # işçi çağrısı 2+1+1+3 = 7 (iptal G-005'in 4'ü hariç) / 4 kart
        self.assertAlmostEqual(self.g["yeniden_deneme_carpani"], 1.75, places=4)

    def test_7_p95_sure_sn(self):
        # tamamlananlar: 600 (teslim), 1200 (onay; teslim yok), 100 -> nearest-rank ceil(2.85)=3 -> 1200
        self.assertAlmostEqual(self.g["p95_sure_sn"], 1200, places=3)

    def test_8_onay_bekleme_medyan_ve_p95(self):
        # karar verilmiş: 10, 30, 60, 100 sn (karar'sız bekleyen hariç) -> medyan 45, p95 nearest-rank = 100
        self.assertAlmostEqual(self.g["onay_bekleme_sn"]["medyan"], 45, places=3)
        self.assertAlmostEqual(self.g["onay_bekleme_sn"]["p95"], 100, places=3)

    def test_olcum_saf_json_donusturulebilir(self):
        json.dumps(self.s)


class IptalVeAnaAjan(Temel):
    """K2."""

    def test_iptal_karti_paydaya_girmez(self):
        durum_kur(self.sd)
        g = olcum(self.sd)["genel"]
        self.assertNotAlmostEqual(g["dogrulanmis_basari"], 3 / 5, places=3)  # iptal dahil olsaydı 0.6
        self.assertAlmostEqual(g["dogrulanmis_basari"], 0.75, places=4)
        self.assertNotAlmostEqual(g["yeniden_deneme_carpani"], 11 / 5, places=3)
        self.assertAlmostEqual(g["yeniden_deneme_carpani"], 1.75, places=4)

    def test_ana_ajan_ayri_satir_ve_kartlara_dagitilmaz(self):
        durum_kur(self.sd)
        s = olcum(self.sd)
        self.assertAlmostEqual(s["ana_ajan_payi"]["maliyet_usd"], 2.00, places=4)
        self.assertEqual(s["ana_ajan_payi"]["token"], 600)
        # ana ajan 2.00 USD kart başına maliyete eklenseydi (2.80/3) olurdu
        self.assertAlmostEqual(s["genel"]["basari_basina_maliyet"], 0.80 / 3, places=4)
        self.assertLess(s["genel"]["basari_basina_maliyet"], 0.5)

    def test_ana_ajan_maliyeti_sinif_ve_basamak_kirilimina_girmez(self):
        durum_kur(self.sd)
        s = olcum(self.sd)
        self.assertAlmostEqual(s["sinif"]["kod"]["basari_basina_maliyet"], 0.65 / 2, places=4)
        self.assertAlmostEqual(s["basamak"]["T2"]["basari_basina_maliyet"], 0.25, places=4)

    def test_yalniz_iptal_karti_olan_durum(self):
        durum_kur(self.sd, kartlar=[KARTLAR[4]], maliyet=[], onaylar=[], kontroller={})
        g = olcum(self.sd)["genel"]
        self.assertIsNone(g["dogrulanmis_basari"])
        self.assertIsNone(g["yeniden_deneme_carpani"])


class SifirPayPayda(Temel):
    """K3: istisna yok, değer None."""

    def test_bos_durum_klasoru(self):
        durum_kur(self.sd, kartlar=[], maliyet=[], onaylar=[], kontroller={})
        s = olcum(self.sd)
        for kpi in KPILER:
            with self.subTest(kpi=kpi):
                self.assertIsNone(s["genel"][kpi])
        self.assertEqual(s["genel"]["onay_bekleme_sn"], {"medyan": None, "p95": None})
        self.assertEqual(s["sinif"], {})
        self.assertEqual(s["basamak"], {})
        self.assertIn(s["ana_ajan_payi"]["maliyet_usd"], (0, 0.0, None))

    def test_dosyasiz_durum_klasoru_bile_cokmez(self):
        s = olcum(self.sd)  # gorevler/, onaylar/, maliyet.jsonl hiç yok
        self.assertIsNone(s["genel"]["dogrulanmis_basari"])

    def test_onayli_kart_var_ama_maliyet_denetim_olay_yok(self):
        k = kart("G-001", "kod", "T2", "onaylandi", z(10), [], 0, [])
        durum_kur(self.sd, kartlar=[k], maliyet=[], onaylar=[], kontroller={})
        g = olcum(self.sd)["genel"]
        self.assertAlmostEqual(g["dogrulanmis_basari"], 1.0)
        for kpi in ("basari_basina_maliyet", "basari_basina_token", "onbellek_isabet", "ret_orani",
                    "onkontrol_ret_orani", "yeniden_deneme_carpani", "p95_sure_sn"):
            with self.subTest(kpi=kpi):
                self.assertIsNone(g[kpi])

    def test_pay_sifir_payda_dolu_null(self):
        # hiç ret yok: pay 0 -> null (spec: pay ya da payda 0 ise null)
        k = kart("G-001", "kod", "T2", "teslim", z(10), [(z(10, 5), "teslim")], 1, ["onay"])
        durum_kur(self.sd, kartlar=[k], maliyet=[mal("G-001", "a1", 1, 1, 1, 1, 0.1)], onaylar=[], kontroller={})
        g = olcum(self.sd)["genel"]
        self.assertIsNone(g["ret_orani"])
        self.assertAlmostEqual(g["basari_basina_maliyet"], 0.1)

    def test_onay_olmadan_bekleme_none(self):
        durum_kur(self.sd, onaylar=[(z(8), None)])
        self.assertEqual(olcum(self.sd)["genel"]["onay_bekleme_sn"], {"medyan": None, "p95": None})


class Kirilimlar(Temel):
    """K4: sinif ve basamak kırılımları (olcum + --json)."""

    def setUp(self):
        super().setUp()
        durum_kur(self.sd)

    def kontrol_sinif_basamak(self, s):
        kod, ar = s["sinif"]["kod"], s["sinif"]["arastirma"]
        self.assertAlmostEqual(kod["dogrulanmis_basari"], 2 / 3, places=4)
        self.assertAlmostEqual(kod["basari_basina_maliyet"], 0.325, places=4)
        self.assertAlmostEqual(kod["basari_basina_token"], 357.5, places=3)
        self.assertAlmostEqual(kod["onbellek_isabet"], 500 / 735, places=4)
        self.assertAlmostEqual(kod["ret_orani"], 4 / 6, places=4)
        self.assertAlmostEqual(kod["onkontrol_ret_orani"], 1 / 3, places=4)
        self.assertAlmostEqual(kod["yeniden_deneme_carpani"], 2.0, places=4)
        self.assertAlmostEqual(kod["p95_sure_sn"], 1200, places=3)
        self.assertAlmostEqual(ar["dogrulanmis_basari"], 1.0, places=4)
        self.assertAlmostEqual(ar["basari_basina_maliyet"], 0.15, places=4)
        self.assertAlmostEqual(ar["basari_basina_token"], 150, places=3)
        self.assertAlmostEqual(ar["onbellek_isabet"], 50 / 140, places=4)
        self.assertAlmostEqual(ar["ret_orani"], 0.5, places=4)
        self.assertIsNone(ar["onkontrol_ret_orani"])
        self.assertAlmostEqual(ar["p95_sure_sn"], 100, places=3)
        t1, t2, t3 = s["basamak"]["T1"], s["basamak"]["T2"], s["basamak"]["T3"]
        # son basamak: G-002 baslangıç T2 ama T3'e yükselmiş -> T3'te sayılır
        self.assertAlmostEqual(t2["dogrulanmis_basari"], 0.5, places=4)  # G-001 onaylı / (G-001,G-004); iptal hariç
        self.assertAlmostEqual(t2["basari_basina_maliyet"], 0.25, places=4)
        self.assertAlmostEqual(t2["basari_basina_token"], 375, places=3)
        self.assertAlmostEqual(t2["onbellek_isabet"], 200 / 425, places=4)
        self.assertAlmostEqual(t2["ret_orani"], 0.75, places=4)
        self.assertAlmostEqual(t2["yeniden_deneme_carpani"], 2.5, places=4)
        self.assertAlmostEqual(t2["p95_sure_sn"], 600, places=3)
        self.assertAlmostEqual(t3["dogrulanmis_basari"], 1.0, places=4)
        self.assertAlmostEqual(t3["basari_basina_token"], 340, places=3)
        self.assertAlmostEqual(t3["onbellek_isabet"], 300 / 310, places=4)
        self.assertAlmostEqual(t3["p95_sure_sn"], 1200, places=3)
        self.assertAlmostEqual(t1["basari_basina_maliyet"], 0.15, places=4)
        for grup in (s["sinif"], s["basamak"]):
            for ad, v in grup.items():
                with self.subTest(grup=ad):
                    for kpi in KPILER:
                        self.assertIn(kpi, v)

    def test_olcum_kirilimlari(self):
        self.kontrol_sinif_basamak(olcum(self.sd))

    def test_json_ciktisinda_kirilimlar(self):
        r = cli(self.proje, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = json.loads(r.stdout)
        self.assertEqual(set(s["sinif"]), {"kod", "arastirma"})
        self.assertEqual(set(s["basamak"]), {"T1", "T2", "T3"})
        self.assertIn("tanimlar", s)
        self.kontrol_sinif_basamak(s)
        self.assertAlmostEqual(s["genel"]["dogrulanmis_basari"], 0.75, places=4)

    def test_json_gun_suzmesi(self):
        # tüm fixture 2026-03-10: çok geniş pencere hepsini tutar, 1 gün (bugün) hiçbirini tutmaz
        genis = json.loads(cli(self.proje, "--json", "--gun", "100000").stdout)
        self.assertAlmostEqual(genis["genel"]["dogrulanmis_basari"], 0.75, places=4)
        dar = cli(self.proje, "--json", "--gun", "1")
        self.assertEqual(dar.returncode, 0, dar.stderr)
        self.assertIsNone(json.loads(dar.stdout)["genel"]["dogrulanmis_basari"])

    def test_varsayilan_cikti_okunur_tablo(self):
        r = cli(self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        with self.assertRaises(ValueError):
            json.loads(r.stdout)
        for ad in ("dogrulanmis_basari", "ret_orani", "p95_sure_sn", "kod", "T2"):
            self.assertIn(ad, r.stdout)

    def test_gecersiz_gun_hata_kodu(self):
        self.assertNotEqual(cli(self.proje, "--json", "--gun", "abc").returncode, 0)

    def test_cikti_sir_ve_istem_metni_icermez(self):
        k = dict(KARTLAR[0], baslik="GIZLI-BASLIK-METNI", girdi="GIZLI-ISTEM-METNI")
        durum_kur(self.sd, kartlar=[k] + KARTLAR[1:])
        r = cli(self.proje, "--json")
        self.assertNotIn("GIZLI-ISTEM-METNI", r.stdout)
        self.assertNotIn("GIZLI-BASLIK-METNI", r.stdout)


class SalitOkuma(Temel):
    """K5."""

    def test_olcum_ve_cli_fixture_uzerinde_dosya_yazmaz(self):
        durum_kur(self.sd)
        once = agac_goruntusu(self.proje)
        olcum(self.sd)
        r = cli(self.proje, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        json.loads(r.stdout)
        cli(self.proje)
        self.assertEqual(agac_goruntusu(self.proje), once)

    def test_gercek_durum_klasorunde_gecerli_json_ve_yazma_yok(self):
        # geçici proje + gerçekçi durum klasörü (makineye bağlı yol yok, skip yok)
        gercek = self.proje
        sd = self.sd
        durum_kur(sd)
        # canlı yazılan dosyalar (defter, maliyet, oturum, kilitler, etkin kart) karşılaştırma dışı
        def canli(rel):
            r = rel.replace("\\", "/")
            return (r in ("maliyet.jsonl", "ortak_defter.md") or r.startswith(("oturumlar/", "raporlar/"))
                    or r.endswith(".lock") or r.startswith("gorevler/G-025") or r.endswith(".tmp"))
        once = {k: v for k, v in agac_goruntusu(sd).items() if not canli(k)}
        r = cli(gercek, "--json", cwd=gercek)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = json.loads(r.stdout)
        for anahtar in ("tanimlar", "genel", "ana_ajan_payi", "sinif", "basamak"):
            self.assertIn(anahtar, s)
        sonra = {k: v for k, v in agac_goruntusu(sd).items() if not canli(k)}
        self.assertEqual(sonra, once, "kpi komutu durum klasöründe dosya yazdı/değiştirdi")


if __name__ == "__main__":
    unittest.main()
