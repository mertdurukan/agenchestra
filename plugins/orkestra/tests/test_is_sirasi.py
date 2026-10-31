"""İş sırası (P-005): mevcut_durum_<gün>.md → plan.md → todo.md. Geçici projede koşar.

Kapı bu testlerde ORKESTRA_SIRA_KAPISI=1 ile açıkça kurulur (ic_kos varsayılanı '0').
"""
import datetime
import json
import os
import re
import sys
import unittest
import unittest.mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S  # noqa: E402

GUN = datetime.datetime.now().strftime("%Y%m%d")
MD_AD = f"mevcut_durum_{GUN}.md"

MD_TAMAM = """# Deneme: mevcut durum

**Amaç:**

Mevcut durumu göstermek.

**Ölçüm saati:**

16.10.2026 10:00 (yerel)

## 1. İstek ya da veri hangi yoldan geçiyor

- `a.py:10` isteği alır.

## 2. Bugünkü davranış ve çalışan korumalar

- Koruma yok (`a.py:20`).

## 3. Etki haritası

- `a.py:10` → alır → orta risk.

## 4. Git durumu

- main, temiz.

## 5. Bilinmeyenler

- Teyit gerekir: b.py.

## 6. Gap analizi

**Hedef durum:** Deneme hedefi.

- **G1:** hedef → mevcut (MD §1) → fark.
- **G2:** hedef → mevcut (MD §2) → fark.
"""


def plan_metni(md_ad=MD_AD, dayanak="MD §3", ekstra=""):
    return (f"# Deneme: plan\n\n**Sıra:**\n\n[{md_ad}]({md_ad}) → bu plan → todo.md.\n\n## 4. Plan maddeleri\n\n"
            f"### P1 İlk madde\n\n**Dayanak:**\n\n{dayanak}\n\n**Gap:** G1\n\n### P2 İkinci madde\n\n**Dayanak:**\n\nMD §1\n\n**Gap:** G2\n{ekstra}\n"
            "## 5. Riskler\n\nYok.\n")


def _golge_sabit(f):
    """Gölge davranışı sınanır: kapı modunu ayar varsayılanından bağımsız `golge`ye sabitler (ADR-0096)."""
    import functools
    from unittest import mock

    @functools.wraps(f)
    def sar(*a, **k):
        import kapi_mod as KM
        with mock.patch.object(KM, "mod", side_effect=lambda kapi, klasor=None: "golge"):
            return f(*a, **k)
    return sar


class IsSirasi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def cli(self, *args, kapi="1"):
        return TC.kos([TC.CLI, *args], self.proje, ortam={"ORKESTRA_SIRA_KAPISI": kapi, "ORKESTRA_KALITE_KAPISI": "0", "ORKESTRA_HARITA_KAPISI": "0"})

    def hook_pre(self, dosya, icerik=None, arac="Write", yeni=None, kapi="1", eski="x"):
        girdi = {"file_path": dosya}
        if arac == "Write":
            girdi["content"] = icerik or ""
        else:
            girdi["old_string"] = eski
            girdi["new_string"] = yeni or ""
        g = {"session_id": TC.OTURUM, "cwd": self.proje, "transcript_path": self.ana_tr, "hook_event_name": "PreToolUse",
             "tool_name": arac, "tool_input": girdi}
        r = TC.kos([TC.HOOK, "PreToolUse"], self.proje, ortam={"ORKESTRA_SIRA_KAPISI": kapi, "ORKESTRA_KALITE_KAPISI": "0", "ORKESTRA_HARITA_KAPISI": "0"}, stdin=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def ac(self, alt="is1", kapi="1"):
        klasor = os.path.join(self.proje, alt)
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor, kapi=kapi)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), klasor, r

    @staticmethod
    def yaz(yol, metin):
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def md_doldur(self, klasor):
        self.yaz(os.path.join(klasor, MD_AD), MD_TAMAM)

    def plan_doldur(self, klasor, **kw):
        self.yaz(os.path.join(klasor, "plan.md"), plan_metni(**kw))

    # ------------------------------------------------------------ is ac
    def test_is_ac_yalniz_mevcut_durum_iskeleti_yazar(self):
        i, klasor, r = self.ac()
        self.assertEqual(sorted(os.listdir(klasor)),
                         sorted([MD_AD, "oturumlar.md", "is.json", "is.json.lock"]) if os.path.exists(os.path.join(klasor, "is.json.lock"))
                         else sorted([MD_AD, "oturumlar.md", "is.json"]))
        self.assertFalse(os.path.exists(os.path.join(klasor, "plan.md")))
        self.assertFalse(os.path.exists(os.path.join(klasor, "todo.md")))
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["sira"], S.SIRA_ADI)
        self.assertEqual(r.stdout.strip(), i)  # stdout yalnız iş kimliği
        self.assertIn("P-005", r.stderr)
        with open(os.path.join(klasor, MD_AD), encoding="utf-8") as f:
            md = f.read()
        self.assertTrue(md.startswith("# Deneme işi: mevcut durum\n"))
        self.assertNotIn("{", md)
        self.assertEqual([n for n in range(1, 6) if f"## {n}." in md], [1, 2, 3, 4, 5])

    def test_iskelet_tamam_sayilmaz(self):
        _, klasor, _ = self.ac()
        eksik = S.mevcut_durum_eksikleri(klasor)
        self.assertEqual(len([e for e in eksik if e.endswith("boş")]), 6, eksik)  # 5 bölüm + Ölçüm saati
        self.assertTrue(any("Ölçüm saati" in e for e in eksik))

    def test_kapi_kapaliyken_eski_davranis(self):
        i, klasor, _ = self.ac("eski", kapi="0")
        self.assertTrue(os.path.exists(os.path.join(klasor, "plan.md")))
        self.assertTrue(os.path.exists(os.path.join(klasor, "todo.md")))
        self.assertFalse([a for a in os.listdir(klasor) if a.startswith("mevcut_durum")])
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            self.assertNotIn("sira", json.load(f))
        r = self.cli("is", "sira", i, kapi="0")
        self.assertIn("yok", r.stdout)

    # ------------------------------------------------------------ CLI ön koşulları
    def test_plan_ve_todo_mevcut_durum_olmadan_acilmaz(self):
        i, klasor, _ = self.ac()
        r = self.cli("is", "belge", i, "plan")
        self.assertEqual(r.returncode, 2)
        self.assertIn("P-005", r.stderr)
        self.assertIn("mevcut durum §1 boş", r.stderr)
        r = self.cli("is", "todo", i, "--ekle", "P1: x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("mevcut durum", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(klasor, "plan.md")))
        self.assertFalse(os.path.exists(os.path.join(klasor, "todo.md")))

    def test_mevcut_durum_tamamlaninca_plan_acilir_ve_baglanir(self):
        i, klasor, _ = self.ac()
        self.md_doldur(klasor)
        r = self.cli("is", "belge", i, "plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(klasor, "plan.md"), encoding="utf-8") as f:
            plan = f.read()
        self.assertIn(f"[{MD_AD}]({MD_AD})", plan)
        self.assertNotIn("{gun}", plan)
        # şablon planı henüz tamam değil: P maddesi yok
        self.assertIn("P<n>", " ".join(S.plan_eksikleri(klasor)))
        r = self.cli("is", "todo", i, "--ekle", "P1: x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan.md", r.stderr)

    def test_todo_satiri_plan_maddesine_baglanmali(self):
        i, klasor, _ = self.ac()
        self.md_doldur(klasor)
        self.plan_doldur(klasor)
        r = self.cli("is", "todo", i, "--ekle", "P1: ilk adım", "--ekle", "P2: ikinci adım")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("todo 0/2", r.stdout)
        for kotu, parca in (("P9: yok", "P9"), ("planı yok sayan madde", "P<n>:")):
            r = self.cli("is", "todo", i, "--ekle", kotu)
            self.assertEqual(r.returncode, 2, kotu)
            self.assertIn(parca, r.stderr)

    def test_todo_eklemede_ihlal_hicbir_sey_yazmaz(self):
        i, klasor, _ = self.ac()
        self.md_doldur(klasor)
        self.plan_doldur(klasor)
        self.cli("is", "todo", i, "--ekle", "P1: ilk")
        r = self.cli("is", "todo", i, "--bitti", "1", "--ekle", "P2: iyi", "--ekle", "P7: kötü")
        self.assertEqual(r.returncode, 2)
        with open(os.path.join(klasor, "todo.md"), encoding="utf-8") as f:
            todo = f.read()
        self.assertIn("- [ ] P1: ilk", todo)
        self.assertNotIn("P2: iyi", todo)

    def test_bitti_serbest(self):
        i, klasor, _ = self.ac()
        self.md_doldur(klasor)
        self.plan_doldur(klasor)
        self.cli("is", "todo", i, "--ekle", "P1: ilk")
        r = self.cli("is", "todo", i, "--bitti", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("todo 1/1", r.stdout)

    # ------------------------------------------------------------ is sira / devam / baglanti
    def test_is_sira_adimi_ve_eksikleri_gosterir(self):
        i, klasor, _ = self.ac()
        r = self.cli("is", "sira", i)
        self.assertIn(f"{i} sıra: mevcut_durum", r.stdout)
        self.assertIn("eksik: mevcut durum §1 boş", r.stdout)
        self.assertIn("plan: yok", r.stdout)
        self.md_doldur(klasor)
        self.assertIn("sıra: plan", self.cli("is", "sira", i).stdout)
        self.cli("is", "belge", i, "plan")
        self.plan_doldur(klasor)
        r = self.cli("is", "sira", i)
        self.assertIn("sıra: todo", r.stdout)
        self.assertNotIn("eksik:", r.stdout)

    def test_is_sira_ac_eski_isi_siraliya_cevirir(self):
        i, klasor, _ = self.ac("eski", kapi="0")
        r = self.cli("is", "sira", i)
        self.assertIn("sıra: yok", r.stdout)
        # eski işte plan ön koşulsuz yazılabilir
        # sıra kapısı sınanır: engel yok. Yazım anı bağlamı (ADR-0111) ayrı mekanizma, kendi testinde.
        with unittest.mock.patch.dict(os.environ, {"ORKESTRA_URETIM_ENJEKSIYON": "0"}):
            self.assertEqual(self.hook_pre(os.path.join(klasor, "plan.md"), "# a\n").get("hookSpecificOutput"), None)
        r = self.cli("is", "sira", i, "--ac")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sıra: mevcut_durum", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(klasor, MD_AD)))
        self.assertEqual(self.karar(self.hook_pre(os.path.join(klasor, "plan.md"), "# a\n")), "deny")

    def karar(self, cikti):
        return (cikti.get("hookSpecificOutput") or {}).get("permissionDecision")

    def test_is_devam_sirayi_gosterir(self):
        i, klasor, _ = self.ac()
        r = self.cli("is", "devam", i)
        self.assertIn("sıra: mevcut_durum — eksik: mevcut durum: `**Ölçüm saati:**` boş", r.stdout)
        self.assertNotIn("plan:", r.stdout)  # plan.md henüz yok

    def test_baglanti_ilk_satir_mevcut_durum(self):
        i, klasor, _ = self.ac()
        self.md_doldur(klasor)
        self.cli("is", "belge", i, "plan")
        self.yaz(os.path.join(klasor, "todo.md"), "- [ ] P1: x\n")
        satirlar = self.cli("is", "baglanti", i).stdout.splitlines()
        self.assertEqual(satirlar[0], f"mevcut durum: [{MD_AD}](is1/{MD_AD})")
        self.assertEqual(satirlar[1], "plan dosyası: [plan.md](is1/plan.md)")
        self.assertEqual(satirlar[2], "to-do dosyası: [todo.md](is1/todo.md)")

    # ------------------------------------------------------------ yazım anı kapısı (hook)
    def test_hook_plan_yazimi_mevcut_durum_tamam_olmadan_reddedilir(self):
        _, klasor, _ = self.ac()
        plan = os.path.join(klasor, "plan.md")
        c = self.hook_pre(plan, plan_metni())
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("P-005", c["hookSpecificOutput"]["permissionDecisionReason"])
        self.md_doldur(klasor)
        self.assertIsNone(self.karar(self.hook_pre(plan, plan_metni())))

    def test_hook_mevcut_durum_yazimi_serbest(self):
        _, klasor, _ = self.ac()
        self.assertIsNone(self.karar(self.hook_pre(os.path.join(klasor, MD_AD), MD_TAMAM)))

    def test_hook_todo_yazimi_plan_ve_satir_kuralina_bakar(self):
        _, klasor, _ = self.ac()
        todo = os.path.join(klasor, "todo.md")
        self.md_doldur(klasor)
        self.assertEqual(self.karar(self.hook_pre(todo, "- [ ] P1: x\n")), "deny")  # plan yok
        self.plan_doldur(klasor)
        self.assertIsNone(self.karar(self.hook_pre(todo, "# Yapılacaklar\n\n- [ ] P1: x\n- [x] P2: y\n")))
        self.assertEqual(self.karar(self.hook_pre(todo, "- [ ] P1: x\n- [ ] planı olmayan satır\n")), "deny")
        self.assertEqual(self.karar(self.hook_pre(todo, "- [ ] P5: x\n")), "deny")
        self.assertEqual(self.karar(self.hook_pre(todo, arac="Edit", yeni="- [x] serbest satır\n")), "deny")
        self.assertIsNone(self.karar(self.hook_pre(todo, arac="Edit", yeni="[x]")))  # onay kutusu satırı değil

    def test_hook_edit_satir_onekini_silince_reddedilir(self):
        _, klasor, _ = self.ac()
        todo = os.path.join(klasor, "todo.md")
        self.md_doldur(klasor)
        self.plan_doldur(klasor)
        self.yaz(todo, "- [ ] P1: x\n- [ ] P2: y\n")
        self.assertEqual(self.karar(self.hook_pre(todo, arac="Edit", eski="P1: x", yeni="x")), "deny")  # parça onay kutusu içermez
        self.assertEqual(self.karar(self.hook_pre(todo, arac="Edit", eski="P2: y", yeni="P9: y")), "deny")  # P9 planda yok
        self.assertIsNone(self.karar(self.hook_pre(todo, arac="Edit", eski="[ ] P1", yeni="[x] P1")))  # bitti işareti serbest
        self.assertIsNone(self.karar(self.hook_pre(todo, arac="Edit", eski="P2: y", yeni="P2: y2")))

    def test_hook_kapi_kapaliyken_ve_eski_iste_gecer(self):
        _, klasor, _ = self.ac()
        self.assertIsNone(self.karar(self.hook_pre(os.path.join(klasor, "plan.md"), "# a\n", kapi="0")))
        _, eski, _ = self.ac("eski", kapi="0")
        self.assertIsNone(self.karar(self.hook_pre(os.path.join(eski, "plan.md"), "# a\n")))
        # iş klasörü dışındaki plan.md etkilenmez
        self.assertIsNone(self.karar(self.hook_pre(os.path.join(self.proje, "baska", "plan.md"), "# a\n")))

    # ------------------------------------------------------------ saf doğrulama
    def test_mevcut_durum_eksik_turleri(self):
        _, klasor, _ = self.ac()
        yol = os.path.join(klasor, MD_AD)
        self.yaz(yol, MD_TAMAM)
        self.assertEqual(S.mevcut_durum_eksikleri(klasor), [])
        self.yaz(yol, MD_TAMAM.replace("16.10.2026 10:00 (yerel)", "<!-- doldur -->"))
        self.assertTrue(any("Ölçüm saati" in e for e in S.mevcut_durum_eksikleri(klasor)))
        self.yaz(yol, MD_TAMAM.replace("- `a.py:10` → alır → orta risk.", "Düz paragraf."))
        self.assertTrue(any("§3" in e and "madde" in e for e in S.mevcut_durum_eksikleri(klasor)))
        self.yaz(yol, MD_TAMAM.replace("## 5. Bilinmeyenler\n\n- Teyit gerekir: b.py.\n", ""))
        self.assertTrue(any("`## 5.` bölümü yok" in e for e in S.mevcut_durum_eksikleri(klasor)))

    def test_plan_eksik_turleri(self):
        _, klasor, _ = self.ac()
        self.md_doldur(klasor)
        self.plan_doldur(klasor)
        self.assertEqual(S.plan_eksikleri(klasor), [])
        self.plan_doldur(klasor, md_ad="baska.md")
        self.assertTrue(any("bağlantısı yok" in e for e in S.plan_eksikleri(klasor)))
        self.plan_doldur(klasor, dayanak="MD §9")
        self.assertTrue(any("P1" in e and "geçersiz" in e for e in S.plan_eksikleri(klasor)))
        self.plan_doldur(klasor, dayanak="yok")
        self.assertTrue(any("P1" in e and "dayanağı yok" in e for e in S.plan_eksikleri(klasor)))
        self.assertEqual(S.plan_maddeleri(klasor), {1, 2})

    def test_plan_ve_todo_yokken_diger_komutlar_hata_vermez(self):
        i, klasor, _ = self.ac()
        for args in (("is", "devir", i), ("is", "devam", i), ("is", "liste"), ("is", "rapor"), ("is", "rapor", i),
                     ("is", "baglanti", i), ("is", "todo-denetle"), ("is", "sira", i)):
            r = self.cli(*args)
            self.assertEqual(r.returncode, 0, f"{args}: {r.stderr}")
            self.assertNotIn("Traceback", r.stderr, args)
        with open(os.path.join(klasor, "devir.md"), encoding="utf-8") as f:
            self.assertIn("Todo: 0/0", f.read())
        import ozet
        liste = ozet._is_todolari(self.sd)
        self.assertEqual([(x["id"], x["biten"], x["toplam"]) for x in liste], [(i, 0, 0)])
        r = self.cli("is", "kapat", i)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_yonlendirme_yeni_isin_sirali_oldugunu_soyler(self):
        import is_yonlendirme as Y
        self.assertIn("P-005", Y.yonlendir([], None))


class GapAnalizi(unittest.TestCase):
    """P-017: gap analizi iki geçiş (MD §6 → plan kapsama). Doğrudan is_sirasi, geçici klasörde."""

    def setUp(self):
        import tempfile
        self.k = tempfile.mkdtemp()
        self.md = os.path.join(self.k, MD_AD)
        self.yaz_is(gap=True)
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(MD_TAMAM)
        self._eski = {a: os.environ.pop(a, None) for a in ("ORKESTRA_GAP_KAPISI", "ORKESTRA_SIRA_KAPISI")}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.k, ignore_errors=True)
        for ad, v in self._eski.items():
            os.environ.pop(ad, None)
            if v is not None:
                os.environ[ad] = v

    def yaz_is(self, gap=True):
        veri = {"sira": S.SIRA_ADI}
        if gap:
            veri["gap"] = True
        with open(os.path.join(self.k, "is.json"), "w", encoding="utf-8") as f:
            json.dump(veri, f)

    def yaz_md(self, metin):
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def plan(self, metin):
        with open(os.path.join(self.k, "plan.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def test_tam_plan_gecer(self):
        self.plan(plan_metni())
        self.assertEqual(S.mevcut_durum_eksikleri(self.k), [])
        self.assertEqual(S.plan_eksikleri(self.k), [])

    def test_birinci_gecis_gapsiz_mevcut_durum_eksik(self):
        self.yaz_md(MD_TAMAM.split("## 6. Gap analizi")[0])
        e = S.mevcut_durum_eksikleri(self.k)
        self.assertTrue(any("Gap analizi" in x for x in e), e)

    def test_birinci_gecis_bos_gap_bolumu_eksik(self):
        self.yaz_md(MD_TAMAM.split("## 6. Gap analizi")[0] + "## 6. Gap analizi\n\n<!-- doldur -->\n")
        self.assertTrue(any("G1" in x for x in S.mevcut_durum_eksikleri(self.k)))

    def test_ikinci_gecis_kapatilmayan_gap(self):
        self.plan(plan_metni().replace("**Gap:** G2", "**Gap:** G1"))
        e = S.plan_eksikleri(self.k)
        self.assertTrue(any(x.startswith("G2:") for x in e), e)

    def test_ikinci_gecis_kapsam_disi_gerekceli_gecer(self):
        self.plan(plan_metni(ekstra="\n## Gap kapsama\n\n- **G2** Kapsam dışı: bu işte yapılmayacak, ayrı iş.\n")
                  .replace("**Gap:** G2", "**Gap:** G1"))
        self.assertEqual(S.plan_eksikleri(self.k), [])

    def test_ikinci_gecis_kapsam_disi_gerekcesiz_eksik(self):
        self.plan(plan_metni(ekstra="\n## Gap kapsama\n\n- **G2** Kapsam dışı: -\n").replace("**Gap:** G2", "**Gap:** G1"))
        self.assertTrue(any(x.startswith("G2:") for x in S.plan_eksikleri(self.k)))

    def test_ikinci_gecis_hayalet_gap(self):
        self.plan(plan_metni().replace("**Gap:** G2", "**Gap:** G9"))
        e = S.plan_eksikleri(self.k)
        self.assertTrue(any("G9" in x and "yok" in x for x in e), e)

    def test_ikinci_gecis_gapsiz_madde(self):
        self.plan(plan_metni().replace("**Gap:** G2", ""))
        e = S.plan_eksikleri(self.k)
        self.assertTrue(any(x.startswith("P2:") and "Gap" in x for x in e), e)

    def test_bayraksiz_is_muaf(self):
        self.yaz_is(gap=False)
        self.yaz_md(MD_TAMAM.split("## 6. Gap analizi")[0])
        self.plan(plan_metni().replace("**Gap:** G1", "").replace("**Gap:** G2", ""))
        self.assertFalse(S.gapli_mi(self.k))
        self.assertEqual(S.mevcut_durum_eksikleri(self.k), [])
        self.assertEqual(S.plan_eksikleri(self.k), [])

    def test_kapi_env_ile_kapanir(self):
        os.environ["ORKESTRA_GAP_KAPISI"] = "0"
        self.assertFalse(S.gapli_mi(self.k))
        self.plan(plan_metni().replace("**Gap:** G2", ""))
        self.assertEqual(S.plan_eksikleri(self.k), [])

    def test_plan_dogrulama_karar_blogu_gap_kapsamasi_yazar(self):
        import plan_dogrulama as PD
        self.plan(plan_metni())
        sonuc = PD.degerlendir(os.path.join(self.k, "plan.md"))
        self.assertEqual(sonuc["gap"], {"toplam": 2, "eksik": 0})
        self.assertIn("**Gap kapsaması:** tam", PD.karar_blogu(sonuc, "x"))
        self.plan(plan_metni().replace("**Gap:** G2", "**Gap:** G1"))
        sonuc = PD.degerlendir(os.path.join(self.k, "plan.md"))
        self.assertEqual(sonuc["gap"]["eksik"], 1)
        self.assertTrue(any(e.startswith("gap kapsaması:") for e in sonuc["eksik"]))

    def test_is_ac_gap_bayragini_koyar(self):
        import is_kaydi as K
        with open(K.__file__, encoding="utf-8") as f:
            self.assertIn('kayit["gap"] = True', f.read())


class KaliteCitasi(unittest.TestCase):
    """P-018: belge çıtası (Özet, Kabul/Geri alma, kanıtlı todo, planla karşılaştıran çalışma özeti)."""

    def setUp(self):
        import tempfile
        self.k = tempfile.mkdtemp()
        self.md = os.path.join(self.k, MD_AD)
        self._eski = {a: os.environ.pop(a, None) for a in ("ORKESTRA_KALITE_KAPISI", "ORKESTRA_GAP_KAPISI", "ORKESTRA_SIRA_KAPISI")}
        with open(os.path.join(self.k, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"sira": S.SIRA_ADI, "kalite": True, "gap": True}, f)
        self.yaz(self.md, self.md_metni())
        self.yaz(os.path.join(self.k, "plan.md"), self.plan_metni())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.k, ignore_errors=True)
        for ad, v in self._eski.items():
            os.environ.pop(ad, None)
            if v is not None:
                os.environ[ad] = v

    @staticmethod
    def yaz(yol, metin):
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    @staticmethod
    def md_metni(ozet="Özet cümlesi burada."):
        return MD_TAMAM.replace("# Deneme: mevcut durum\n", f"# Deneme: mevcut durum\n\n## Özet\n\n{ozet}\n", 1)

    @staticmethod
    def plan_metni(ozet="Plan özeti burada.", kabul="**Kabul:** testler geçer\n\n**Geri alma:** git checkout\n"):
        p = plan_metni().replace("# Deneme: plan\n", f"# Deneme: plan\n\n## Özet\n\n{ozet}\n", 1)
        return p.replace("**Gap:** G1\n", f"**Gap:** G1\n\n{kabul}", 1).replace("**Gap:** G2\n", f"**Gap:** G2\n\n{kabul}", 1)

    @_golge_sabit

    def test_tam_set_gecer(self):
        self.assertEqual(S.mevcut_durum_eksikleri(self.k), [])
        self.assertEqual(S.plan_eksikleri(self.k), [])

    def test_mevcut_durumda_ozet_yok_ya_da_bos(self):
        self.yaz(self.md, MD_TAMAM)
        self.assertTrue(any("Özet" in e for e in S.mevcut_durum_eksikleri(self.k)))
        self.yaz(self.md, self.md_metni("<!-- doldur -->"))
        self.assertTrue(any("boş" in e for e in S.mevcut_durum_eksikleri(self.k)))

    def test_planda_ozet_kabul_geri_alma_zorunlu(self):
        self.yaz(os.path.join(self.k, "plan.md"), self.plan_metni(ozet="<!-- doldur -->"))
        self.assertTrue(any("plan: `## Özet`" in e for e in S.plan_eksikleri(self.k)))
        self.yaz(os.path.join(self.k, "plan.md"), self.plan_metni(kabul=""))
        e = S.plan_eksikleri(self.k)
        self.assertTrue(any(x.startswith("P1:") and "Kabul" in x for x in e), e)
        self.assertTrue(any(x.startswith("P2:") and "Geri alma" in x for x in e), e)

    def test_doldur_yer_tutucusu_bos_sayilir(self):
        self.yaz(os.path.join(self.k, "plan.md"), self.plan_metni(kabul="**Kabul:** <doldur>\n\n**Geri alma:** <doldur> sonra\n"))
        e = S.plan_eksikleri(self.k)
        self.assertTrue(any(x.startswith("P1:") and "Kabul" in x for x in e), e)
        self.assertTrue(any(x.startswith("P1:") and "Geri alma" in x for x in e), e)
        self.assertTrue(S.alan_dolu("**Kabul:** testler geçer; `<doldur>` kalmaz", "Kabul"))  # metin içi alıntı dolu sayılır
        self.assertFalse(S.alan_dolu("**Kabul:** `<doldur>`", "Kabul"))

    def test_todo_bitti_satiri_kanit_ister(self):
        planli = {1, 2}
        self.assertTrue(S.todo_satir_ihlalleri("- [x] P1: iş\n", planli, kanit=True))
        self.assertEqual(S.todo_satir_ihlalleri("- [x] P1: iş — 2026-10-19: kanıt: 98 test geçti\n", planli, kanit=True), [])
        self.assertEqual(S.todo_satir_ihlalleri("- [ ] P1: iş\n", planli, kanit=True), [])
        self.assertEqual(S.todo_satir_ihlalleri("- [x] P1: iş\n", planli, kanit=False), [])

    def test_todo_bitir_notsuz_reddedilir(self):
        import is_kaydi as K
        self.yaz(os.path.join(self.k, "todo.md"), "# Yapılacaklar\n\n- [ ] P1: iş\n")
        with self.assertRaises(ValueError):
            K.todo_bitir(self.k, "1")
        K.todo_bitir(self.k, "1", "kanıt: testler geçti")
        with open(os.path.join(self.k, "todo.md"), encoding="utf-8") as f:
            self.assertIn("[x] P1: iş — ", f.read())

    @_golge_sabit

    def test_calisma_ozeti_planla_karsilastirir(self):
        import importlib
        I = importlib.import_module("komutlar.isler")
        govde = ("# T: çalışma özeti\n\n## Özet\n\nBitti.\n\n**Ana bulgu:**\n\nBulgu var.\n\n"
                 "## Plana göre gerçekleşen\n\n- P1: yapıldı. Kanıt: x.\n- P2: yapıldı. Kanıt: y.\n- G1: kapandı.\n- G2: kapandı.\n")
        yol = os.path.join(self.k, "calisma_ozeti_20261019.md")
        self.yaz(yol, govde)
        self.assertIsNone(I._ozet_eksigi(self.k))
        self.yaz(yol, govde.replace("- G2: kapandı.\n", ""))
        self.assertIn("G2", I._ozet_eksigi(self.k))
        self.yaz(yol, govde.replace("- P2: yapıldı. Kanıt: y.\n", ""))
        self.assertIn("P2", I._ozet_eksigi(self.k))
        self.yaz(yol, govde.replace("## Özet\n\nBitti.\n\n", ""))
        self.assertIn("Özet", I._ozet_eksigi(self.k))

    def test_bayraksiz_is_ve_env_muaf(self):
        self.yaz(self.md, MD_TAMAM)
        os.environ["ORKESTRA_KALITE_KAPISI"] = "0"
        self.assertFalse(S.kaliteli_mi(self.k))
        self.assertFalse(any("Özet" in e for e in S.mevcut_durum_eksikleri(self.k)))
        del os.environ["ORKESTRA_KALITE_KAPISI"]
        with open(os.path.join(self.k, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"sira": S.SIRA_ADI}, f)
        self.assertFalse(S.kaliteli_mi(self.k))
        self.assertEqual(S.mevcut_durum_eksikleri(self.k), [])

    def test_is_ac_kalite_bayragini_koyar(self):
        import is_kaydi as K
        with open(K.__file__, encoding="utf-8") as f:
            self.assertIn('kayit["kalite"] = True', f.read())

    def test_todo_sablonu_bagli_ve_k005_duzeninde(self):
        import is_kaydi as K
        metin = K.sablon_metni(K.BELGE_TURLERI["todo"][0], "T")
        self.assertTrue(metin.startswith("# T: yapılacaklar"))


class PlanYazimRaporu(unittest.TestCase):
    """I-224: plan.md yazım anında planın tüm alan eksikleri tek iletide, düzeltme satırıyla verilir; ret koşulu değişmez."""

    TASLAK = ("# Deneme: plan\n\n## 4. Plan maddeleri\n\n### P1 İlk madde\n\n**Ne:** x\n\n"
              "### P2 İkinci madde\n\n**Dayanak:** MD §9\n\n## 5. Riskler\n\nYok.\n")

    def setUp(self):
        import tempfile
        self.k = tempfile.mkdtemp()
        self._eski = {a: os.environ.pop(a, None) for a in ("ORKESTRA_KALITE_KAPISI", "ORKESTRA_GAP_KAPISI", "ORKESTRA_SIRA_KAPISI",
                                                           "ORKESTRA_BIC_KAPISI")}
        self.is_json({"sira": S.SIRA_ADI, "kalite": True, "gap": True})
        KaliteCitasi.yaz(os.path.join(self.k, MD_AD), KaliteCitasi.md_metni())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.k, ignore_errors=True)
        for ad, v in self._eski.items():
            os.environ.pop(ad, None)
            if v is not None:
                os.environ[ad] = v

    def is_json(self, veri):
        with open(os.path.join(self.k, "is.json"), "w", encoding="utf-8") as f:
            json.dump(veri, f)

    def hook_yaz(self, icerik):
        """hook._sira_kapisi işlem içinde: (reddedildi mi, ret nedeni, bilgi bağlamı)."""
        import contextlib, io
        import hook
        yol = os.path.join(self.k, "plan.md")
        hook._BEKLEYEN_UYARI = ""
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            try:
                hook._sira_kapisi("Write", {"file_path": yol, "content": icerik}, yol)
            except SystemExit:
                o = json.loads(cikti.getvalue())
                return True, o["hookSpecificOutput"]["permissionDecisionReason"], ""
        return False, "", hook._BEKLEYEN_UYARI

    def test_k1_eski_davranis_tek_eksik_yeni_davranis_tum_eksikler(self):
        # Eski davranış: plan yazımında ön koşul tamamsa alan eksikleri hiç görünmezdi; ret yalnız bu yazımın getirdiği
        # `Mevcut varlık` hatasını (tek madde) gösterirdi. Kalanlar todo yazımında / plan dogrula'da parça parça çıkardı.
        self.assertEqual(S.plan_onkosulu(self.k), [])
        ret = ["P1: `yok` için aranan şey yazılmalı (`yok — <aranan>`)"]
        eski = S.mesaj(ret, "plan.md")
        self.assertNotIn("Kabul", eski)
        self.assertNotIn("Gap", eski)
        # Yeni davranış: aynı ret iletisi, diskte henüz olmayan yazılacak metnin tüm eksiklerini sıralı listeler.
        self.assertFalse(os.path.exists(os.path.join(self.k, "plan.md")))
        m = S.plan_yazim_mesaji(self.k, ret, self.TASLAK)
        self.assertTrue(m.startswith("plan.md yazılamaz (P-005"), m)
        self.assertLess(m.index("Ret nedeni (1):"), m.index("Diğer eksikler"))
        for parca in ("aranan şey", "bağlantısı yok", "P1: `MD §<k>` dayanağı yok", "P2: dayanak MD §9 geçersiz",
                      "plan: `## Özet` bölümü yok", "P1: `**Kabul:**`", "P2: `**Geri alma:**`", "P1: `**Gap:** G<n>`",
                      "P2: `**Gap:** G<n>`", "G1: hiçbir P", "G2: hiçbir P"):
            self.assertIn(parca, m)
        self.assertLessEqual(len(m), S.PLAN_MESAJ_SINIR)

    @_golge_sabit

    def test_k1_taslak_yazimi_reddedilmez_eksikler_bilgi_olarak_gelir(self):
        red, neden, bilgi = self.hook_yaz(self.TASLAK)
        self.assertFalse(red, neden)  # yeni sertlik yok: taslak plan yazılabilir
        self.assertIn("plan.md yazıldı", bilgi)
        for parca in ("dayanağı yok", "`## Özet`", "`**Kabul:**`", "`**Gap:** G<n>`", "G2: hiçbir P"):
            self.assertIn(parca, bilgi)
        self.assertIn("Bilgi, gölge kapı", bilgi)  # P-030 best in class gölgede: engellemez, yalnız bilgi
        self.assertIn("Alternatifler", bilgi)

    def test_k1_on_kosul_once_gelir_alan_eksikleri_ayni_iletide(self):
        KaliteCitasi.yaz(os.path.join(self.k, MD_AD), MD_TAMAM.replace("16.10.2026 10:00 (yerel)", ""))
        red, neden, _ = self.hook_yaz(self.TASLAK)
        self.assertTrue(red)
        self.assertLess(neden.index("Ölçüm saati"), neden.index("Diğer eksikler"))
        self.assertIn("`**Kabul:**`", neden)

    def test_k2_her_eksik_icin_duzeltme_satiri(self):
        m = S.plan_yazim_mesaji(self.k, [], self.TASLAK)
        satirlar = m.splitlines()
        maddeler = [i for i, s in enumerate(satirlar) if re.match(r"^\d+\. ", s)]
        self.assertGreaterEqual(len(maddeler), 10)
        for i in maddeler:
            self.assertTrue(satirlar[i + 1].startswith("   → "), satirlar[i:i + 2])
        for duzeltme in ("P1 altına yaz: `**Gap:** G1`", "P1 altına yaz: `**Kabul:** <ölçülebilir ölçüt>`",
                         "P2 altına yaz: `**Geri alma:**", "P1 altına yaz: `**Dayanak:** MD §3`", "`## Özet` ve 3-4 cümle",
                         "`- **G2:** Kapsam dışı: <gerekçe>`", "P1 altına yaz: `**Alternatifler:**`"):
            self.assertIn(duzeltme, m)

    def test_k2_uzun_ileti_sinirda_kesilir(self):
        cok = "".join(f"### P{n} Madde\n\n**Ne:** x\n\n" for n in range(1, 40))
        m = S.plan_yazim_mesaji(self.k, [], "# p\n\n## 4. Plan\n\n" + cok)
        self.assertLessEqual(len(m), S.PLAN_MESAJ_SINIR)
        self.assertRegex(m.splitlines()[-1], r"^\+\d+ eksik daha: orkestra plan dogrula")

    def test_k3_eksiksiz_plan_etkilenmez(self):
        self.is_json({"sira": S.SIRA_ADI, "kalite": True, "gap": True})
        os.environ["ORKESTRA_BIC_KAPISI"] = "0"
        tam = KaliteCitasi.plan_metni()
        self.assertEqual(S.plan_yazim_mesaji(self.k, [], tam), "")
        self.assertEqual(self.hook_yaz(tam), (False, "", ""))
        KaliteCitasi.yaz(os.path.join(self.k, "plan.md"), tam)
        self.assertEqual(S.plan_eksikleri(self.k), [])  # diskteki plan_eksikleri davranışı aynı

    def test_yazim_ani_metni_diskteki_plani_degistirmez(self):
        KaliteCitasi.yaz(os.path.join(self.k, "plan.md"), KaliteCitasi.plan_metni())
        os.environ["ORKESTRA_BIC_KAPISI"] = "0"
        self.assertTrue(S.plan_yazim_mesaji(self.k, [], self.TASLAK))
        self.assertEqual(S.plan_eksikleri(self.k), [])  # geçici metin sızmaz

    def test_kayit_dusmez(self):
        import kapi_mod as KM
        with unittest.mock.patch.object(KM, "kaydet") as k1, unittest.mock.patch.object(KM, "ret_kaydet") as k2:
            S.plan_yazim_mesaji(self.k, [], self.TASLAK)
        self.assertFalse(k1.called or k2.called)


if __name__ == "__main__":
    unittest.main()
