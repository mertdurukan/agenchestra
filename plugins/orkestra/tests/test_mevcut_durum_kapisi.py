"""Mevcut durum kapısı: kod kartında işçi, ilgili mevcut kodu okuduğunu kanıtlamadan kod yazamaz / is-bitti geçemez.

`python -m unittest discover -s plugins/orkestra/tests -p test_mevcut_durum_kapisi.py -v`

Kapı bu testlerde ORKESTRA_MEVCUT_KAPISI=1 ile açıkça kurulur (ic_kos varsayılanı '0').
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
OTURUM = "test-oturum-mevcut"

BETIK = "import os, sys\nprint('kosuldu')\nsys.exit(0)\n"
KAYNAK = "def topla(a, b):\n    \"\"\"iki sayıyı toplar\"\"\"\n    return a + b\n\n\ndef carp(a, b):\n    return a * b\n"

ISCI = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t2")
TEST_YAZARI = dict(ajan_id="ty1", ajan_tipi="orkestra:test-yazari")

GECERLI = {
    "okunan": [{"dosya": "src/mod.py", "satir": 1, "alinti": "def topla(a, b):",
                "rol": "toplama yardımcısı; kart bunu genişletecek"}],
    "yetenekler": ["topla iki sayıyı toplar, carp çarpar; hata yönetimi yok"],
    "karar": "degistir",
    "neden": "Mevcut topla fonksiyonu yeterli; yeni işlev onun yanına eklenir, çağıranlar bozulmaz.",
    "etkilenenler": ["testler/test_a.py → topla"],
}


def kos(args, cwd, kapi="1", girdi=None):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    env["ORKESTRA_MEVCUT_KAPISI"] = kapi
    env["ORKESTRA_TEKNIK_KAPISI"] = "0"
    return ic_kos.kos(args, cwd=cwd, env=env, input=girdi)


class MevcutKapisi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_mev_")
        self.assertEqual(self.cli("baslat").returncode, 0)
        self.yaz("testler/test_a.py", BETIK)
        self.yaz("src/mod.py", KAYNAK)
        self.komut = f'"{sys.executable}" testler/test_a.py'

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    # ---------------------------------------------------------- yardımcılar
    def yaz(self, goreli, icerik):
        yol = os.path.join(self.proje, *goreli.split("/"))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik)
        return yol

    def not_dosyasi(self, nesne=None, ad="mevcut.json", ham=None):
        icerik = ham if ham is not None else json.dumps(GECERLI if nesne is None else nesne, ensure_ascii=False)
        return self.yaz(ad, icerik)

    def cli(self, *args, kapi="1", kim=None):
        a = [CLI] + list(args)
        if kim:
            a += ["--ajan-id", kim["ajan_id"], "--ajan-tipi", kim["ajan_tipi"]]
        return kos(a, self.proje, kapi=kapi)

    def goster(self, g):
        r = self.cli("kart", "goster", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def kart(self, sinif="kod"):
        a = ["kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2", "--sinif", sinif,
             "--kabul", "çalışır", "--yazma", "src/**"]
        if sinif == "kod":
            a += ["--tdd", "--test-komutu", self.komut, "--test-alani", "testler/*.py"]
        r = self.cli(*a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def kart_tddsiz(self):
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2", "--sinif", "kod",
                     "--kabul", "çalışır", "--yazma", "src/**", "--test-komutu", self.komut, "--test-alani", "testler/*.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def mevcut(self, g, nesne=None, **kw):
        return self.cli("kart", "mevcut", g, "--dosya", self.not_dosyasi(nesne, **kw), kim=ISCI)

    def bitir(self, g, kim=ISCI, kapi="1"):
        return self.cli("kart", "durum", g, "is-bitti", "--ozet", "bitti", "--cikti", "src/mod.py", kim=kim, kapi=kapi)

    def kayitli_degil(self, g):
        k = self.goster(g)
        self.assertNotIn("mevcut_durum", k)
        self.assertNotIn("mevcut-durum", [h.get("olay") for h in k["gecmis"]])

    # ---------------------------------------------------------- doğrulama modülü
    def modul(self, nesne, alan=None):
        sys.path.insert(0, os.path.join(KOK, "scripts"))
        import mevcut_durum
        return mevcut_durum.dogrula(nesne, [self.proje], alan)

    def test_modul_gecerli(self):
        tamam, hatalar = self.modul(copy.deepcopy(GECERLI))
        self.assertTrue(tamam, hatalar)
        self.assertEqual(list(hatalar), [])

    def test_modul_nesne_degil(self):
        self.assertFalse(self.modul("metin")[0])

    def _bozuk(self, anahtar, deger, beklenen):
        n = copy.deepcopy(GECERLI)
        n[anahtar] = deger
        tamam, hatalar = self.modul(n)
        self.assertFalse(tamam)
        self.assertTrue(any(beklenen in h for h in hatalar), hatalar)

    def test_modul_okunan_bos(self):
        self._bozuk("okunan", [], "okunan")

    def test_modul_yetenekler_bos(self):
        self._bozuk("yetenekler", [], "yetenekler")

    def test_modul_karar_gecersiz(self):
        self._bozuk("karar", "belki", "karar")

    def test_modul_neden_kisa(self):
        self._bozuk("neden", "kısa", "neden")

    def test_modul_etkilenenler_liste_degil(self):
        self._bozuk("etkilenenler", "yok", "etkilenenler")

    def test_modul_etkilenenler_bos_liste_gecerli(self):
        n = dict(copy.deepcopy(GECERLI), etkilenenler=[])
        self.assertTrue(self.modul(n)[0])

    def test_modul_anahtar_eksik(self):
        for a in ("okunan", "yetenekler", "karar", "neden", "etkilenenler"):
            n = copy.deepcopy(GECERLI)
            del n[a]
            tamam, hatalar = self.modul(n)
            self.assertFalse(tamam, a)
            self.assertTrue(any(a in h for h in hatalar), (a, hatalar))

    def _okunan(self, **ek):
        o = dict(GECERLI["okunan"][0], **ek)
        return dict(copy.deepcopy(GECERLI), okunan=[o])

    def test_modul_dosya_yok(self):
        tamam, hatalar = self.modul(self._okunan(dosya="src/yok.py"))
        self.assertFalse(tamam)
        self.assertTrue(any("bulunamadı" in h for h in hatalar), hatalar)

    def test_modul_satir_dosya_disinda(self):
        tamam, hatalar = self.modul(self._okunan(satir=999))
        self.assertFalse(tamam)
        self.assertTrue(any("satır sayısı" in h for h in hatalar), hatalar)

    def test_modul_satir_gecersiz_tip(self):
        for deger in (0, -1, "1", True):
            self.assertFalse(self.modul(self._okunan(satir=deger))[0], deger)

    def test_modul_alinti_satirda_yok(self):
        tamam, hatalar = self.modul(self._okunan(alinti="def olmayan_fonksiyon():"))
        self.assertFalse(tamam)
        self.assertTrue(any("alinti" in h for h in hatalar), hatalar)

    def test_modul_alinti_pencere_icinde_gecerli(self):
        # satır 3 (return a + b), alıntı satır 1'de: ±2 pencere içinde
        self.assertTrue(self.modul(self._okunan(satir=3))[0])

    def test_modul_alinti_pencere_disinda_gecersiz(self):
        # satır 7 (return a * b), alıntı satır 1'de: pencere dışı
        self.assertFalse(self.modul(self._okunan(satir=7))[0])

    def test_modul_alinti_kisa(self):
        self.assertFalse(self.modul(self._okunan(alinti="def"))[0])

    def test_modul_rol_kisa(self):
        self.assertFalse(self.modul(self._okunan(rol="kısa"))[0])

    def test_modul_degistir_yazma_alani_disinda(self):
        tamam, hatalar = self.modul(copy.deepcopy(GECERLI), alan=lambda y: False)
        self.assertFalse(tamam)
        self.assertTrue(any("yazma alanında değil" in h for h in hatalar), hatalar)

    def test_modul_yeni_karar_yazma_alani_kurali_yok(self):
        n = dict(copy.deepcopy(GECERLI), karar="yeni")
        self.assertTrue(self.modul(n, alan=lambda y: False)[0])

    def test_modul_yazma_alaninda_gecerli(self):
        self.assertTrue(self.modul(copy.deepcopy(GECERLI), alan=lambda y: True)[0])

    # ---------------------------------------------------------- CLI: kart mevcut
    def test_cli_gecerli_not_kaydedilir(self):
        g = self.kart()
        r = self.mevcut(g)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.goster(g)
        self.assertEqual(k["mevcut_durum"]["karar"], "degistir")
        self.assertTrue(k.get("mevcut_durum_zaman"))
        self.assertIn("mevcut-durum", [h.get("olay") for h in k["gecmis"]])

    def test_cli_gecersiz_not_reddedilir_ve_kaydedilmez(self):
        g = self.kart()
        r = self.mevcut(g, dict(GECERLI, karar="belki"))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("KAYDEDİLMEDİ", r.stdout + r.stderr)
        self.assertIn("karar", r.stdout + r.stderr)
        self.kayitli_degil(g)

    def test_cli_json_bozuk(self):
        g = self.kart()
        r = self.mevcut(g, ham="{bozuk")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.kayitli_degil(g)

    def test_cli_dosya_yok(self):
        g = self.kart()
        r = self.cli("kart", "mevcut", g, "--dosya", os.path.join(self.proje, "yok.json"), kim=ISCI)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_cli_kod_karti_degilse_reddeder(self):
        g = self.kart("arastirma")
        r = self.mevcut(g)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("kod kartı değil", r.stdout + r.stderr)

    def test_cli_degistir_yazma_alani_disindaki_dosyayi_reddeder(self):
        g = self.kart()
        self.yaz("baska/diger.py", KAYNAK)
        n = copy.deepcopy(GECERLI)
        n["okunan"][0]["dosya"] = "baska/diger.py"
        r = self.mevcut(g, n)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("yazma alanında değil", r.stdout + r.stderr)
        self.kayitli_degil(g)

    def test_cli_yeni_kararda_alan_disi_dosya_okunmus_sayilir(self):
        g = self.kart()
        self.yaz("baska/diger.py", KAYNAK)
        n = copy.deepcopy(GECERLI)
        n["okunan"][0]["dosya"] = "baska/diger.py"
        n["karar"] = "yeni"
        r = self.mevcut(g, n)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # ---------------------------------------------------------- is-bitti kapısı
    def test_isbitti_notsuz_isci_reddedilir(self):
        g = self.kart()
        r = self.bitir(g)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("is-bitti KAYDEDİLMEDİ: mevcut durum notu yok", r.stdout + r.stderr)
        self.assertNotIn("is-bitti", [h.get("olay") for h in self.goster(g)["gecmis"]])

    def test_isbitti_not_varsa_gecer(self):
        g = self.kart_tddsiz()
        self.assertEqual(self.mevcut(g).returncode, 0)
        r = self.bitir(g)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("is-bitti", [h.get("olay") for h in self.goster(g)["gecmis"]])

    def test_isbitti_notsuz_testler_kosmaz(self):
        g = self.kart_tddsiz()
        self.assertEqual(self.bitir(g).returncode, 4)
        self.assertEqual(self.goster(g).get("test_kosulari") or [], [])

    def test_isbitti_yeniden_denenebilir(self):
        g = self.kart_tddsiz()
        self.assertEqual(self.bitir(g).returncode, 4)
        self.assertEqual(self.mevcut(g).returncode, 0)
        self.assertEqual(self.bitir(g).returncode, 0)

    def test_isbitti_kod_disi_kart_muaf(self):
        g = self.kart("arastirma")
        r = self.bitir(g)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_isbitti_test_yazari_muaf(self):
        g = self.kart()
        r = self.bitir(g, kim=TEST_YAZARI)
        self.assertNotIn("mevcut durum notu", r.stdout + r.stderr)

    def test_isbitti_ortam_degiskeni_sifir_kapiyi_kapatir(self):
        g = self.kart_tddsiz()
        r = self.bitir(g, kapi="0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # ---------------------------------------------------------- hook kapısı
    def hook(self, girdi, kapi="1"):
        g = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": "PreToolUse"}
        g.update(girdi)
        r = kos([HOOK, "PreToolUse"], self.proje, kapi=kapi, girdi=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def karar(self, c):
        return (c.get("hookSpecificOutput") or {}).get("permissionDecision")

    def neden(self, c):
        return (c.get("hookSpecificOutput") or {}).get("permissionDecisionReason") or ""

    def ajan(self, aid, gorev, surec="is"):
        os.makedirs(os.path.join(self.proje, ".claude", "orkestra", "oturumlar"), exist_ok=True)
        with open(os.path.join(self.proje, ".claude", "orkestra", "oturumlar", f"ajan_{aid}.json"), "w", encoding="utf-8") as f:
            json.dump({"gorev": gorev, "surec": surec, "ajan": "orkestra:isci-t2"}, f)

    def yaz_hook(self, yol, kapi="1", **ek):
        girdi = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.proje, yol), "content": "x"}}
        girdi.update(ek)
        return self.hook(girdi, kapi=kapi)

    def test_hook_notsuz_yazma_alanina_yazamaz(self):
        g = self.kart_tddsiz()
        self.ajan("w1", g)
        c = self.yaz_hook("src/yeni.py", agent_id="w1", agent_type="orkestra:isci-t2")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("mevcut durumu anla", self.neden(c))
        self.assertIn(f"orkestra kart mevcut {g}", self.neden(c))

    def test_hook_edit_ve_multiedit_da_kapali(self):
        g = self.kart_tddsiz()
        self.ajan("w1", g)
        for arac in ("Edit", "MultiEdit"):
            c = self.yaz_hook("src/mod.py", agent_id="w1", agent_type="orkestra:isci-t2", tool_name=arac)
            self.assertEqual(self.karar(c), "deny", arac)

    def test_hook_not_kaydedilince_yazabilir(self):
        g = self.kart_tddsiz()
        self.ajan("w1", g)
        self.assertEqual(self.mevcut(g).returncode, 0)
        c = self.yaz_hook("src/yeni.py", agent_id="w1", agent_type="orkestra:isci-t2")
        self.assertNotEqual(self.karar(c), "deny", self.neden(c))

    def test_hook_yazma_alani_disi_serbest(self):
        g = self.kart_tddsiz()
        self.ajan("w1", g)
        # teknik/mevcut not JSON'u gibi ara dosyalar yazma alanı dışındadır: kapıdan etkilenmez
        c = self.yaz_hook("not/mevcut.json", agent_id="w1", agent_type="orkestra:isci-t2")
        self.assertNotIn("mevcut durumu anla", self.neden(c))

    def test_hook_test_yaz_sureci_muaf(self):
        g = self.kart()
        self.ajan("ty", g, "test-yaz")
        c = self.yaz_hook("testler/test_yeni.py", agent_id="ty", agent_type="orkestra:test-yazari")
        self.assertNotIn("mevcut durumu anla", self.neden(c))

    def test_hook_ana_ajan_etkilenmez(self):
        self.kart_tddsiz()
        c = self.yaz_hook("src/yeni.py")
        self.assertNotIn("mevcut durumu anla", self.neden(c))

    def test_hook_kod_disi_kart_muaf(self):
        g = self.kart("arastirma")
        self.ajan("w1", g)
        c = self.yaz_hook("src/yeni.py", agent_id="w1", agent_type="orkestra:isci-t2")
        self.assertNotIn("mevcut durumu anla", self.neden(c))

    def test_hook_ortam_degiskeni_sifir_kapiyi_kapatir(self):
        g = self.kart_tddsiz()
        self.ajan("w1", g)
        c = self.yaz_hook("src/yeni.py", kapi="0", agent_id="w1", agent_type="orkestra:isci-t2")
        self.assertNotEqual(self.karar(c), "deny", self.neden(c))

    # ---------------------------------------------------------- belgeler
    def _icerik(self, goreli):
        with open(os.path.join(KOK, *goreli.split("/")), encoding="utf-8") as f:
            return f.read()

    def test_belge_isciler(self):
        for ad in ("isci-t1", "isci-t2", "isci-t3", "isci-t4"):
            t = self._icerik(f"agents/{ad}.md")
            self.assertIn("kart mevcut", t, ad)
            for anahtar in ("okunan", "yetenekler", "karar", "etkilenenler"):
                self.assertIn(anahtar, t, f"{ad}: {anahtar}")

    def test_belge_calistir_js(self):
        t = self._icerik("workflows/calistir.js")
        i = t.index("KAPI_PROTOKOLU")
        self.assertIn("kart mevcut", t[i:])

    def test_belge_is_skill(self):
        t = self._icerik("skills/is/SKILL.md")
        self.assertIn("kart mevcut", t)
        self.assertIn("mevcut durum", t.lower())

    def test_belge_denetci_tutarlilik(self):
        t = self._icerik("agents/denetci.md").lower()
        self.assertIn("mevcut durum", t)
        self.assertIn("tutarl", t)

    def test_belge_kurallar(self):
        t = self._icerik("KURALLAR.md").lower()
        self.assertIn("mevcut durum", t)
        self.assertIn("kart mevcut", t)


if __name__ == "__main__":
    unittest.main()
