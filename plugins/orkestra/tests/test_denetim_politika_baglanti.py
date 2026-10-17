"""G-143 (L5-D2): denetim politikasının is-bitti ve calistir.js'e bağı (gölge kayıt, otomatik onay yolu)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402
import test_calistir_akisi as TCA  # noqa: E402

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
OTURUM = "test-oturum-dpb"
ISCI = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t2")
BETIK_YESIL = "import sys\nsys.exit(0)\n"


class PolitikaBaglanti(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_dpb_")
        r = self.kos([CLI, "baslat"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sd = os.path.join(self.proje, ".claude", "orkestra")

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    # --- yardımcılar
    def kos(self, args):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
        env.pop("CLAUDE_PROJECT_DIR", None)
        return ic_kos.kos(args, cwd=self.proje, env=env)

    def cli(self, *args, ajan_id=None, ajan_tipi=None):
        a = [CLI] + list(args)
        if ajan_id:
            a += ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi]
        return self.kos(a)

    def kart(self, *ek, sinif="arastirma"):
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "politika işi", "--basamak", "T2",
                     "--sinif", sinif, "--kabul", "K1: kriter", "--yazma", "src/**", *ek)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.strip()

    def kod_kart(self):
        os.makedirs(os.path.join(self.proje, "testler"), exist_ok=True)
        with open(os.path.join(self.proje, "testler", "test_a.py"), "w", encoding="utf-8") as f:
            f.write(BETIK_YESIL)
        return self.kart("--test-komutu", f'"{sys.executable}" testler/test_a.py', "--test-alani", "testler/*.py",
                         "--elle-teslim", sinif="kod")

    def goster(self, gid):
        r = self.cli("kart", "goster", gid)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def kart_yaz(self, k):
        with open(os.path.join(self.sd, "gorevler", f"{k['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False)

    def gecmis_kartlar(self, sinif="arastirma", n=12, ret=0):
        """Aynı gruptan (sinif|T2) n teslim edilmiş geçmiş kart: ilk denetim kararları (ret adet ret)."""
        for i in range(n):
            self.kart_yaz({"id": f"G-{900 + i}", "baslik": "eski", "sinif": sinif, "basamak": "T2", "durum": "teslim",
                           "denetimler": [{"karar": "ret" if i < ret else "onay", "sira": 1}], "gecmis": []})

    def politika(self, mod, gecit_acik=True, **ek):
        ayar = {"mod": mod, "min_ornek": 10, "max_ilk_ret_orani": 0.1, "ornekleme_orani": 0.0}
        ayar["gecit"] = {"min_denetim": 1, "min_kanit_kart": 0} if gecit_acik else {"min_denetim": 10 ** 6,
                                                                                   "min_kanit_kart": 10 ** 6}
        ayar.update(ek)
        with open(os.path.join(self.sd, "denetim_politikasi.json"), "w", encoding="utf-8") as f:
            json.dump(ayar, f)

    def bitti(self, gid):
        return self.cli("kart", "durum", gid, "is-bitti", "--ozet", "bitti", "--cikti", "src/a.py", **ISCI)

    def otomatik_onay_yok(self, gid, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("OTOMATIK-ONAY", r.stdout)
        k = self.goster(gid)
        self.assertEqual(k["durum"], "denetimde")
        self.assertFalse([d for d in k["denetimler"] if d.get("denetim_turu") == "otomatik"])
        self.assertFalse([g for g in k["gecmis"] if g.get("otomatik")])
        return k

    # K1
    def test_k1_varsayilan_golge_kayit_var_uygulanmaz(self):
        self.gecmis_kartlar()
        gid = self.kart()
        r = self.bitti(gid)  # proje ezmesi yok: eklenti varsayılanı mod=golge (I-058 P6, 17.10.2026)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), f"{gid} → denetimde")
        k = self.goster(gid)
        self.assertEqual(k["durum"], "denetimde")
        pk = k.get("politika_kararlari") or []
        self.assertEqual(len(pk), 1)
        self.assertIs(pk[-1]["uygulanir"], False)
        self.assertFalse([d for d in k["denetimler"] if d.get("denetim_turu") == "otomatik"])

    def test_k1_tam_mod_acik_ezmeyle_de_kayit_yok(self):
        self.gecmis_kartlar()
        self.politika("tam")
        gid = self.kart()
        r = self.bitti(gid)
        self.assertEqual(r.stdout.strip(), f"{gid} → denetimde")
        self.assertNotIn("politika_kararlari", self.goster(gid))

    # K2
    def test_k2_golge_kayit_yazar_uygulamaz(self):
        self.gecmis_kartlar()
        self.politika("golge")
        gid = self.kart()
        k = self.otomatik_onay_yok(gid, self.bitti(gid))
        pk = k["politika_kararlari"]
        self.assertEqual(len(pk), 1)
        self.assertEqual(pk[0]["karar"], "atla")
        self.assertIs(pk[0]["uygulanir"], False)
        self.assertEqual(pk[0]["mod"], "golge")
        self.assertEqual(pk[0]["grup"], "arastirma|T2")

    # K3
    def test_k3_etkin_gecit_acik_atla_otomatik_onay(self):
        self.gecmis_kartlar()
        self.politika("etkin")
        gid = self.kart()
        r = self.bitti(gid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        satirlar = [s for s in r.stdout.splitlines() if s.startswith("OTOMATIK-ONAY")]
        self.assertEqual(satirlar, ["OTOMATIK-ONAY: politika dusuk-risk-grup"])
        k = self.goster(gid)
        self.assertEqual(k["durum"], "onaylandi")
        d = k["denetimler"][-1]
        self.assertEqual(d["denetim_turu"], "otomatik")
        self.assertEqual(d["karar"], "onay")
        self.assertEqual(d["ajan"], "politika")
        self.assertIsNone(d["agent_id"])
        self.assertEqual(d["gerekce"], "politika: dusuk-risk-grup")
        self.assertEqual(d["politika"]["karar"], "atla")
        g = [x for x in k["gecmis"] if x.get("olay") == "denetim:onay"]
        self.assertEqual(len(g), 1)
        self.assertIs(g[0]["otomatik"], True)
        self.assertEqual(g[0]["ajan"], "politika")
        self.assertIs(k["politika_kararlari"][-1]["uygulanir"], True)

    def test_k3_kod_karti_taze_yesille_otomatik_onay(self):
        self.gecmis_kartlar(sinif="kod")
        self.politika("etkin")
        gid = self.kod_kart()
        r = self.bitti(gid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OTOMATIK-ONAY: politika dusuk-risk-grup", r.stdout)
        k = self.goster(gid)
        self.assertEqual(k["durum"], "onaylandi")
        self.assertEqual(k["denetimler"][-1]["denetim_turu"], "otomatik")

    # K4
    def test_k4_gecit_kapali_otomatik_onay_yok(self):
        self.gecmis_kartlar()
        self.politika("etkin", gecit_acik=False)
        gid = self.kart()
        k = self.otomatik_onay_yok(gid, self.bitti(gid))
        self.assertEqual(k["politika_kararlari"][-1]["karar"], "atla")
        self.assertIs(k["politika_kararlari"][-1]["uygulanir"], False)

    def test_k4_tdd_karti_otomatik_onay_yok(self):
        self.gecmis_kartlar()
        self.politika("etkin")
        gid = self.kart()
        k = self.goster(gid)
        k["tdd"] = True  # tdd kod kartı kırmızı aşama ister; politika yalnız bayrağa bakar
        self.kart_yaz(k)
        k = self.otomatik_onay_yok(gid, self.bitti(gid))
        self.assertEqual(k["politika_kararlari"][-1]["neden"], "tdd")

    def test_k4_yuksek_risk_otomatik_onay_yok(self):
        self.gecmis_kartlar()
        self.politika("etkin")
        gid = self.kart("--risk", "yuksek")
        k = self.otomatik_onay_yok(gid, self.bitti(gid))
        self.assertEqual(k["politika_kararlari"][-1]["neden"], "yuksek-risk")

    def test_k4_orneklenmis_otomatik_onay_yok(self):
        self.gecmis_kartlar()
        self.politika("etkin", ornekleme_orani=1.0)
        gid = self.kart()
        k = self.otomatik_onay_yok(gid, self.bitti(gid))
        pk = k["politika_kararlari"][-1]
        self.assertEqual(pk["neden"], "ornekleme")
        self.assertIs(pk["orneklenmis"], True)

    def test_k4_ret_orani_yuksek_otomatik_onay_yok(self):
        self.gecmis_kartlar(ret=6)
        self.politika("etkin")
        gid = self.kart()
        k = self.otomatik_onay_yok(gid, self.bitti(gid))
        self.assertEqual(k["politika_kararlari"][-1]["neden"], "ret-orani-yuksek")

    # K5
    def test_k5_kod_karti_taze_yesil_yoksa_otomatik_onay_yok(self):
        self.gecmis_kartlar(sinif="kod")
        self.politika("etkin")
        gid = self.kod_kart()
        k = self.goster(gid)
        # Eski biçim kod kartı: test alanları yok → is-bitti yeşil koşmaz, taze yeşil kaydı oluşmaz.
        for alan in ("test_komutu", "test_alani"):
            k.pop(alan, None)
        self.kart_yaz(k)
        r = self.bitti(gid)
        k = self.otomatik_onay_yok(gid, r)
        self.assertIs(k["politika_kararlari"][-1]["uygulanir"], True)  # politika atla dedi, yeşil kuralı engelledi
        self.assertIn("politika-onay-engeli", [g.get("olay") for g in k["gecmis"]])
        self.assertIn("otomatik onayı verilmedi", r.stderr)

    # K6
    def _patlak(self, ad):
        import denetim_politika
        eski = getattr(denetim_politika, ad)

        def patlak(*a, **kw):
            raise RuntimeError("bozuk")
        setattr(denetim_politika, ad, patlak)
        self.addCleanup(setattr, denetim_politika, ad, eski)

    def test_k6_kaydet_istisnasi_is_bitti_basarili(self):
        self.gecmis_kartlar()
        self.politika("etkin")
        self._patlak("kaydet")
        gid = self.kart()
        r = self.bitti(gid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"{gid} → denetimde", r.stdout)
        self.assertNotIn("OTOMATIK-ONAY", r.stdout)
        self.assertEqual(self.goster(gid)["durum"], "denetimde")

    def test_k6_karar_istisnasi_is_bitti_basarili(self):
        self.gecmis_kartlar()
        self.politika("golge")
        self._patlak("karar")
        gid = self.kart()
        r = self.bitti(gid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.goster(gid)
        self.assertEqual(k["durum"], "denetimde")
        self.assertNotIn("politika_kararlari", k)
        self.assertEqual(len(k["is_turlari"]), 1)


# K7 ------------------------------------------------------------- calistir.js (node gerekir)
class CalistirOtoOnayStatik(unittest.TestCase):
    def test_sema_ve_protokol(self):
        with open(TCA.BETIK, encoding="utf-8") as f:
            js = f.read()
        self.assertIn("oto_onay: { type: 'boolean' }", js)
        self.assertIn("OTOMATIK-ONAY satırı varsa oto_onay=true", js)
        g = TCA.yurut_kaynagi(js)
        self.assertLess(g.index("is.oto_onay === true"), g.index("'orkestra:denetci'"))


@unittest.skipUnless(TCA.NODE, TCA.NODE_YOK_GEREKCE)
class CalistirOtoOnay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_dpb_js_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(TCA.KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos(self, gorevler, **senaryo):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=gorevler), f, ensure_ascii=False)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        p = subprocess.run([TCA.NODE, self.kosum, TCA.BETIK, yol], capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        cikti = json.loads(p.stdout.decode("utf-8"))
        return cikti["sonuc"]["sonuclar"][0], cikti["cagrilar"]

    def test_k7_oto_onay_true_denetci_cagrilmaz(self):
        s, c = self.kos([TCA.kart()], onkontrol=[{"kapi": "gecti", "oto_onay": True}])
        self.assertEqual([x for x in c if x["agentType"] == "orkestra:denetci"], [])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertIn({"basamak": "T2", "surec": "denetim", "karar": "oto-onay"}, s["gecmis"])
        self.assertIn("OTOMATIK-ONAY", c[0]["istem"])

    def test_k7_oto_onay_yoksa_denetci_cagrilir(self):
        for kapi in ({"kapi": "gecti"}, {"kapi": "gecti", "oto_onay": False}):
            s, c = self.kos([TCA.kart()], onkontrol=[kapi])
            self.assertEqual(len([x for x in c if x["agentType"] == "orkestra:denetci"]), 1)
            self.assertEqual(s["durum"], "onaylandi")
            self.assertNotIn("oto-onay", [g.get("karar") for g in s["gecmis"]])


if __name__ == "__main__":
    unittest.main()
