"""Plan ✅/❌ doğrulama kapısı: iddia ayrıştırma, kanıt doğrulama, karar, CLI, şablon, todo kapısı.

Kapı bu testlerde ORKESTRA_DOGRULAMA_KAPISI=1 ile açıkça kurulur (ic_kos/conftest varsayılanı '0').
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import plan_dogrulama as PD  # noqa: E402
from test_is_sirasi import MD_AD  # noqa: E402

TAMAM, YOK = PD.TAMAM, PD.YOK
ORTAM = {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_DOGRULAMA_KAPISI": "1"}

KAYNAK = "def a():\n    return 1\n\nDEGER = 42\n"


def plan_metni(iddialar, maddeler, kok="."):
    return (f"# Deneme: plan\n\n[{MD_AD}]({MD_AD})\n\n**Kök:** {kok}\n\n## 2. İddialar\n\n{iddialar}\n\n## 4. Plan maddeleri\n\n{maddeler}\n"
            "## 5. Riskler\n\nYok.\n")


def madde(no, iddia="", kapatir="", dayanak="MD §3"):
    s = f"### P{no} Madde {no}\n\n**Ne:** iş.\n\n**Dayanak:** {dayanak}\n\n"
    if iddia:
        s += f"**İddialar:** {iddia}\n\n"
    if kapatir:
        s += f"**Kapatır:** {kapatir}\n\n"
    return s


class PlanDogrulamaBirim(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ork_pd_")
        os.makedirs(os.path.join(self.d, ".claude"))
        with open(os.path.join(self.d, "kaynak.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(KAYNAK)
        os.makedirs(os.path.join(self.d, "testler"))
        for ad in ("test_a.py", "test_b.py"):
            open(os.path.join(self.d, "testler", ad), "w").close()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def yaz(self, iddialar, maddeler, kok="."):
        yol = os.path.join(self.d, "plan.md")
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(plan_metni(iddialar, maddeler, kok))
        return yol

    def hesap(self, iddialar, maddeler="", **kw):
        yol = self.yaz(iddialar, maddeler or madde(1, "C1"), kok=kw.pop("kok", "."))
        return PD.degerlendir(yol, **kw)

    def isaret(self, sonuc, no=1):
        return next(c for c in sonuc["iddialar"] if c["no"] == no)["hesap"]

    # ------------------------------------------------------------ kanıt türleri
    def test_dosya_kaniti_satir_ve_alinti_tutarsa_onaylanir(self):
        s = self.hesap('- **C1** Dönüş 1.\n  - Kanıt: dosya kaynak.py:2 "return 1"')
        self.assertEqual(self.isaret(s), TAMAM)

    def test_dosya_kaniti_satir_kaymissa_reddedilir(self):
        s = self.hesap('- **C1** Dönüş 1.\n  - Kanıt: dosya kaynak.py:40 "return 1"\n  - Risk: yok')
        self.assertEqual(self.isaret(s), YOK)

    def test_dosya_kaniti_arti_eksi_iki_satir_hosgorulur(self):
        s = self.hesap('- **C1** Sabit.\n  - Kanıt: dosya kaynak.py:2 "DEGER = 42"')  # gerçek satır 4
        self.assertEqual(self.isaret(s), TAMAM)
        s = self.hesap('- **C1** Sabit.\n  - Kanıt: dosya kaynak.py:1 "DEGER = 42"\n  - Risk: kaymış')  # fark 3
        self.assertEqual(self.isaret(s), YOK)

    def test_kisa_alinti_ve_olmayan_dosya_reddedilir(self):
        for kanit in ('dosya kaynak.py:2 "a"', 'dosya yok.py:1 "return 1"'):
            s = self.hesap(f"- **C1** x.\n  - Kanıt: {kanit}\n  - Risk: r")
            self.assertEqual(self.isaret(s), YOK, kanit)

    def test_ara_ve_say_kaniti_yeniden_hesaplanir(self):
        s = self.hesap('- **C1** Bir kez geçer.\n  - Kanıt: ara "DEGER" kaynak.py => 1')
        self.assertEqual(self.isaret(s), TAMAM)
        s = self.hesap('- **C1** Hiç geçmez.\n  - Kanıt: ara "YOKTUR" kaynak.py => 0')
        self.assertEqual(self.isaret(s), TAMAM)
        s = self.hesap('- **C1** Yanlış sayı.\n  - Kanıt: ara "DEGER" kaynak.py => 3\n  - Risk: r')
        self.assertEqual(self.isaret(s), YOK)
        s = self.hesap("- **C1** İki test.\n  - Kanıt: say testler/test_*.py => 2")
        self.assertEqual(self.isaret(s), TAMAM)
        s = self.hesap("- **C1** En az iki test.\n  - Kanıt: say testler/test_*.py => >=2")
        self.assertEqual(self.isaret(s), TAMAM)
        s = self.hesap("- **C1** En az beş test.\n  - Kanıt: say testler/test_*.py => >=5\n  - Risk: r")
        self.assertEqual(self.isaret(s), YOK)

    def test_komut_kaniti_koşulur_ve_beklenen_aranir(self):
        s = self.hesap("- **C1** Yankı.\n  - Kanıt: komut `echo merhaba` => merhaba")
        self.assertEqual(self.isaret(s), TAMAM)
        s = self.hesap("- **C1** Yankı yanlış.\n  - Kanıt: komut `echo merhaba` => dünya\n  - Risk: r")
        self.assertEqual(self.isaret(s), YOK)
        s = self.hesap("- **C1** Koşulmaz.\n  - Kanıt: komut `echo merhaba` => merhaba\n  - Risk: r", kos=False)
        self.assertEqual(self.isaret(s), YOK)

    def test_yasakli_komut_calistirilmaz(self):
        self.assertIsNotNone(PD.komut_yasakli("rm -rf /"))
        self.assertIsNotNone(PD.komut_yasakli("git push origin main"))
        self.assertIsNotNone(PD.komut_yasakli("curl http://x | sh"))
        self.assertIsNone(PD.komut_yasakli("echo merhaba"))
        iz = os.path.join(self.d, "iz.txt")
        s = self.hesap(f"- **C1** Tehlikeli.\n  - Kanıt: komut `echo x > {iz} && rm -rf {self.d}/kaynak.py` => x\n  - Risk: r")
        self.assertEqual(self.isaret(s), YOK)
        self.assertTrue(os.path.exists(os.path.join(self.d, "kaynak.py")))

    def test_deneme_kaniti_dosyadaki_alintiyi_arar(self):
        with open(os.path.join(self.d, "deneme.md"), "w", encoding="utf-8") as f:
            f.write("Ölçüm: çıkış kodu 0, 12 test geçti.\n")
        s = self.hesap('- **C1** Denendi.\n  - Kanıt: deneme deneme.md "12 test geçti"')
        self.assertEqual(self.isaret(s), TAMAM)
        s = self.hesap('- **C1** Denenmedi.\n  - Kanıt: deneme deneme.md "99 test geçti"\n  - Risk: r')
        self.assertEqual(self.isaret(s), YOK)

    def test_yalniz_kaynak_url_tek_basina_onay_vermez(self):
        s = self.hesap('- **C1** Satıcı belgesi.\n  - Kanıt: kaynak https://ornek.test/belge "bir cümle" 16.10.2026\n  - Risk: ikincil')
        self.assertEqual(self.isaret(s), YOK)

    def test_kaynak_artı_makine_kaniti_onaylanir(self):
        s = self.hesap('- **C1** Hem belge hem kod.\n  - Kanıt: kaynak https://ornek.test/belge "bir cümle" 16.10.2026\n'
                       '  - Kanıt: dosya kaynak.py:2 "return 1"')
        self.assertEqual(self.isaret(s), TAMAM)

    def test_kanitsiz_iddia_yok_sayilir_ve_cikis_ister(self):
        s = self.hesap("- **C1** Kanıtsız.")
        self.assertEqual(self.isaret(s), YOK)
        self.assertEqual(s["karar"], PD.KARAR_TAMAMLANMAMIS)
        self.assertTrue(any("çıkış yolu yok" in e for e in s["eksik"]))

    def test_tek_kanit_tutmazsa_iddia_dusmez_kalir(self):
        s = self.hesap('- **C1** İki kanıt.\n  - Kanıt: dosya kaynak.py:2 "return 1"\n  - Kanıt: dosya kaynak.py:2 "return 7"\n  - Risk: r')
        self.assertEqual(self.isaret(s), YOK)  # tüm kanıtlar tutmalı

    # ------------------------------------------------------------ ayrıştırma
    def test_kod_blogu_ve_yorum_icindeki_iddia_sayilmaz(self):
        yol = self.yaz("```\n- **C7** Kod bloğu içinde.\n```\n<!-- - **C8** Yorum içinde. -->\n"
                       '- **C1** Gerçek.\n  - Kanıt: dosya kaynak.py:2 "return 1"', madde(1, "C1"))
        s = PD.degerlendir(yol)
        self.assertEqual([c["no"] for c in s["iddialar"]], [1])

    def test_onceki_isaret_yok_sayilir_hesap_yeniden_yapilir(self):
        s = self.hesap('- ❌ **C1** Yanlış işaretli.\n  - Kanıt: dosya kaynak.py:2 "return 1"')
        self.assertEqual(self.isaret(s), TAMAM)
        self.assertEqual(s["bayat"], ["C1"])

    def test_yinelenen_iddia_kimligi_eksiktir(self):
        s = self.hesap('- **C1** Bir.\n  - Kanıt: dosya kaynak.py:2 "return 1"\n- **C1** İki.\n  - Risk: r')
        self.assertTrue(any("iki kez tanımlı" in e for e in s["eksik"]))

    # ------------------------------------------------------------ karar
    def test_karar_uygulanabilir_koşullu_uygulanamaz(self):
        iyi = '- **C1** İyi.\n  - Kanıt: dosya kaynak.py:2 "return 1"'
        kotu = "- **C2** Kötü.\n  - Risk: ölçülmedi"
        s = self.hesap(iyi, madde(1, "C1"))
        self.assertEqual((s["karar"], s["engelli"]), (PD.KARAR_UYGULANABILIR, {}))
        s = self.hesap(iyi + "\n" + kotu, madde(1, "C1") + madde(2, "C2"))
        self.assertEqual(s["karar"], PD.KARAR_KOSULLU)
        self.assertEqual(s["engelli"], {2: [2]})
        self.assertEqual(s["engelsiz"], [1])
        s = self.hesap(kotu, madde(1, "C2"))
        self.assertEqual(s["karar"], PD.KARAR_UYGULANAMAZ)

    def test_kapatir_maddesi_engellenmez(self):
        kotu = "- **C2** Kötü.\n  - Spike: P2 dener"
        s = self.hesap(kotu, madde(1, "C2") + madde(2, kapatir="C2"))
        self.assertEqual(s["engelli"], {1: [2]})
        self.assertIn(2, s["engelsiz"])
        self.assertEqual(s["karar"], PD.KARAR_KOSULLU)

    def test_plan_maddesi_iddiasiz_ya_da_tanimsiz_iddiaya_bagliysa_tamamlanmamis(self):
        iyi = '- **C1** İyi.\n  - Kanıt: dosya kaynak.py:2 "return 1"'
        s = self.hesap(iyi, madde(1))
        self.assertEqual(s["karar"], PD.KARAR_TAMAMLANMAMIS)
        s = self.hesap(iyi, madde(1, "C1, C9"))
        self.assertTrue(any("C9 planda tanımlı değil" in e for e in s["eksik"]))

    def test_cikis_kodlari_karar_ile_eslesir(self):
        self.assertEqual(PD.CIKIS_KODU[PD.KARAR_UYGULANABILIR], 0)
        self.assertEqual(PD.CIKIS_KODU[PD.KARAR_KOSULLU], 1)
        self.assertEqual(PD.CIKIS_KODU[PD.KARAR_UYGULANAMAZ], 2)
        self.assertEqual(PD.CIKIS_KODU[PD.KARAR_TAMAMLANMAMIS], 3)

    # ------------------------------------------------------------ yazma
    def test_yaz_isaret_ve_karar_blogu_koyar_ikinci_yazim_degismez(self):
        yol = self.yaz('- **C1** İyi.\n  - Kanıt: dosya kaynak.py:2 "return 1"\n- **C2** Kötü.\n  - Risk: ölçülmedi',
                       madde(1, "C1") + madde(2, "C2"))
        PD.yaz(yol)
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        self.assertIn("- ✅ **C1**", metin)
        self.assertIn("- ❌ **C2**", metin)
        self.assertIn(PD.BLOK_BASLA, metin)
        self.assertIn("**Karar:** KOŞULLU", metin)
        self.assertIn("- Madde P2 ←", metin)
        ilk = metin
        PD.yaz(yol)
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(f.read().replace("\r\n", "\n").split("**Ölçüm saati:**")[0],
                             ilk.replace("\r\n", "\n").split("**Ölçüm saati:**")[0])
        b = PD.blok_oku(yol)
        self.assertTrue(b["guncel"])
        self.assertEqual(b["engelli"], [2])
        self.assertEqual(b["karar"], PD.KARAR_KOSULLU)

    def test_plan_degisince_ozet_bayatlar(self):
        yol = self.yaz('- **C1** İyi.\n  - Kanıt: dosya kaynak.py:2 "return 1"', madde(1, "C1"))
        PD.yaz(yol)
        self.assertTrue(PD.blok_oku(yol)["guncel"])
        with open(yol, "a", encoding="utf-8", newline="\n") as f:
            f.write("\nEk cümle.\n")
        self.assertFalse(PD.blok_oku(yol)["guncel"])

    def test_karar_blogu_ozeti_etkilemez(self):
        yol = self.yaz('- **C1** İyi.\n  - Kanıt: dosya kaynak.py:2 "return 1"', madde(1, "C1"))
        PD.yaz(yol)
        with open(yol, encoding="utf-8") as f:
            once = PD.ozet(f.read())
        PD.yaz(yol)  # blok yeniden yazılır, özet aynı kalır
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(PD.ozet(f.read()), once)

    def test_elle_degistirilen_isaret_ozeti_bozar(self):
        yol = self.yaz("- **C2** Kötü.\n  - Risk: ölçülmedi", madde(1, "C2"))
        PD.yaz(yol)
        self.assertTrue(PD.blok_oku(yol)["guncel"])
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin.replace("- ❌ **C2**", "- ✅ **C2**"))
        self.assertFalse(PD.blok_oku(yol)["guncel"])


class PlanDogrulamaUctanUca(unittest.TestCase):
    tearDown = TC.Cekirdek.tearDown

    def setUp(self):
        TC.Cekirdek.setUp(self)
        # Proje kökü `.claude` klasöründen bulunur; `baslat` durum klasörünü başka yere de yazabilir, kök işareti testte sabitlenir.
        os.makedirs(self.sd, exist_ok=True)
        # Kapı modu eklentinin gönderdiği ayara değil testin kendi ayarına bağlı: varsayılan gölge, ihlal testleri `ihlal_modu` ile değiştirir.
        with open(os.path.join(self.sd, "plan_dogrulama.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"mod": "golge"}, f)

    def cli(self, *args, ortam=None):
        return TC.kos([TC.CLI, *args], self.proje, ortam=dict(ORTAM, **(ortam or {})))

    def hook_pre(self, dosya, icerik, ortam=None):
        g = {"session_id": TC.OTURUM, "cwd": self.proje, "transcript_path": self.ana_tr, "hook_event_name": "PreToolUse",
             "tool_name": "Write", "tool_input": {"file_path": dosya, "content": icerik}}
        r = TC.kos([TC.HOOK, "PreToolUse"], self.proje, ortam=dict(ORTAM, **(ortam or {})), stdin=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def karar(self, cikti):
        return (cikti.get("hookSpecificOutput") or {}).get("permissionDecision")

    @staticmethod
    def yaz(yol, metin):
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def ac(self, *ek, alt="is1", ortam=None):
        klasor = os.path.join(self.proje, alt)
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor, *ek, ortam=ortam)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), klasor

    def is_json(self, klasor):
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            return json.load(f)

    def sirayi_tamamla(self, klasor):
        import test_is_sirasi as TS
        self.yaz(os.path.join(klasor, TS.MD_AD), TS.MD_TAMAM)

    def kaynak(self):
        self.yaz(os.path.join(self.proje, "kaynak.py"), KAYNAK)

    def plan(self, klasor, iddialar, maddeler):
        self.kaynak()
        self.yaz(os.path.join(klasor, "plan.md"), plan_metni(iddialar, maddeler))

    IYI = '- **C1** İyi.\n  - Kanıt: dosya kaynak.py:2 "return 1"'
    KOTU = "- **C2** Kötü.\n  - Risk: ölçülmedi"

    # ------------------------------------------------------------ is ac bayrağı ve şablon
    def test_yeni_sirali_is_bayrak_ve_dogrulamali_sablon_alir(self):
        i, klasor = self.ac()
        self.assertEqual(self.is_json(klasor).get("dogrulama"), PD.DOGRULAMA_ADI)
        self.sirayi_tamamla(klasor)
        r = self.cli("is", "belge", i, "plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(klasor, "plan.md"), encoding="utf-8") as f:
            plan = f.read()
        self.assertIn("**Kök:**", plan)
        self.assertIn("iddia", plan.lower())
        self.assertNotIn("{", plan)

    def test_dogrulamasiz_ve_kapali_kapi_eski_sablon(self):
        i, klasor = self.ac("--dogrulamasiz", alt="a")
        self.assertNotIn("dogrulama", self.is_json(klasor))
        self.sirayi_tamamla(klasor)
        self.cli("is", "belge", i, "plan")
        with open(os.path.join(klasor, "plan.md"), encoding="utf-8") as f:
            self.assertNotIn("**Kök:**", f.read())
        _, klasor2 = self.ac(alt="b", ortam={"ORKESTRA_DOGRULAMA_KAPISI": "0"})
        self.assertNotIn("dogrulama", self.is_json(klasor2))

    def test_sirasiz_is_bayrak_almaz(self):
        _, klasor = self.ac(alt="eski", ortam={"ORKESTRA_SIRA_KAPISI": "0"})
        self.assertNotIn("dogrulama", self.is_json(klasor))

    def test_sablon_plani_ham_haliyle_tamamlanmamis_sayilir(self):
        i, klasor = self.ac()
        self.sirayi_tamamla(klasor)
        self.cli("is", "belge", i, "plan")
        r = self.cli("plan", "dogrula", i)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("TAMAMLANMAMIŞ", r.stdout)

    # ------------------------------------------------------------ CLI
    def test_cli_cikis_kodu_ve_json(self):
        i, klasor = self.ac()
        self.plan(klasor, self.IYI, madde(1, "C1"))
        r = self.cli("plan", "dogrula", i)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("karar: UYGULANABİLİR", r.stdout)
        self.plan(klasor, self.IYI + "\n" + self.KOTU, madde(1, "C1") + madde(2, "C2"))
        r = self.cli("plan", "dogrula", i)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("engelli: P2", r.stdout)
        r = self.cli("plan", "dogrula", i, "--json")
        d = json.loads(r.stdout)
        self.assertEqual(d["karar"], "KOŞULLU")
        self.assertEqual({c["no"]: c["hesap"] for c in d["iddialar"]}, {1: TAMAM, 2: YOK})
        self.plan(klasor, self.KOTU, madde(1, "C2"))
        self.assertEqual(self.cli("plan", "dogrula", i).returncode, 2)

    def test_cli_yaz_isaret_koyar_ve_hedef_yol_olabilir(self):
        i, klasor = self.ac()
        self.plan(klasor, self.IYI, madde(1, "C1"))
        r = self.cli("plan", "dogrula", os.path.join(klasor, "plan.md"), "--yaz")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(klasor, "plan.md"), encoding="utf-8") as f:
            self.assertIn("- ✅ **C1**", f.read())

    def test_cli_komut_kosma_komut_kanitini_dusurur(self):
        i, klasor = self.ac()
        self.plan(klasor, "- **C1** Yankı.\n  - Kanıt: komut `echo merhaba` => merhaba\n  - Risk: r", madde(1, "C1"))
        self.assertEqual(self.cli("plan", "dogrula", i).returncode, 0)
        r = self.cli("plan", "dogrula", i, "--komut-kosma")
        self.assertEqual(r.returncode, 2, r.stdout)

    # ------------------------------------------------------------ todo kapısı
    def dogrulanmis(self, klasor, iddialar, maddeler):
        self.sirayi_tamamla(klasor)
        self.plan(klasor, iddialar, maddeler)
        self.assertIn(self.cli("plan", "dogrula", os.path.join(klasor, "plan.md"), "--yaz").returncode, (0, 1, 2, 3))

    def test_golge_modda_ihlal_yazimi_engellemez_gunluge_duser(self):
        i, klasor = self.ac()
        self.dogrulanmis(klasor, self.IYI + "\n" + self.KOTU, madde(1, "C1") + madde(2, "C2"))
        r = self.cli("is", "todo", i, "--ekle", "P2: engelli madde")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gölge", r.stderr)
        gunluk = os.path.join(self.sd, "gunluk.jsonl")
        self.assertTrue(os.path.exists(gunluk))
        with open(gunluk, encoding="utf-8") as f:
            satirlar = [json.loads(s) for s in f if "plan_dogrulama" in s]
        self.assertTrue(satirlar and satirlar[-1]["mod"] == "golge")

    def ihlal_modu(self):
        self.yaz(os.path.join(self.sd, "plan_dogrulama.json"), json.dumps({"mod": "ihlal"}))

    def test_ihlal_modunda_engelli_madde_reddedilir_spike_gecer(self):
        self.ihlal_modu()
        i, klasor = self.ac()
        self.dogrulanmis(klasor, self.IYI + "\n" + "- **C2** Kötü.\n  - Spike: P3 dener",
                         madde(1, "C1") + madde(2, "C2") + madde(3, kapatir="C2"))
        r = self.cli("is", "todo", i, "--ekle", "P2: engelli")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("❌ iddiaya dayanıyor", r.stderr)
        self.assertEqual(self.cli("is", "todo", i, "--ekle", "P1: engelsiz").returncode, 0)
        r = self.cli("is", "todo", i, "--ekle", "P3: spike")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ihlal_modunda_dogrulanmamis_ya_da_bayat_plan_todo_yazdirmaz(self):
        self.ihlal_modu()
        i, klasor = self.ac()
        self.sirayi_tamamla(klasor)
        self.plan(klasor, self.IYI, madde(1, "C1"))
        r = self.cli("is", "todo", i, "--ekle", "P1: x")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("plan doğrulaması yok", r.stderr)
        self.cli("plan", "dogrula", i, "--yaz")
        self.assertEqual(self.cli("is", "todo", i, "--ekle", "P1: x").returncode, 0)
        with open(os.path.join(klasor, "plan.md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\nplan sonradan değişti.\n")
        r = self.cli("is", "todo", i, "--ekle", "P1: y")
        self.assertEqual(r.returncode, 2)
        self.assertIn("güncel değil", r.stderr)

    def test_ihlal_modunda_tamamlanmamis_plan_todo_yazdirmaz(self):
        self.ihlal_modu()
        i, klasor = self.ac()
        self.dogrulanmis(klasor, "- **C1** Kanıtsız.", madde(1, "C1"))
        r = self.cli("is", "todo", i, "--ekle", "P1: x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("TAMAMLANMAMIŞ", r.stderr)

    def test_kapali_kapi_ihlal_modunda_bile_gecer(self):
        self.ihlal_modu()
        i, klasor = self.ac()
        self.dogrulanmis(klasor, self.KOTU, madde(1, "C2"))
        r = self.cli("is", "todo", i, "--ekle", "P1: x", ortam={"ORKESTRA_DOGRULAMA_KAPISI": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bayraksiz_is_kapidan_etkilenmez(self):
        self.ihlal_modu()
        i, klasor = self.ac("--dogrulamasiz")
        self.sirayi_tamamla(klasor)
        self.plan(klasor, self.KOTU, madde(1, "C2"))
        self.assertEqual(self.cli("is", "todo", i, "--ekle", "P1: x").returncode, 0)

    def test_hook_cli_ile_ayni_karari_verir(self):
        self.ihlal_modu()
        i, klasor = self.ac()
        self.dogrulanmis(klasor, self.IYI + "\n" + self.KOTU, madde(1, "C1") + madde(2, "C2"))
        todo = os.path.join(klasor, "todo.md")
        self.assertEqual(self.karar(self.hook_pre(todo, "- [ ] P2: engelli\n")), "deny")
        self.assertNotEqual(self.karar(self.hook_pre(todo, "- [ ] P1: engelsiz\n")), "deny")  # main hook sözleşmesi: izinli yazım "allow" ya da None döner
        self.assertNotEqual(self.karar(self.hook_pre(todo, "- [ ] P2: engelli\n", ortam={"ORKESTRA_DOGRULAMA_KAPISI": "0"})), "deny")  # main hook sözleşmesi: izinli yazım "allow" ya da None döner

    def test_golge_modda_hook_yazimi_engellemez(self):
        i, klasor = self.ac()
        self.dogrulanmis(klasor, self.IYI + "\n" + self.KOTU, madde(1, "C1") + madde(2, "C2"))
        todo = os.path.join(klasor, "todo.md")
        self.assertNotEqual(self.karar(self.hook_pre(todo, "- [ ] P2: engelli\n")), "deny")  # main hook sözleşmesi: izinli yazım "allow" ya da None döner

    def test_bozuk_is_json_kapiyi_sessiz_gecirir(self):
        self.ihlal_modu()
        i, klasor = self.ac()
        self.dogrulanmis(klasor, self.KOTU, madde(1, "C2"))
        self.assertFalse(PD.dogrulamali_mi(os.path.join(self.proje, "yok_klasor")))
        self.assertEqual(PD.todo_onkosulu(os.path.join(self.proje, "yok_klasor")), "")


if __name__ == "__main__":
    unittest.main()
