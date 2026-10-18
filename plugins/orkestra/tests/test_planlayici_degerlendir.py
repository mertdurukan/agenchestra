"""040 P7: planlayıcı tablosunun haftalık değerlendirmesi — eşik aşımı onay önerisi açar, model sürümü değişince dönem sıfırlanır."""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402
import planlayici_degerlendir as PD  # noqa: E402

CLI = os.path.join(KOK, "scripts", "orkestra.py")
SIMDI = datetime.datetime(2026, 10, 18, 12, 0).astimezone()


def kart(i, plan, ilk_onay, gun_once=1):
    olus = (SIMDI - datetime.timedelta(days=gun_once)).isoformat(timespec="seconds")
    return {"id": f"G-{i:03d}", "durum": "onaylandi", "sinif": "kod", "basamak": "T2", "plan_modeli": plan, "olusturma": olus,
            "denetimler": [{"sira": 1, "karar": "onay" if ilk_onay else "ret", "zaman": olus}]}


def grup(plan, n, onay_sayisi, baslangic=0, gun_once=1):
    return [kart(baslangic + i, plan, i < onay_sayisi, gun_once) for i in range(n)]


class PlanlayiciDegerlendir(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_pld_")
        self.addCleanup(shutil.rmtree, self.sd, ignore_errors=True)

    def deger(self, kartlar, **kw):
        return PD.degerlendir(self.sd, simdi=SIMDI, kartlar=kartlar, kayitlar=[], surum="claude-sonnet-5-5", **kw)

    def donem_ilk(self):
        """İlk koşu dönem başını yazar (sifirlandi); sonraki haftalık koşular bunun üstüne kurulur."""
        self.assertEqual(PD.degerlendir(self.sd, simdi=SIMDI - datetime.timedelta(days=30), kartlar=[], kayitlar=[],
                                        surum="claude-sonnet-5-5")["durum"], "sifirlandi")

    def test_esik_asimi_onay_onerisi_acar_ve_ayni_hafta_tekrar_acmaz(self):
        self.donem_ilk()
        kartlar = grup("sonnet", 20, 14) + grup("opus", 20, 19, baslangic=100)  # ilk geçiş 0,70 / 0,95
        r = self.deger(kartlar)
        self.assertEqual(r["durum"], "degerlendirildi")
        self.assertEqual(len(r["farklar"]), 1)
        self.assertTrue(r["oneri"])
        self.assertEqual(r["oneri"]["anahtar"], "planlayici:claude-sonnet-5-5:2026-W42")
        self.assertEqual(self.deger(kartlar)["durum"], "bekliyor")
        r2 = self.deger(kartlar, zorla=True)  # zorlama aynı anahtarla yeni kayıt açmaz
        self.assertEqual(r2["oneri"]["onay_id"], r["oneri"]["onay_id"])

    def test_fark_esik_altinda_veya_veri_yetersizse_oneri_yok(self):
        self.donem_ilk()
        yakin = grup("sonnet", 20, 15) + grup("opus", 20, 15, baslangic=100)  # ilk geçiş eşit, maliyet/süre verisi yok
        r = self.deger(yakin, zorla=True)
        self.assertEqual(r["farklar"], [])
        self.assertIsNone(r["oneri"])
        kucuk = grup("sonnet", 20, 14) + grup("opus", 5, 5, baslangic=100)  # opus n<20: yetersiz veri
        r = self.deger(kucuk, zorla=True)
        self.assertEqual(r["farklar"], [])
        self.assertIsNone(r["oneri"])

    def test_model_surumu_degisince_donem_sifirlanir_eski_kartlar_sayilmaz(self):
        self.donem_ilk()
        d = PD._oku(self.sd)
        eski = grup("sonnet", 20, 10, gun_once=40) + grup("opus", 20, 20, baslangic=100, gun_once=40)
        yeni = PD.degerlendir(self.sd, simdi=SIMDI, kartlar=eski, kayitlar=[], surum="claude-sonnet-5-6")
        self.assertEqual(yeni["durum"], "sifirlandi")
        self.assertEqual(yeni["onceki_surum"], "claude-sonnet-5-5")
        self.assertEqual(PD._oku(self.sd)["model_surumu"], "claude-sonnet-5-6")
        self.assertNotEqual(PD._oku(self.sd)["donem_basi"], d["donem_basi"])
        r = PD.degerlendir(self.sd, simdi=SIMDI, kartlar=eski, kayitlar=[], surum="claude-sonnet-5-6", zorla=True)
        self.assertEqual(r["durum"], "degerlendirildi")
        self.assertEqual([x for x in r["planlayicilar"] if x["n"]], [])  # dönem öncesi kartlar dışarıda
        self.assertIsNone(r["oneri"])

    def test_kuru_hicbir_sey_yazmaz(self):
        r = PD.degerlendir(self.sd, simdi=SIMDI, kartlar=[], kayitlar=[], surum="claude-sonnet-5-5", kuru=True)
        self.assertEqual(r["durum"], "sifirlandi")
        self.assertFalse(os.path.exists(PD._durum_yolu(self.sd)))


class PlanlayiciCli(unittest.TestCase):
    def test_cli_json_ve_kpi_islem_dali(self):
        proje = tempfile.mkdtemp(prefix="ork_pldc_")
        self.addCleanup(shutil.rmtree, proje, ignore_errors=True)
        env = dict(os.environ, PYTHONUTF8="1", CLAUDE_CODE_SESSION_ID="pld-oturum", CLAUDE_PROJECT_DIR=proje)

        def cli(*a):
            return ic_kos.kos([CLI, *a, "--ajan-id", "ana", "--ajan-tipi", "ana"], cwd=proje, env=env)
        self.assertEqual(cli("baslat").returncode, 0)
        r = cli("kpi", "planlayici-degerlendir", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["durum"], "sifirlandi")
        r = cli("kpi", "planlayici-degerlendir", "--json", "--zorla")
        self.assertEqual(json.loads(r.stdout)["durum"], "degerlendirildi")
        self.assertEqual(cli("kpi", "planlayici-degerlendir").returncode, 0)  # bekliyor, metin çıktı
        self.assertEqual(cli("kpi", "--json").returncode, 0)  # eski kullanım bozulmadı


if __name__ == "__main__":
    unittest.main()
