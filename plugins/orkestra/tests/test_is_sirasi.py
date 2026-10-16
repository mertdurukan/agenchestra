"""İş sırası (P-005): mevcut_durum_<gün>.md → plan.md → todo.md. Geçici projede koşar.

Kapı bu testlerde ORKESTRA_SIRA_KAPISI=1 ile açıkça kurulur (ic_kos varsayılanı '0').
"""
import datetime
import json
import os
import sys
import unittest

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
"""


def plan_metni(md_ad=MD_AD, dayanak="MD §3", ekstra=""):
    return (f"# Deneme: plan\n\n**Sıra:**\n\n[{md_ad}]({md_ad}) → bu plan → todo.md.\n\n## 4. Plan maddeleri\n\n"
            f"### P1 İlk madde\n\n**Dayanak:**\n\n{dayanak}\n\n### P2 İkinci madde\n\n**Dayanak:**\n\nMD §1\n{ekstra}\n"
            "## 5. Riskler\n\nYok.\n")


class IsSirasi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def cli(self, *args, kapi="1"):
        return TC.kos([TC.CLI, *args], self.proje, ortam={"ORKESTRA_SIRA_KAPISI": kapi})

    def hook_pre(self, dosya, icerik=None, arac="Write", yeni=None, kapi="1", eski="x"):
        girdi = {"file_path": dosya}
        if arac == "Write":
            girdi["content"] = icerik or ""
        else:
            girdi["old_string"] = eski
            girdi["new_string"] = yeni or ""
        g = {"session_id": TC.OTURUM, "cwd": self.proje, "transcript_path": self.ana_tr, "hook_event_name": "PreToolUse",
             "tool_name": arac, "tool_input": girdi}
        r = TC.kos([TC.HOOK, "PreToolUse"], self.proje, ortam={"ORKESTRA_SIRA_KAPISI": kapi}, stdin=json.dumps(g))
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


if __name__ == "__main__":
    unittest.main()
