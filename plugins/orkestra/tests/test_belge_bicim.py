"""Ö3/Ö4 (I-020): okunacak belgelerde K-005 yazım anı kapısı ve K-003 Stop bağlantı kapısı, gölge ve ihlal modu.

Saf kurallar belge_bicim.py'de; kancalar geçici projede koşar (gerçek durum dizinine yazılmaz).
"""
import json
import os
import sys
import unittest

import test_cekirdek as TC

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import belge_bicim as BB  # noqa: E402

AYAR = BB.ayar_oku(None)

TEMIZ = """# Başlık

## Amaç

Kısa bir amaç cümlesi.

## Kararlar

- Birinci karar.
- İkinci karar.

**Neden:**

Tek etiket ayrı paragrafta.
"""

# 3. satır: iki etiket tek paragrafta; 5. satır: satır içi liste
IHLALLI = """# Başlık

**Amaç:** a **Neden:** b

Şunlar yapılacak: (a) bir, (b) iki, (c) üç.
"""


class Kurallar(unittest.TestCase):
    def tara(self, metin, ad="plan.md"):
        return BB.yazim_ihlalleri(metin, ad, AYAR)

    def test_temiz_metin_ihlalsiz(self):
        self.assertEqual(self.tara(TEMIZ), [])

    def test_coklu_etiket_ve_sikisik_liste_satir_numarasiyla(self):
        ih = self.tara(IHLALLI)
        self.assertEqual([(i["satir"], i["kural"]) for i in ih], [(3, "coklu_etiket"), (5, "sikisik_liste")])

    def test_noktalivirgul_ve_nokta_isareti_listesi(self):
        self.assertEqual(self.tara("a; b; c; d\n")[0]["kural"], "sikisik_liste")
        self.assertEqual(self.tara("x · y · z\n")[0]["kural"], "sikisik_liste")
        self.assertEqual(self.tara("tek; noktalı; virgül\n"), [])

    def test_uzun_paragraf_ve_todo_madde_siniri(self):
        uzun = "kelime " * 50  # 350 karakter
        self.assertEqual(self.tara(uzun)[0]["kural"], "uzun_paragraf")
        madde = "- " + "kelime " * 35  # ~245 karakter: paragraf sınırı altında, todo sınırı üstünde
        self.assertEqual(self.tara(madde, "plan.md"), [])
        self.assertEqual(self.tara(madde, "todo.md")[0]["kural"], "uzun_todo_madde")

    def test_kod_tablo_baslik_given_when_then_yok_sayilir(self):
        metin = ("## a; b; c\n\n| x ; y ; z | **A:** **B:** |\n|---|---|\n\n```\n**A:** **B:** a; b; c\n```\n\n"
                 "Given bir; When iki; Then üç; And dört\n")
        self.assertEqual(self.tara(metin), [])

    def test_satir_ici_kod_ve_baglanti_hedefi_sayilmaz(self):
        self.assertEqual(self.tara("Örnek `a; b; c` ve [x](<yol; ile; noktalı.md>) bağlantı.\n"), [])

    def test_bastirma_isareti(self):
        self.assertEqual(self.tara("a; b; c; d <!-- biçim-tamam -->\n"), [])

    def test_belge_adi_kalibi(self):
        k = AYAR["yazim_kapisi"]
        for ad in ("plan.md", "todo.md", "bulgu.md", "jira_onerisi.md", "rapor.md", "calisma_ozeti_20261016.md",
                   "a/b/rapor_20261016.md"):
            self.assertTrue(BB.belge_mi(ad, k), ad)
        for ad in ("README.md", "devir_ozeti.md", "plan.py", "planlama_notu.md", "sablonlar/plan.md",
                   ".claude/rules/orkestra_kurallari.md", "KURALLAR.md"):
            self.assertFalse(BB.belge_mi(ad, k), ad)

    def test_baglantisiz_belgeler(self):
        yol = os.path.join("C:\\", "p", "is1", "rapor.md")
        diger = os.path.join("C:\\", "p", "kod.py")
        self.assertEqual(BB.baglantisiz_belgeler([yol, diger], "bitti", AYAR), [yol.replace("\\", "/")])
        self.assertEqual(BB.baglantisiz_belgeler([yol], "rapor: [rapor.md](is1/rapor.md)", AYAR), [])
        self.assertEqual(BB.baglantisiz_belgeler([yol], "rapor: [r](<is 1/rapor.md>)", AYAR), [])
        self.assertEqual(BB.baglantisiz_belgeler([yol], "yalnız ad: rapor.md", AYAR), [yol.replace("\\", "/")])
        self.assertEqual(BB.baglantisiz_belgeler([yol, yol], "x", AYAR), [yol.replace("\\", "/")])  # tekrar yok

    def test_bozuk_ayar_varsayilana_duser(self):
        d = BB.ayar_oku("/yok/olan/dizin")
        self.assertEqual(BB.mod(d, "yazim_kapisi"), "ihlal")  # eklentinin gönderdiği ayar: ihlal (18.10.2026)
        self.assertEqual(BB.mod({"yazim_kapisi": {"mod": "saçma"}}, "yazim_kapisi"), "golge")


class Kancalar(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    hook = TC.Cekirdek.hook
    karar = TC.Cekirdek.karar
    kart = TC.Cekirdek.kart

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def ihlaller(self, kural):
        return [g for g in self.gunluk() if g.get("tur") == "kural_ihlal" and g.get("kural") == kural]

    def ayar_yaz(self, **kapilar):
        with open(os.path.join(self.sd, "belge_bicim.json"), "w", encoding="utf-8") as f:
            json.dump({k: {"mod": v} for k, v in kapilar.items()}, f)

    def yaz(self, ad, icerik, arac="Write", alan="content"):
        return self.hook("PreToolUse", {"tool_name": arac, "tool_input": {"file_path": os.path.join(self.proje, ad), alan: icerik}})

    def stop(self, yanit, dokunulan):
        satirlar = [{"type": "assistant", "timestamp": "2026-10-16T10:00:00Z",
                     "message": {"model": "claude-opus-5-5", "usage": {"input_tokens": 1, "output_tokens": 1},
                                 "content": [{"type": "tool_use", "name": "Write", "input": {"file_path": os.path.join(self.proje, d)}}
                                             for d in dokunulan]}}]
        with open(self.ana_tr, "w", encoding="utf-8", newline="\n") as f:
            for s in satirlar:
                f.write(json.dumps(s) + chr(10))
        return self.hook("Stop", {"last_assistant_message": yanit})

    # --- Ö4 yazım anı
    def test_golge_yazimi_engellemez_kayit_ve_uyari_dusurur(self):
        self.ayar_yaz(yazim_kapisi="golge")
        c = self.yaz("is1/plan.md", IHLALLI)
        self.assertIsNone(self.karar(c))
        self.assertIn("K-005", c["hookSpecificOutput"]["additionalContext"])
        self.assertIn("satır 3 coklu_etiket", c["hookSpecificOutput"]["additionalContext"])
        k = self.ihlaller("belge_bicim")
        self.assertEqual(len(k), 1, k)
        self.assertEqual((k[0]["mod"], k[0]["dosya"], k[0]["adet"]), ("golge", "is1/plan.md", 2))

    def test_temiz_ve_belge_olmayan_dosya_sessiz(self):
        self.assertEqual(self.yaz("is1/plan.md", TEMIZ), {})
        self.assertEqual(self.yaz("is1/notlar.md", IHLALLI), {})
        self.assertEqual(self.yaz("kod.py", "a; b; c; d"), {})
        self.assertEqual(self.ihlaller("belge_bicim"), [])

    def test_edit_ve_multiedit_parcasi_taranir(self):
        self.ayar_yaz(yazim_kapisi="golge")
        c = self.yaz("is1/todo.md", "a; b; c; d", arac="Edit", alan="new_string")
        self.assertIn("sikisik_liste", c["hookSpecificOutput"]["additionalContext"])
        c = self.hook("PreToolUse", {"tool_name": "MultiEdit", "tool_input": {
            "file_path": os.path.join(self.proje, "is1/rapor.md"), "edits": [{"old_string": "x", "new_string": "a; b; c; d"}]}})
        self.assertIn("sikisik_liste", c["hookSpecificOutput"]["additionalContext"])

    def test_ihlal_modunda_yazim_reddedilir_bastirma_gecer(self):
        self.ayar_yaz(yazim_kapisi="ihlal")
        c = self.yaz("is1/plan.md", IHLALLI)
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("satır 3 coklu_etiket", c["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(self.yaz("is1/plan.md", "a; b; c; d <!-- biçim-tamam -->\n"), {})
        self.assertEqual(self.ihlaller("belge_bicim")[0]["mod"], "ihlal")

    def test_biçim_kapisi_kilitli_test_kapisini_atlamaz(self):
        """Gölge uyarısı gec() çıkışına taşınır; sonraki ret kapıları (ana ajan alan kapısı) yine çalışır."""
        k = self.kart("--yazma", "is1/**")
        self.assertTrue(k)
        r = self.cli("kart", "durum", k, "isleniyor")
        self.assertEqual(r.returncode, 0, r.stderr)
        c = self.yaz("is1/plan.md", IHLALLI)
        self.assertEqual(self.karar(c), "deny", c)

    # --- Ö3 Stop
    def test_stop_golge_baglantisiz_belgeyi_kaydeder_bloklamaz(self):
        self.ayar_yaz(baglanti_kapisi="golge")
        c = self.stop("bitti", ["is1/rapor.md", "kod.py"])
        self.assertNotEqual(c.get("decision"), "block", c)
        k = self.ihlaller("belge_baglantisi_yok")
        self.assertEqual(len(k), 1, k)
        self.assertEqual((k[0]["mod"], k[0]["dosyalar"], k[0]["adet"]), ("golge", ["is1/rapor.md"], 1))

    def test_stop_baglantili_yanit_kayit_dusurmez(self):
        self.stop("rapor: [rapor.md](is1/rapor.md)", ["is1/rapor.md"])
        self.assertEqual(self.ihlaller("belge_baglantisi_yok"), [])

    def test_stop_ihlal_modunda_hook_gosterir_bloklamaz(self):
        self.ayar_yaz(baglanti_kapisi="ihlal")
        c = self.stop("bitti", ["is1/rapor.md"])
        self.assertNotEqual(c.get("decision"), "block", c)
        self.assertIn("rapor.md", c["systemMessage"])
        self.assertIn("(is1/rapor.md)", c["systemMessage"])

    def test_stop_belge_olmayan_dosya_ihlal_sayilmaz(self):
        self.stop("bitti", ["scripts/kod.py", "README.md", "is1/devir_ozeti.md"])
        self.assertEqual(self.ihlaller("belge_baglantisi_yok"), [])


if __name__ == "__main__":
    unittest.main()
