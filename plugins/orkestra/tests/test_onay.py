"""onay.py testleri: eşitleme, karar akışı, kurallar, hook bağlamı ve CLI duman testi."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
FIXTURE = os.path.join(AD, "fixtures", "ruya_20261013_1500.md")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, SCRIPTS)
import onay  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = self.t.name
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "ruya"))
        os.makedirs(os.path.join(self.sd, "onerilen_skill"))
        self.kural_dosyasi = os.path.join(self.proje, ".claude", "rules", "orkestra_kurallari.md")

    def tearDown(self):
        self.t.cleanup()

    def rapor(self, ad="ruya_20261013_1500.md", metin=None):
        yol = os.path.join(self.sd, "ruya", ad)
        if metin is None:
            shutil.copy(FIXTURE, yol)
        else:
            with open(yol, "w", encoding="utf-8") as f:
                f.write(metin)
        return yol

    def skill(self, ad, gerekce=True):
        d = os.path.join(self.sd, "onerilen_skill", ad)
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: " + ad + "\n---\nGövde")
        if gerekce:
            with open(os.path.join(d, "GEREKCE.md"), "w", encoding="utf-8") as f:
                f.write("Neden gerekli")
        return d

    def kayit(self, **kw):
        return onay.iste(self.sd, "Soru", "Metin", **kw)


class EsitleTest(Temel):
    def test_gercek_rapor_7_oneri_2_skill_ve_idempotent(self):
        self.rapor()
        onay.esitle(self.sd)
        k = onay.liste(self.sd)
        self.assertEqual(len(k), 9)
        self.assertTrue(all(x["tur"] == "perspektif" and x["durum"] == "bekliyor" for x in k))
        oneri = [x for x in k if "#oneri-" in x["anahtar"]]
        skill = [x for x in k if "#skill-" in x["anahtar"]]
        self.assertEqual((len(oneri), len(skill)), (7, 2))
        self.assertEqual(sorted(x["baslik"] for x in skill),
                         ["Skill adayı: hafiza-yol-dogrula", "Skill adayı: orkestra-kart-ozeti"])
        onay.esitle(self.sd)
        self.assertEqual(len(onay.liste(self.sd)), 9)

    def test_diff_bloklari_maddede_kalir_ve_baslik_kisa(self):
        self.rapor()
        onay.esitle(self.sd)
        m1 = next(x for x in onay.liste(self.sd) if x["anahtar"].endswith("#oneri-1"))
        self.assertIn("```diff", m1["metin"])
        self.assertIn("+**Diğer belgeler:**", m1["metin"])
        self.assertNotIn("2. `klibre-db.md`", m1["metin"])
        self.assertLessEqual(len(m1["baslik"]), 100)
        self.assertTrue(m1["baslik"].startswith("`klibre-ciktilar-dizini.md`"))
        m7 = next(x for x in onay.liste(self.sd) if x["anahtar"].endswith("#oneri-7"))
        self.assertNotIn("## 7", m7["metin"])
        self.assertNotIn("Skill adayları", m7["metin"])
        s1 = next(x for x in onay.liste(self.sd) if x["anahtar"].endswith("#skill-1"))
        self.assertIn("Tetik", s1["metin"])
        self.assertIn("ruya_20261013_1500.md", s1["anahtar"])

    def test_yeni_rapor_eskiyi_eskidi_yapar(self):
        self.rapor()
        onay.esitle(self.sd)
        eski = onay.liste(self.sd)[0]
        onay.karar_ver(self.sd, eski["id"], "ret")  # karar verilmiş olan eskimez
        self.rapor("ruya_20261014_0900.md", "# R\n\n## 6. Önerilen değişiklikler\n1. Yeni madde\n")
        onay.esitle(self.sd)
        k = onay.liste(self.sd)
        durumlar = {x["anahtar"]: x["durum"] for x in k}
        self.assertEqual(durumlar["perspektif:ruya_20261014_0900.md#oneri-1"], "bekliyor")
        self.assertEqual(durumlar[eski["anahtar"]], "reddedildi")
        eskiler = [x for x in k if x["durum"] == "eskidi"]
        self.assertEqual(len(eskiler), 8)
        self.assertIn("ruya_20261014_0900.md", eskiler[0]["gecmis"][-1]["not"])

    def _perspektif_raporu(self, ad, metin):
        d = os.path.join(self.sd, "perspektif")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ad), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def test_perspektif_klasoru_raporu_ayristirilir(self):
        self._perspektif_raporu("perspektif_20261014_0900.md", "# R\n\n## 6. Önerilen değişiklikler\n1. Yeni madde\n")
        onay.esitle(self.sd)
        self.assertEqual([x["anahtar"] for x in onay.liste(self.sd)],
                         ["perspektif:perspektif_20261014_0900.md#oneri-1"])

    def test_iki_klasorde_tarih_damgasi_en_yeniyi_secer(self):
        self.rapor("ruya_20261015_0900.md", "# R\n\n## 6. Önerilen değişiklikler\n1. Ruya maddesi\n")
        self._perspektif_raporu("perspektif_20261014_0900.md", "# R\n\n## 6. Önerilen değişiklikler\n1. Perspektif maddesi\n")
        onay.esitle(self.sd)
        self.assertEqual([x["anahtar"] for x in onay.liste(self.sd)], ["perspektif:ruya_20261015_0900.md#oneri-1"])
        # Önek alfabetik sırada ruya > perspektif iken yalnız damgaya bakılır: daha yeni perspektif kazanır.
        self._perspektif_raporu("perspektif_20261016_0800.md", "# R\n\n## 6. Önerilen değişiklikler\n1. Daha yeni\n")
        onay.esitle(self.sd)
        durum = {x["anahtar"]: x["durum"] for x in onay.liste(self.sd)}
        self.assertEqual(durum["perspektif:perspektif_20261016_0800.md#oneri-1"], "bekliyor")
        self.assertEqual(durum["perspektif:ruya_20261015_0900.md#oneri-1"], "eskidi")

    def test_perspektif_hata_raporu_yok_sayilir(self):
        self._perspektif_raporu("perspektif_hata_20261014.md", "## 1. Önerilen değişiklikler\n1. x\n")
        onay.esitle(self.sd)
        self.assertEqual(onay.liste(self.sd), [])

    def test_hata_raporu_yok_sayilir(self):
        self.rapor("ruya_hata_20261014.md", "## 1. Önerilen değişiklikler\n1. x\n")
        onay.esitle(self.sd)
        self.assertEqual(onay.liste(self.sd), [])

    def test_skill_klasoru_eslenir_ve_kurulu_olan_atlanir(self):
        self.skill("docx-donusum")
        self.skill("zaten-var")
        os.makedirs(os.path.join(self.proje, ".claude", "skills", "zaten-var"))
        onay.esitle(self.sd)
        onay.esitle(self.sd)
        k = onay.liste(self.sd, tur="skill")
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["baslik"], "Skill önerisi: docx-donusum")
        self.assertEqual(k[0]["anahtar"], "skill:docx-donusum")
        self.assertEqual(k[0]["metin"], "Neden gerekli\n\n---\n\n---\nname: docx-donusum\n---\nGövde")

    def test_oneri_kural_icin_onay_kaydi(self):
        os.makedirs(os.path.join(self.sd, "kurallar"))
        with open(os.path.join(self.sd, "kurallar", "kurallar.json"), "w", encoding="utf-8") as f:
            json.dump({"kurallar": [{"id": "K-002", "metin": "X yap", "neden": "", "durum": "oneri",
                                     "kaynak": "cli", "olusturma": "2026-10-13T10:00:00+03:00",
                                     "guncelleme": "2026-10-13T10:00:00+03:00", "gecmis": []}]}, f)
        onay.esitle(self.sd)
        onay.esitle(self.sd)
        k = onay.liste(self.sd, tur="kural")
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["anahtar"], "kural:K-002")


class KararTest(Temel):
    def test_iste_ve_anahtar_tekil(self):
        a = self.kayit(anahtar="x:1")
        b = self.kayit(anahtar="x:1")
        self.assertEqual(a["id"], "O-001")
        self.assertEqual(a["id"], b["id"])
        c = self.kayit()
        self.assertEqual(c["id"], "O-002")
        self.assertEqual(c["tur"], "karar")
        self.assertEqual(c["durum"], "bekliyor")

    def test_gecisler_ve_hatalar(self):
        k = self.kayit()
        with self.assertRaises(ValueError):
            onay.karar_ver(self.sd, k["id"], "belki")
        r = onay.karar_ver(self.sd, k["id"], "onay", not_="olur", kim="cli")
        self.assertEqual(r["durum"], "onaylandi")
        self.assertEqual(r["karar"]["kim"], "cli")
        with self.assertRaisesRegex(ValueError, "bekliyor"):
            onay.karar_ver(self.sd, k["id"], "ret")
        with self.assertRaises(ValueError):
            onay.karar_ver(self.sd, "O-099", "ret")
        r = onay.al(self.sd, k["id"], "s1")
        self.assertEqual(r["durum"], "uygulaniyor")
        self.assertEqual(r["uygulama"]["oturum"], "s1")
        r = onay.uygulandi(self.sd, k["id"], "bitti")
        self.assertEqual((r["durum"], r["uygulama"]["ozet"], r["uygulama"]["oturum"]), ("uygulandi", "bitti", "s1"))
        with self.assertRaises(ValueError):
            onay.iptal(self.sd, k["id"], "geç")
        k2 = self.kayit()
        self.assertEqual(onay.karar_ver(self.sd, k2["id"], "ret")["durum"], "reddedildi")
        k3 = self.kayit()
        self.assertEqual(onay.iptal(self.sd, k3["id"], "gereksiz")["durum"], "iptal")
        self.assertEqual(onay.goster(self.sd, k3["id"])["gecmis"][-1]["olay"], "iptal")
        self.assertIsNone(onay.goster(self.sd, "O-404"))

    def test_secenekli_karar(self):
        k = self.kayit(secenekler=["A", "B"])
        with self.assertRaisesRegex(ValueError, "seçim"):
            onay.karar_ver(self.sd, k["id"], "onay")
        with self.assertRaisesRegex(ValueError, "geçersiz seçim"):
            onay.karar_ver(self.sd, k["id"], "onay", secim="C")
        r = onay.karar_ver(self.sd, k["id"], "onay", secim="B")
        self.assertEqual(r["karar"]["secim"], "B")
        k2 = self.kayit(secenekler=["A", "B"])
        self.assertEqual(onay.karar_ver(self.sd, k2["id"], "ret")["durum"], "reddedildi")

    def test_al_cakismasi(self):
        k = self.kayit()
        with self.assertRaises(ValueError):
            onay.al(self.sd, k["id"], "s1")  # henüz onaylanmadı
        onay.karar_ver(self.sd, k["id"], "onay")
        onay.al(self.sd, k["id"], "s1")
        with self.assertRaisesRegex(ValueError, "s1"):
            onay.al(self.sd, k["id"], "s2")
        self.assertEqual(onay.al(self.sd, k["id"], "s1")["durum"], "uygulaniyor")

    def test_liste_sirasi_ve_sayac(self):
        a = self.kayit()
        b = self.kayit()
        c = onay.iste(self.sd, "Perspektif", "m", tur="perspektif")
        onay.karar_ver(self.sd, a["id"], "onay")
        sirali = onay.liste(self.sd)
        self.assertEqual(sirali[-1]["id"], a["id"])
        self.assertEqual({x["id"] for x in sirali[:2]}, {b["id"], c["id"]})
        self.assertEqual(len(onay.liste(self.sd, durum="bekliyor", tur="karar")), 1)
        s = onay.sayac(self.sd)
        self.assertEqual((s["bekliyor"], s["uygulanacak"]), (2, 1))
        self.assertEqual((s["tur"]["karar"], s["tur"]["perspektif"]), (1, 1))
        onay.al(self.sd, a["id"], "s")
        self.assertEqual(onay.sayac(self.sd)["uygulanacak"], 1)


class KuralTest(Temel):
    def test_oneri_onayi_dosyayi_yazar_ve_kaldirinca_silinir(self):
        r = onay.kural_oner(self.sd, "Sır yazma", "güvenlik", "oturum-1")
        self.assertEqual((r["id"], r["durum"]), ("K-001", "oneri"))
        self.assertFalse(os.path.exists(self.kural_dosyasi))
        k = onay.liste(self.sd, tur="kural")
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["anahtar"], "kural:K-001")
        onay.esitle(self.sd)
        self.assertEqual(len(onay.liste(self.sd, tur="kural")), 1)  # yeniden açmaz
        s = onay.karar_ver(self.sd, k[0]["id"], "onay")
        self.assertEqual(s["durum"], "uygulandi")
        self.assertEqual(s["uygulama"]["ozet"], "panelde etkinleştirildi")
        self.assertEqual(onay.kurallar(self.sd)[0]["durum"], "etkin")
        with open(self.kural_dosyasi, encoding="utf-8") as f:
            icerik = f.read()
        tarih = onay.kurallar(self.sd)[0]["olusturma"][:10]
        self.assertEqual(icerik.splitlines()[0], "# Orkestra kuralları (panelden yönetilir)")
        self.assertIn("Bu dosya Orkestra panelinden üretilir; elle düzenleme, panelde Kurallar sayfasını kullan.", icerik)
        self.assertIn(f"- Sır yazma (K-001, {tarih})\n  - Neden: güvenlik\n", icerik)
        onay.kural_kaldir(self.sd, "K-001", "artık gerekmiyor")
        self.assertFalse(os.path.exists(self.kural_dosyasi))
        self.assertEqual(onay.kurallar(self.sd)[0]["durum"], "kaldirildi")

    def test_ret_kurali_reddeder(self):
        onay.kural_oner(self.sd, "Kural", "", "cli")
        k = onay.liste(self.sd, tur="kural")[0]
        self.assertEqual(onay.karar_ver(self.sd, k["id"], "ret")["durum"], "reddedildi")
        self.assertEqual(onay.kurallar(self.sd)[0]["durum"], "reddedildi")
        self.assertFalse(os.path.exists(self.kural_dosyasi))

    def test_ekle_duzenle_ve_maskeleme(self):
        r = onay.kural_ekle(self.sd, "Adres a.b@example.com kullanma", "")
        self.assertEqual((r["durum"], r["kaynak"]), ("etkin", "panel"))
        self.assertNotIn("a.b@example.com", r["metin"])
        onay.kural_ekle(self.sd, "İkinci kural", "neden var")
        onay.kural_duzenle(self.sd, "K-002", "İkinci kural v2")
        with open(self.kural_dosyasi, encoding="utf-8") as f:
            icerik = f.read()
        self.assertIn("İkinci kural v2 (K-002", icerik)
        self.assertIn("  - Neden: neden var", icerik)
        self.assertNotIn("example.com", icerik)
        self.assertEqual(onay.kurallar(self.sd)[1]["gecmis"][-1]["metin"], "İkinci kural")
        onay.kural_kaldir(self.sd, "K-001", "x")
        self.assertTrue(os.path.exists(self.kural_dosyasi))
        onay.kural_kaldir(self.sd, "K-002", "x")
        self.assertFalse(os.path.exists(self.kural_dosyasi))
        with self.assertRaises(ValueError):
            onay.kural_ekle(self.sd, "   ", "")
        with self.assertRaises(ValueError):
            onay.kural_kaldir(self.sd, "K-001", "tekrar")
        with self.assertRaises(ValueError):
            onay.kural_duzenle(self.sd, "K-009", "x")

    def test_oneri_kaldirinca_onay_iptal_olur(self):
        onay.kural_oner(self.sd, "Kural", "", "cli")
        onay.kural_kaldir(self.sd, "K-001", "vazgeçtim")
        self.assertEqual(onay.liste(self.sd, tur="kural")[0]["durum"], "iptal")

    def test_gorunum_ve_kaynaklar(self):
        onay.kural_ekle(self.sd, "Etkin kural", "")
        onay.kural_oner(self.sd, "Önerilen kural", "", "cli")
        onay.kural_ekle(self.sd, "Kalkacak", "")
        onay.kural_kaldir(self.sd, "K-003", "x")
        with open(os.path.join(self.proje, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# P\n\n## Odak\nbir\n\n## Orkestra (sistem)\nkural metni\n\n## Git\nüç\n")
        with open(os.path.join(self.proje, ".claude", "rules", "db.md"), "w", encoding="utf-8") as f:
            f.write("DB kuralı " + "x" * 9000)
        g = onay.kural_gorunum(self.sd, self.proje)
        self.assertEqual([r["id"] for r in g["etkin"]], ["K-001"])
        self.assertEqual(g["oneriler"][0]["onay_id"], onay.liste(self.sd, tur="kural")[0]["id"])
        self.assertEqual([r["id"] for r in g["gecmis"]], ["K-003"])
        basliklar = [k["baslik"] for k in g["kaynaklar"]]
        self.assertEqual(basliklar, ["Orkestra (sistem)", "db.md"])
        self.assertEqual(g["kaynaklar"][0]["metin"], "kural metni")
        self.assertEqual(len(g["kaynaklar"][1]["metin"]), 8000)


class BaglamTest(Temel):
    def test_session_start(self):
        self.assertEqual(onay.baglam_metni(self.sd, "s1", "SessionStart"), "")
        a = onay.iste(self.sd, "Perspektif önerisi", "m", tur="perspektif")
        k = self.kayit(oturum="s1")
        b = self.kayit(oturum="s2")
        onay.karar_ver(self.sd, a["id"], "onay")
        onay.karar_ver(self.sd, k["id"], "onay")
        onay.karar_ver(self.sd, b["id"], "onay")
        self.kayit()
        m = onay.baglam_metni(self.sd, "s1", "SessionStart")
        self.assertIn("2 karar", m)
        self.assertIn(f"{a['id']} [perspektif] Perspektif önerisi", m)
        self.assertIn(k["id"], m)
        self.assertNotIn(b["id"], m)
        self.assertIn("/orkestra:onay ile uygula", m)
        self.assertIn("1 karar bekliyor (/onaylar)", m)
        self.assertLessEqual(len(m), 900)

    def test_session_start_900_ile_sinirli(self):
        for i in range(40):
            k = onay.iste(self.sd, "Çok uzun bir başlık " * 10, "m", tur="perspektif")
            onay.karar_ver(self.sd, k["id"], "onay")
        self.assertEqual(len(onay.baglam_metni(self.sd, "s1", "SessionStart")), 900)

    def test_user_prompt_submit_yeni_karar_yoksa_bos(self):
        self.assertEqual(onay.baglam_metni(self.sd, "s1", "UserPromptSubmit"), "")
        k = self.kayit(oturum="s1", secenekler=["A", "B"])
        self.assertEqual(onay.baglam_metni(self.sd, "s1", "UserPromptSubmit"), "")
        onay.karar_ver(self.sd, k["id"], "onay", secim="B", not_="acele değil")
        m = onay.baglam_metni(self.sd, "s1", "UserPromptSubmit")
        self.assertIn(f"{k['id']} kararın: B (not: acele değil)", m)
        self.assertEqual(onay.baglam_metni(self.sd, "s1", "UserPromptSubmit"), "")
        self.assertTrue(os.path.exists(os.path.join(self.sd, "onaylar", "gorulen.json")))

    def test_session_start_gecmisi_isaretler(self):
        eski = onay.iste(self.sd, "Eski karar", "m", tur="perspektif")
        onay.karar_ver(self.sd, eski["id"], "onay")
        self.assertIn(eski["id"], onay.baglam_metni(self.sd, "yeni", "SessionStart"))
        # SessionStart'ta söylenen/geçmiş karar UserPromptSubmit'te tekrarlanmaz
        self.assertEqual(onay.baglam_metni(self.sd, "yeni", "UserPromptSubmit"), "")
        # sonradan verilen karar yine gelir
        yeni = onay.iste(self.sd, "Yeni karar", "m", tur="perspektif")
        onay.karar_ver(self.sd, yeni["id"], "ret")
        m = onay.baglam_metni(self.sd, "yeni", "UserPromptSubmit")
        self.assertIn(yeni["id"], m)
        self.assertNotIn(eski["id"], m)
        # karar yokken ya da oturumsuzken sessizce geçer
        onay.gorulen_isaretle(self.sd, None)
        onay.gorulen_isaretle(os.path.join(self.proje, "yok", ".claude", "orkestra"), "x")

    def test_user_prompt_submit_oturum_ayrimi(self):
        k = self.kayit(oturum="s2")
        onay.karar_ver(self.sd, k["id"], "ret")
        self.assertEqual(onay.baglam_metni(self.sd, "s1", "UserPromptSubmit"), "")
        self.assertIn("kararın: ret", onay.baglam_metni(self.sd, "s2", "UserPromptSubmit"))
        p = onay.iste(self.sd, "Başlık", "m", tur="perspektif")
        onay.karar_ver(self.sd, p["id"], "onay")
        m = onay.baglam_metni(self.sd, "s1", "UserPromptSubmit")
        self.assertIn(f"{p['id']} [perspektif] onaylandı", m)
        self.assertLessEqual(len(m), 900)
        self.assertEqual(onay.baglam_metni(self.sd, "s1", "Bilinmeyen"), "")


class CliTest(Temel):
    def calistir(self, *args, ortam=None):
        env = dict(os.environ, PYTHONUTF8="1", CLAUDE_PROJECT_DIR=self.proje)
        env.pop("CLAUDE_SESSION_ID", None)
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        env.update(ortam or {})
        return ic_kos.kos([ORKESTRA, *args], cwd=self.proje, env=env)

    def test_onay_ve_kural_akisi(self):
        self.rapor()
        r = self.calistir("onay", "esitle")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.calistir("onay", "liste", "--json")
        self.assertEqual(len(json.loads(r.stdout)), 9)
        r = self.calistir("onay", "iste", "--baslik", "Hangisi?", "--metin", "m", "--secenek", "A", "--secenek", "B",
                          "--oturum", "s9")
        self.assertEqual(r.returncode, 0, r.stderr)
        oid = r.stdout.strip()
        self.assertRegex(oid, r"^O-\d{3}$")
        r = self.calistir("onay", "karar", oid, "--onay")
        self.assertEqual(r.returncode, 2)
        self.assertIn("seçim zorunlu", r.stderr)
        r = self.calistir("onay", "karar", oid, "--onay", "--secim", "A", "--not", "tamam")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.calistir("onay", "al", oid, "--oturum", "s9")
        self.assertIn("uygulaniyor", r.stdout)
        r = self.calistir("onay", "uygulandi", oid, "--ozet", "yapıldı")
        self.assertIn("uygulandi", r.stdout)
        r = self.calistir("onay", "goster", oid)
        k = json.loads(r.stdout)
        self.assertEqual((k["durum"], k["karar"]["kim"], k["karar"]["secim"]), ("uygulandi", "cli", "A"))
        r = self.calistir("onay", "liste", "--durum", "uygulandi")
        self.assertIn(oid, r.stdout)
        r = self.calistir("onay", "iptal", "O-001", "--not", "gereksiz")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.calistir("onay", "goster", "O-999")
        self.assertEqual(r.returncode, 2)

        r = self.calistir("kural", "ekle", "--metin", "Hep Türkçe yaz", "--neden", "tercih")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(self.kural_dosyasi))
        r = self.calistir("kural", "oner", "--metin", "Başka kural")
        self.assertIn("K-002", r.stdout)
        r = self.calistir("kural", "duzenle", "K-001", "--metin", "Hep Türkçe yaz!")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.calistir("kural", "liste", "--json")
        self.assertEqual([x["id"] for x in json.loads(r.stdout)], ["K-001", "K-002"])
        r = self.calistir("kural", "kaldir", "K-001", "--not", "bitti")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.kural_dosyasi))
        r = self.calistir("kural", "liste")
        self.assertIn("kaldirildi", r.stdout)

    def test_mevcut_komutlar_calismaya_devam_eder(self):
        r = self.calistir("kart", "liste")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
