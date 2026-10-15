"""E2: `orkestra onay vaat|etki-izle|etki-liste|etki-kapat|etki-geri-al` CLI ve hook etki ipucu.

Eşikler: göreli fark %10, birikimde en az 20 örnek, 3 gün üst üste 'kotu' -> geri al / sürdür sorusu.
Sabit süre yok: izleme yalnız etki-kapat ya da etki-geri-al ile durur.
Testler yalnız CLI ve hook sınırından konuşur (etki.py iç arayüzüne bağlı değildir)."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import onay  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)

OTURUM = "etki-cli-oturum"
GECERSIZ_ISARET = "sürdür"  # hook ipucunun soru metninde geçer; temiz bağlamda bulunmamalı


class EtkiTemel(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_etki_")
        self.ev = tempfile.mkdtemp(prefix="ork_ev_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = self.kos([CLI, "baslat"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.ev, ignore_errors=True)

    def kos(self, args, stdin=None):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1", HOME=self.ev, USERPROFILE=self.ev)
        env.pop("CLAUDE_PROJECT_DIR", None)
        return ic_kos.kos(args, cwd=self.proje, env=env, input=stdin)

    def cli(self, *args):
        return self.kos([CLI, "onay"] + list(args))

    def hook(self, olay="SessionStart"):
        g = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": olay}
        r = self.kos([HOOK, olay], stdin=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def baglam(self, cikti):
        return (cikti.get("hookSpecificOutput") or {}).get("additionalContext", "")

    # --- yardımcılar
    def uygulanmis(self, vaat=True, olculemez=False, geriye_gun=0):
        """Onaylı + uygulanmış bir kayıt kurar; vaat yazar; uygulama tarihini geriye_gun kadar geri çeker."""
        k = onay.iste(self.sd, "Öneri", "metin", tur="perspektif")
        onay.karar_ver(self.sd, k["id"], "onay")
        if vaat:
            args = ["vaat", k["id"], "--metin", "Ret oranı azalır"]
            if olculemez:
                args += ["--olculemez"]
            else:
                args += ["--metrik", "kpi:ret_orani", "--yon", "azalmali"]
            r = self.cli(*args)
            self.assertEqual(r.returncode, 0, r.stderr)
        onay.al(self.sd, k["id"], OTURUM)
        onay.uygulandi(self.sd, k["id"], "uygulandı", oturum=OTURUM)
        if geriye_gun:
            self.tarih_geri(k["id"], geriye_gun)
        return k["id"]

    def tarih_geri(self, oid, gun):
        yol = onay._kayit_yolu(self.sd, oid)
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        d = (datetime.date.today() - datetime.timedelta(days=gun)).isoformat()
        e = k.setdefault("etki", {})
        e["uygulama_tarihi"] = d
        e.setdefault("izleme", {})["baslangic"] = d
        e["gunluk"] = []
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False)

    def kayit(self, oid):
        with open(onay._kayit_yolu(self.sd, oid), encoding="utf-8") as f:
            return json.load(f)

    def gunluk_say(self, oid):
        return len((self.kayit(oid).get("etki") or {}).get("gunluk") or [])

    def jsonl_say(self):
        yol = os.path.join(self.sd, "onaylar", "etki.jsonl")
        if not os.path.exists(yol):
            return 0
        with open(yol, encoding="utf-8") as f:
            return len([s for s in f.read().splitlines() if s.strip()])

    def kayit_yaz(self, oid, degistir):
        yol = onay._kayit_yolu(self.sd, oid)
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        degistir(k)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f, ensure_ascii=False)


class Vaat(EtkiTemel):
    def test_vaat_olculebilir_yazilir_varsayilan_esikle(self):
        k = onay.iste(self.sd, "Öneri", "metin", tur="perspektif")
        onay.karar_ver(self.sd, k["id"], "onay")
        r = self.cli("vaat", k["id"], "--metin", "Ret oranı azalır", "--metrik", "kpi:ret_orani",
                     "--yon", "azalmali")
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.kayit(k["id"])["vaat"]
        self.assertEqual(v["metin"], "Ret oranı azalır")
        self.assertTrue(v["olculebilir"])
        self.assertEqual(v["metrik"], "kpi:ret_orani")
        self.assertEqual(v["yon"], "azalmali")
        self.assertEqual(v["kapsam"], "genel")
        self.assertAlmostEqual(v["esik"]["goreli"], 0.10)
        self.assertEqual(v["esik"]["min_ornek"], 20)

    def test_vaat_kapsam_yazilir(self):
        k = onay.iste(self.sd, "Öneri", "metin", tur="perspektif")
        r = self.cli("vaat", k["id"], "--metin", "m", "--metrik", "kpi:ret_orani", "--yon", "artmali",
                     "--kapsam", "kod")
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.kayit(k["id"])["vaat"]
        self.assertEqual(v["kapsam"], "kod")
        self.assertEqual(v["yon"], "artmali")

    def test_vaat_olculemez_isaretlenir_metrik_gerekmez(self):
        k = onay.iste(self.sd, "Öneri", "metin", tur="perspektif")
        r = self.cli("vaat", k["id"], "--metin", "Hafıza sadeleşir", "--olculemez")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.kayit(k["id"])["vaat"]["olculebilir"])

    def test_vaat_gecersiz_yon_anlasilir_hata(self):
        k = onay.iste(self.sd, "Öneri", "metin", tur="perspektif")
        r = self.cli("vaat", k["id"], "--metin", "m", "--metrik", "kpi:ret_orani", "--yon", "yukari")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("azalmali", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIsNone(self.kayit(k["id"]).get("vaat"))

    def test_vaat_olculebilirde_metrik_zorunlu(self):
        k = onay.iste(self.sd, "Öneri", "metin", tur="perspektif")
        r = self.cli("vaat", k["id"], "--metin", "m", "--yon", "azalmali")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIsNone(self.kayit(k["id"]).get("vaat"))

    def test_vaat_metin_zorunlu(self):
        k = onay.iste(self.sd, "Öneri", "metin", tur="perspektif")
        r = self.cli("vaat", k["id"], "--olculemez")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--metin", r.stderr)

    def test_vaat_olmayan_kayit_hata(self):
        r = self.cli("vaat", "O-999", "--metin", "m", "--olculemez")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)

    def test_vaat_gecersiz_kimlik_hata(self):
        r = self.cli("vaat", "xyz", "--metin", "m", "--olculemez")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)

    def test_vaat_olay_gunlugune_eklenir(self):
        k = onay.iste(self.sd, "Öneri", "metin", tur="perspektif")
        once = self.jsonl_say()
        r = self.cli("vaat", k["id"], "--metin", "m", "--metrik", "kpi:ret_orani", "--yon", "azalmali")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreater(self.jsonl_say(), once)


class EtkiIzle(EtkiTemel):
    def test_izle_uygulama_gununden_bugune_gun_doldurur(self):
        oid = self.uygulanmis(geriye_gun=3)
        r = self.cli("etki-izle", oid)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = self.kayit(oid)["etki"]
        self.assertEqual(len(e["gunluk"]), 4)  # uygulama günü dahil 4 gün
        self.assertEqual([g["gun"] for g in e["gunluk"]], [1, 2, 3, 4])
        self.assertEqual(e["gunluk"][0]["tarih"], e["uygulama_tarihi"])
        self.assertEqual(e["izleme"]["durum"], "suruyor")

    def test_izle_ikinci_calistirmada_satir_eklemez_kayit(self):
        oid = self.uygulanmis(geriye_gun=2)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        gunluk = self.gunluk_say(oid)
        self.assertGreater(gunluk, 0)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        self.assertEqual(self.gunluk_say(oid), gunluk)

    def test_izle_ikinci_calistirmada_satir_eklemez_jsonl(self):
        oid = self.uygulanmis(geriye_gun=2)
        self.assertEqual(self.cli("etki-izle").returncode, 0)
        satir = self.jsonl_say()
        self.assertGreater(satir, 0)
        self.assertEqual(self.cli("etki-izle").returncode, 0)
        self.assertEqual(self.jsonl_say(), satir)
        self.assertEqual(self.gunluk_say(oid), 3)

    def test_izle_kimliksiz_tum_izlenenleri_dolasir(self):
        a = self.uygulanmis(geriye_gun=1)
        b = self.uygulanmis(geriye_gun=2)
        r = self.cli("etki-izle")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.gunluk_say(a), 2)
        self.assertEqual(self.gunluk_say(b), 3)

    def test_izle_atlanan_gunler_sonraki_calismada_dolar(self):
        oid = self.uygulanmis(geriye_gun=1)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        self.assertEqual(self.gunluk_say(oid), 2)
        # zaman geçmiş gibi: uygulama tarihi 4 gün öncesine alınır, mevcut satırlar korunur
        def geri(k):
            d = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
            k["etki"]["uygulama_tarihi"] = d
            k["etki"]["izleme"]["baslangic"] = d
            k["etki"]["gunluk"] = []
        self.kayit_yaz(oid, geri)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        self.assertEqual(self.gunluk_say(oid), 5)

    def test_izle_sabit_bitis_yok_uzun_sure_sonra_da_surer(self):
        oid = self.uygulanmis(geriye_gun=120)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        e = self.kayit(oid)["etki"]
        self.assertEqual(len(e["gunluk"]), 121)
        self.assertEqual(e["izleme"]["durum"], "suruyor")
        self.assertIsNone(e["izleme"]["kapanis"])

    def test_izle_olculemez_vaat_sahte_iyi_demez(self):
        oid = self.uygulanmis(olculemez=True, geriye_gun=2)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        e = self.kayit(oid).get("etki") or {}
        for g in e.get("gunluk") or []:
            self.assertEqual(g["gidisat"], "olculemez")
        self.assertNotEqual((e.get("izleme") or {}).get("son_gidisat"), "iyi")

    def test_izle_vaatsiz_kayit_olculemez_damgali(self):
        oid = self.uygulanmis(vaat=False, geriye_gun=1)
        r = self.cli("etki-izle", oid)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = self.kayit(oid).get("etki") or {}
        self.assertNotIn((e.get("izleme") or {}).get("son_gidisat"), ("iyi", "kotu", "etkisiz"))
        for g in e.get("gunluk") or []:
            self.assertEqual(g["gidisat"], "olculemez")

    def test_izle_veri_yokken_yetersiz_veri(self):
        oid = self.uygulanmis(geriye_gun=2)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        for g in self.kayit(oid)["etki"]["gunluk"]:
            self.assertEqual(g["gidisat"], "yetersiz-veri")

    def test_izle_olmayan_kayit_hata(self):
        r = self.cli("etki-izle", "O-999")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)

    def test_izle_uygulanmamis_kayit_satir_eklemez(self):
        k = onay.iste(self.sd, "Bekleyen", "m", tur="perspektif")
        self.cli("vaat", k["id"], "--metin", "m", "--olculemez")
        self.assertEqual(self.cli("etki-izle").returncode, 0)
        self.assertEqual(self.gunluk_say(k["id"]), 0)

    def test_izle_bos_projede_hatasiz(self):
        r = self.cli("etki-izle")
        self.assertEqual(r.returncode, 0, r.stderr)


class EtkiListe(EtkiTemel):
    def test_liste_bos(self):
        r = self.cli("etki-liste")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kayıt yok", r.stdout)

    def test_liste_json_bos(self):
        r = self.cli("etki-liste", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [])

    def test_liste_uygulanan_kaydi_gosterir(self):
        oid = self.uygulanmis(geriye_gun=1)
        r = self.cli("etki-liste")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(oid, r.stdout)

    def test_liste_json_alanlari(self):
        oid = self.uygulanmis(geriye_gun=1)
        r = self.cli("etki-liste", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        veri = json.loads(r.stdout)
        self.assertIsInstance(veri, list)
        satir = [s for s in veri if s.get("id") == oid]
        self.assertEqual(len(satir), 1)

    def test_liste_uygulanmamis_kaydi_icermez(self):
        k = onay.iste(self.sd, "Bekleyen", "m", tur="perspektif")
        self.cli("vaat", k["id"], "--metin", "m", "--olculemez")
        veri = json.loads(self.cli("etki-liste", "--json").stdout)
        self.assertNotIn(k["id"], [s.get("id") for s in veri])

    def test_liste_yazma_yapmaz(self):
        self.uygulanmis(geriye_gun=2)
        self.cli("etki-izle")
        satir = self.jsonl_say()
        self.cli("etki-liste")
        self.cli("etki-liste", "--json")
        self.assertEqual(self.jsonl_say(), satir)


class EtkiKapat(EtkiTemel):
    def test_kapat_gecersiz_sonuc_anlasilir_hata(self):
        oid = self.uygulanmis(geriye_gun=1)
        r = self.cli("etki-kapat", oid, "--sonuc", "belki")
        self.assertNotEqual(r.returncode, 0)
        for gecerli in ("dogru-karar", "yanlis-karar", "belirsiz"):
            self.assertIn(gecerli, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIsNone((self.kayit(oid).get("etki") or {}).get("karar"))

    def test_kapat_sonuc_zorunlu(self):
        oid = self.uygulanmis(geriye_gun=1)
        r = self.cli("etki-kapat", oid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--sonuc", r.stderr)

    def test_kapat_her_gecerli_sonuc_kabul(self):
        for sonuc in ("dogru-karar", "yanlis-karar", "belirsiz"):
            oid = self.uygulanmis(geriye_gun=1)
            r = self.cli("etki-kapat", oid, "--sonuc", sonuc, "--not", "gerekçe")
            self.assertEqual(r.returncode, 0, r.stderr)
            e = self.kayit(oid)["etki"]
            self.assertEqual(e["karar"]["sonuc"], sonuc)
            self.assertEqual(e["karar"]["not"], "gerekçe")
            self.assertTrue(e["karar"]["zaman"])
            self.assertIsNotNone(e["izleme"]["kapanis"])
            self.assertNotEqual(e["izleme"]["durum"], "suruyor")

    def test_kapat_not_istege_bagli(self):
        oid = self.uygulanmis(geriye_gun=1)
        r = self.cli("etki-kapat", oid, "--sonuc", "belirsiz")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_kapatilan_izleme_artik_satir_eklemez(self):
        oid = self.uygulanmis(geriye_gun=1)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        self.assertEqual(self.cli("etki-kapat", oid, "--sonuc", "dogru-karar").returncode, 0)
        gunluk, satir = self.gunluk_say(oid), self.jsonl_say()
        def geri(k):
            d = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
            k["etki"]["uygulama_tarihi"] = d
        self.kayit_yaz(oid, geri)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        self.assertEqual(self.gunluk_say(oid), gunluk)
        self.assertEqual(self.jsonl_say(), satir)

    def test_kapat_olay_gunlugune_eklenir(self):
        oid = self.uygulanmis(geriye_gun=1)
        once = self.jsonl_say()
        self.assertEqual(self.cli("etki-kapat", oid, "--sonuc", "dogru-karar").returncode, 0)
        self.assertGreater(self.jsonl_say(), once)

    def test_kapat_uygulanmamis_kayit_hata(self):
        k = onay.iste(self.sd, "Bekleyen", "m", tur="perspektif")
        r = self.cli("etki-kapat", k["id"], "--sonuc", "belirsiz")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)

    def test_kapat_olmayan_kayit_hata(self):
        r = self.cli("etki-kapat", "O-999", "--sonuc", "belirsiz")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)


class EtkiGeriAl(EtkiTemel):
    def test_geri_al_neden_zorunlu(self):
        oid = self.uygulanmis(geriye_gun=1)
        r = self.cli("etki-geri-al", oid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--neden", r.stderr)

    def test_geri_al_izlemeyi_durdurur(self):
        oid = self.uygulanmis(geriye_gun=2)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        r = self.cli("etki-geri-al", oid, "--neden", "ret oranı yükseldi")
        self.assertEqual(r.returncode, 0, r.stderr)
        e = self.kayit(oid)["etki"]
        self.assertIsNotNone(e["izleme"]["kapanis"])
        self.assertNotEqual(e["izleme"]["durum"], "suruyor")
        gunluk = self.gunluk_say(oid)
        self.assertEqual(self.cli("etki-izle", oid).returncode, 0)
        self.assertEqual(self.gunluk_say(oid), gunluk)

    def test_geri_alma_olay_gunlugune_eklenir(self):
        oid = self.uygulanmis(geriye_gun=1)
        once = self.jsonl_say()
        self.assertEqual(self.cli("etki-geri-al", oid, "--neden", "n").returncode, 0)
        yol = os.path.join(self.sd, "onaylar", "etki.jsonl")
        with open(yol, encoding="utf-8") as f:
            icerik = f.read()
        self.assertGreater(self.jsonl_say(), once)
        self.assertIn("geri-alindi", icerik)

    def test_geri_al_olmayan_kayit_hata(self):
        r = self.cli("etki-geri-al", "O-999", "--neden", "n")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)


class EtkiGunlukEkleSadece(EtkiTemel):
    def test_jsonl_onceki_satirlar_degismez(self):
        oid = self.uygulanmis(geriye_gun=1)
        self.cli("etki-izle", oid)
        yol = os.path.join(self.sd, "onaylar", "etki.jsonl")
        with open(yol, encoding="utf-8") as f:
            once = f.read()
        self.cli("etki-kapat", oid, "--sonuc", "belirsiz")
        with open(yol, encoding="utf-8") as f:
            sonra = f.read()
        self.assertTrue(sonra.startswith(once))
        self.assertGreater(len(sonra), len(once))
        for s in sonra.splitlines():
            json.loads(s)  # her satır geçerli JSON


class HookEtkiIpucu(EtkiTemel):
    def test_kayit_yokken_ipucu_yok(self):
        m = self.baglam(self.hook())
        self.assertIn("Orkestra bu projede açık", m)
        self.assertNotIn(GECERSIZ_ISARET, m)

    def test_iyi_giden_kayitta_ipucu_yok(self):
        oid = self.uygulanmis(geriye_gun=1)
        def iyi(k):
            k["etki"]["izleme"].update({"durum": "suruyor", "son_gidisat": "iyi", "ayni_gidisat_gun": 2})
        self.kayit_yaz(oid, iyi)
        m = self.baglam(self.hook())
        self.assertNotIn(GECERSIZ_ISARET, m)
        self.assertNotIn("geri al", m.lower())

    def test_olculemez_kayitta_ipucu_yok(self):
        self.uygulanmis(olculemez=True, geriye_gun=1)
        m = self.baglam(self.hook())
        self.assertNotIn(GECERSIZ_ISARET, m)

    def test_soru_bekleyen_kayitta_ipucu_gorunur(self):
        oid = self.uygulanmis(geriye_gun=3)
        def soru(k):
            k["etki"]["izleme"].update({"durum": "soru_bekliyor", "son_gidisat": "kotu", "ayni_gidisat_gun": 3})
        self.kayit_yaz(oid, soru)
        m = self.baglam(self.hook())
        self.assertIn("Orkestra bu projede açık", m)  # mevcut bağlam korunur
        self.assertIn(oid, m)
        self.assertIn("geri al", m.lower())
        self.assertIn(GECERSIZ_ISARET, m.lower())

    def test_kapanmis_kayitta_ipucu_yok(self):
        oid = self.uygulanmis(geriye_gun=1)
        self.cli("etki-kapat", oid, "--sonuc", "yanlis-karar")
        m = self.baglam(self.hook())
        self.assertNotIn(GECERSIZ_ISARET, m)

    def test_user_prompt_submit_bozulmaz(self):
        self.uygulanmis(geriye_gun=1)
        self.hook("UserPromptSubmit")  # çıkış kodu 0 hook() içinde doğrulanır

    def test_bozuk_etki_gunlugu_hook_cokmez(self):
        self.uygulanmis(geriye_gun=2)
        os.makedirs(os.path.join(self.sd, "onaylar"), exist_ok=True)
        with open(os.path.join(self.sd, "onaylar", "etki.jsonl"), "w", encoding="utf-8") as f:
            f.write("{bozuk json\n\x00\x00\n")
        m = self.baglam(self.hook())
        self.assertIn("Orkestra bu projede açık", m)

    def test_bozuk_etki_alani_hook_cokmez(self):
        oid = self.uygulanmis(geriye_gun=2)
        self.kayit_yaz(oid, lambda k: k.update({"etki": "bozuk", "vaat": 5}))
        m = self.baglam(self.hook())
        self.assertIn("Orkestra bu projede açık", m)
        self.assertNotIn("Traceback", m)

    def test_bozuk_tarih_hook_cokmez(self):
        oid = self.uygulanmis(geriye_gun=2)
        self.kayit_yaz(oid, lambda k: k["etki"].update({"uygulama_tarihi": "tarih-degil"}))
        m = self.baglam(self.hook())
        self.assertIn("Orkestra bu projede açık", m)

    def test_oturum_acilisinda_izle_calisir(self):
        oid = self.uygulanmis(geriye_gun=2)
        self.hook("SessionStart")
        self.assertEqual(self.gunluk_say(oid), 3)  # hook etki.izle çağırır, atlanan günler dolar
        self.hook("SessionStart")
        self.assertEqual(self.gunluk_say(oid), 3)  # ikinci açılış satır eklemez


if __name__ == "__main__":
    unittest.main()
