"""Mühendislik kontrolü (ADR-0179): doğrulama planı (T), kanıt kaydı (E), bayatlık, eval alanları, üç kapı kararı ve
kapanış gölge kaydı. Fikstür iş: G1-G2 → P1-P2 → S1-S2 → T1-T2; kapsam dosyası proje kökünde `src/a.py`."""
import json
import os
import sys
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S  # noqa: E402
import muhendislik_kontrol as MK  # noqa: E402

PY = '"' + sys.executable.replace("\\", "/") + '"'

MD = """# Deneme: mevcut durum

## 1. Kapsam

- deneme

## 2. Bulgular

- bulgu

## 3. Etki haritası

- src/a.py

## 4. Kısıtlar

- yok

## 5. Gap analizi

- **G1:** hedef bir → mevcut → fark
- **G2:** hedef iki → mevcut → fark

## Yol kararı

- yeni yol seçildi
"""

SOZ = """# Deneme: sözleşme

## Problem

- Zincir kopuk.

## Başarı kriterleri

- **S1:** birinci kriter
- **S2:** ikinci kriter

## Kapsam dışı

- yok

## Kısıtlar

- yok
{sonuc}"""

PLAN = """# Deneme: plan

## 4. Plan maddeleri

### P1 Birinci
**Gap:** G1
**Sözleşme:** S1
**Yazma alanı:** src/a.py

### P2 İkinci
**Gap:** G2
**Sözleşme:** S2
**Yazma alanı:** src/b.py

## Doğrulama planı

{tler}

## Best in class denetimi

{denetci}
"""

T_IKI = ("- **T1:** S1 — birinci — Komut: `{py} -c \"import sys; sys.exit(0)\"`\n"
         "- **T2:** S2 — ikinci — Komut: `{py} -c \"import sys; sys.exit(0)\"`").format(py=PY)

TODO_BITTI = "- [x] P1 Birinci — 2026-11-12: pytest geçti\n- [x] P2 İkinci — 2026-11-12: pytest geçti\n"
OZET = "# Özet\n\n**Ne yapıldı?**\n\n- zincir kuruldu\n"


class Fikstur(unittest.TestCase):
    """Testler ve test_belge_gorunum için ortak sıralı iş fikstürü (Cekirdek'in testleri miras alınmaz)."""

    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def is_kur(self, kademe=None, tler=T_IKI, todo=TODO_BITTI, sonuc="", ozet=True, denetci="", ad="001-edel"):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", ad)
        os.makedirs(k, exist_ok=True)
        kayit = {"id": "I-001", "sira": S.SIRA_ADI, "baslik": "Deneme"}
        if kademe:
            kayit["kademe"] = kademe
        self.yaz(k, "is.json", json.dumps(kayit))
        self.yaz(k, "mevcut_durum_20261112.md", MD)
        self.yaz(k, "sozlesme_20261112.md", SOZ.format(sonuc=sonuc))
        self.yaz(k, "plan.md", PLAN.format(tler=tler, denetci=denetci))
        if todo is not None:
            self.yaz(k, "todo.md", todo)
        if ozet:
            self.yaz(k, "calisma_ozeti_20261112.md", OZET)
        self.yaz(self.proje, os.path.join("src", "a.py"), "A = 1\n")
        self.yaz(self.proje, os.path.join("src", "b.py"), "B = 1\n")
        return k

    @staticmethod
    def yaz(kok, ad, metin):
        yol = os.path.join(kok, ad)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)

    @staticmethod
    def eksik(r, kapi, kontrol=None):
        kp = r["kapilar"][int(kapi) - 1]
        return [e["mesaj"] for e in kp["eksikler"] if kontrol is None or e["kontrol"] == kontrol]


class DogrulamaPlani(Fikstur):
    def test_dogrulama_t_satiri_ayristirilir(self):
        tler = MK.dogrulama_plani(
            "## Doğrulama planı\n\n- **T1:** S1, S3 — açıklama — Komut: `pytest -q` — Kapsam: `src/*.py, lib/x.py`\n"
            "- **T2:** S2 — dış servis — Engel: VPN yok\n- **T3:** S2 — model — Eval: — Komut: `python e.py`\n")
        self.assertEqual(tler[1]["s"], [1, 3])
        self.assertEqual(tler[1]["komut"], "pytest -q")
        self.assertEqual(tler[1]["kapsam"], ["src/*.py", "lib/x.py"])
        self.assertEqual(tler[2]["engel"], "VPN yok")
        self.assertEqual(tler[2]["komut"], "")
        self.assertTrue(tler[3]["eval"])
        self.assertFalse(tler[1]["eval"])

    def test_dogrulama_yorumdaki_ornek_sayilmaz(self):
        self.assertEqual(MK.dogrulama_plani("## Doğrulama planı\n\n<!-- - **T1:** S1 — x — Komut: `a` -->\n"), {})

    def test_dogrulama_tsiz_s_reddedilir(self):
        k = self.is_kur(tler="- **T1:** S1 — yalnız biri — Komut: `{} -c \"pass\"`".format(PY))
        r = MK.kontrol(k)
        self.assertEqual(r["kapilar"][0]["sonuc"], "FAIL")
        self.assertIn("S2: doğrulama planında T yok", self.eksik(r, 1, "t_s_kapsama"))

    def test_dogrulama_olmayan_s_anan_t_reddedilir(self):
        k = self.is_kur(tler=T_IKI + "\n- **T3:** S9 — hayalet — Komut: `{} -c \"pass\"`".format(PY))
        self.assertIn("T3: S9 sözleşmede yok", self.eksik(MK.kontrol(k), 1, "t_s_kapsama"))

    def test_dogrulama_plani_yoksa_kapi1_fail(self):
        k = self.is_kur(tler="")
        r = MK.kontrol(k)
        self.assertEqual(r["kapilar"][0]["sonuc"], "FAIL")
        self.assertTrue(self.eksik(r, 1, "dogrulama_plani"))

    def test_dogrulama_komutsuz_t_reddedilir(self):
        k = self.is_kur(tler="- **T1:** S1 — komutsuz\n- **T2:** S2 — x — Komut: `{} -c \"pass\"`".format(PY))
        self.assertIn("T1: `Komut:` yok", self.eksik(MK.kontrol(k), 1, "dogrulama_plani"))


class KanitKaydi(Fikstur):
    def test_kanit_basarili_kayit_alanlari(self):
        k = self.is_kur()
        e = MK.kanit_al(k, 1)
        self.assertEqual((e["e"], e["t"], e["cikis"]), ("E1", "T1", 0))
        for alan in ("zaman", "komut", "sure_sn", "cikti_sha256", "kok", "kapsam", "kapsam_imza"):
            self.assertIn(alan, e)
        self.assertEqual(e["kapsam"], ["src/a.py"])
        self.assertEqual(e["kapsam_dosya"], 1)
        self.assertEqual(len(MK.kanitlar(k)), 1)

    def test_kanit_basarisiz_komut_kapi3_fail(self):
        k = self.is_kur(tler=T_IKI.replace("sys.exit(0)", "sys.exit(3)", 1))
        e = MK.kanit_al(k, 1)
        self.assertEqual(e["cikis"], 3)
        MK.kanit_al(k, 2)
        r = MK.kontrol(k)
        self.assertEqual(r["kapilar"][2]["sonuc"], "FAIL")
        self.assertIn("T1: son kanıt E1 çıkış 3", self.eksik(r, 3, "kanit_gecti"))

    def test_kanit_plan_disi_t_ve_engelli_t_reddedilir(self):
        k = self.is_kur(tler=T_IKI + "\n- **T3:** S2 — dış — Engel: servis kapalı")
        with self.assertRaises(ValueError):
            MK.kanit_al(k, 9)
        with self.assertRaises(ValueError):
            MK.kanit_al(k, 3)

    def test_kanit_yasakli_komut_kosulmaz(self):
        k = self.is_kur(tler="- **T1:** S1 — x — Komut: `echo a > b.txt`\n- **T2:** S2 — y — Komut: `{} -c \"pass\"`".format(PY))
        with self.assertRaises(ValueError):
            MK.kanit_al(k, 1)
        self.assertFalse(os.path.exists(os.path.join(self.proje, "b.txt")))

    def test_bayat_kapsam_dosyasi_degisince(self):
        k = self.is_kur(sonuc="\n## Sonuç\n\n- S1, S2 karşılandı.\n")
        MK.kanit_al(k, 1)
        MK.kanit_al(k, 2)
        self.assertEqual(MK.kontrol(k)["kapilar"][2]["sonuc"], "PASS")
        self.yaz(self.proje, os.path.join("src", "a.py"), "A = 2\n")
        r = MK.kontrol(k)
        self.assertEqual(r["kapilar"][2]["sonuc"], "FAIL")
        self.assertTrue(any("bayat" in m for m in self.eksik(r, 3, "kanit_taze")))
        durumlar = {z["t"]: z["e"]["durum"] for z in r["zincir"]}
        self.assertEqual(durumlar[1], "bayat")
        self.assertEqual(durumlar[2], "geçti")

    def test_bayat_plandaki_komut_degisince(self):
        k = self.is_kur()
        MK.kanit_al(k, 1)
        MK.kanit_al(k, 2)
        plan = os.path.join(k, "plan.md")
        with open(plan, encoding="utf-8") as f:
            metin = f.read()
        self.yaz(k, "plan.md", metin.replace('import sys; sys.exit(0)', 'import sys;  sys.exit(0)', 1))
        self.assertTrue(any("farklı komut" in m for m in self.eksik(MK.kontrol(k), 3, "kanit_gecti")))

    def test_bayat_sonradan_dogan_kapsam_dosyasi(self):
        k = self.is_kur(tler=T_IKI.replace("— birinci —", "— birinci — Kapsam: `src/yeni_*.py` —", 1))
        MK.kanit_al(k, 1)
        MK.kanit_al(k, 2)
        self.assertEqual(self.eksik(MK.kontrol(k), 3, "kanit_taze"), [])
        self.yaz(self.proje, os.path.join("src", "yeni_x.py"), "X = 1\n")
        self.assertTrue(self.eksik(MK.kontrol(k), 3, "kanit_taze"))

    def test_eval_ciktidan_okunur(self):
        satir = 'EDEL_EVAL {"model": "m1", "prompt_surum": "p3", "eval_seti": "set-a", "kosu_sayisi": 5}'
        self.yaz(self.proje, "eval_kos.py", f"print({satir!r})\n")
        k = self.is_kur(kademe="kritik", tler=f"- **T1:** S1 — ajan — Eval: — Komut: `{PY} eval_kos.py`\n"
                                               f"- **T2:** S2 — x — Komut: `{PY} -c \"pass\"`")
        e = MK.kanit_al(k, 1)
        self.assertEqual(e["eval"], {"model": "m1", "prompt_surum": "p3", "eval_seti": "set-a", "kosu_sayisi": 5,
                                     "kaynak": "cikti"})
        MK.kanit_al(k, 2)
        self.assertEqual(self.eksik(MK.kontrol(k), 3, "eval_alanlari"), [])

    def test_eval_eksik_alan_reddedilir(self):
        k = self.is_kur(tler=f"- **T1:** S1 — ajan — Eval: — Komut: `{PY} -c \"pass\"`\n- **T2:** S2 — x — Komut: `{PY} -c \"pass\"`")
        e = MK.kanit_al(k, 1, {"model": "m1", "kosu_sayisi": 3})
        self.assertEqual(e["eval"]["kaynak"], "beyan")
        MK.kanit_al(k, 2)
        m = self.eksik(MK.kontrol(k), 3, "eval_alanlari")
        self.assertEqual(len(m), 1)
        self.assertIn("prompt_surum", m[0])
        self.assertIn("eval_seti", m[0])

    def test_eval_esik_alti_kosu_reddedilir(self):
        k = self.is_kur(kademe="kritik", tler=f"- **T1:** S1 — ajan — Eval: — Komut: `{PY} -c \"pass\"`\n"
                                               f"- **T2:** S2 — x — Komut: `{PY} -c \"pass\"`")
        MK.kanit_al(k, 1, {"model": "m", "prompt_surum": "p", "eval_seti": "s", "kosu_sayisi": 3})
        MK.kanit_al(k, 2)
        m = self.eksik(MK.kontrol(k), 3, "eval_alanlari")
        self.assertEqual(m, ["T1: eval koşu sayısı 3 < kritik eşiği 5"])

    def test_eval_hafif_kademede_istenmez(self):
        k = self.is_kur(kademe="hafif", tler=f"- **T1:** S1 — ajan — Eval: — Komut: `{PY} -c \"pass\"`\n"
                                              f"- **T2:** S2 — x — Komut: `{PY} -c \"pass\"`")
        MK.kanit_al(k, 1)
        MK.kanit_al(k, 2)
        self.assertEqual(MK.kontrol(k)["kapilar"][2]["sonuc"], "PASS")


class KapiKarari(Fikstur):
    def tam_is(self, **kw):
        kw.setdefault("sonuc", "\n## Sonuç\n\n- S1 ve S2 karşılandı.\n")
        k = self.is_kur(**kw)
        for t in MK.Baglam(k).kosulacak():
            MK.kanit_al(k, t)
        return k

    def test_kapi_pass(self):
        r = MK.kontrol(self.tam_is())
        self.assertEqual([kp["sonuc"] for kp in r["kapilar"]], ["PASS", "PASS", "PASS"])
        self.assertEqual(r["genel"], "PASS")
        self.assertIsNone(r["asama"])
        self.assertEqual(MK.cikis_kodu(r["genel"]), 0)

    def test_kapi_fail_ilk_kalan_kapi_asama(self):
        k = self.tam_is(todo="- [x] P1 Birinci — 2026-11-12: pytest geçti\n- [ ] P2 İkinci\n")
        r = MK.kontrol(k)
        self.assertEqual(r["genel"], "FAIL")
        self.assertEqual(r["asama"], "2")
        self.assertIn("todo.md'de 1 açık madde", self.eksik(r, 2, "todo_tamam"))
        self.assertEqual(MK.cikis_kodu("FAIL"), 1)

    def test_kapi_kanitsiz_bitti_satiri_fail(self):
        k = self.tam_is(todo="- [x] P1 Birinci\n- [x] P2 İkinci — 2026-11-12: pytest geçti\n")
        self.assertTrue(self.eksik(MK.kontrol(k), 2, "todo_kanit"))

    def test_kapi_engel_blocked(self):
        k = self.tam_is(tler=T_IKI + "\n- **T3:** S2 — canlı servis — Engel: VPN kapalı")
        r = MK.kontrol(k)
        self.assertEqual(r["kapilar"][0]["sonuc"], "PASS")
        self.assertEqual(r["kapilar"][1]["sonuc"], "BLOCKED")
        self.assertEqual(r["genel"], "BLOCKED")
        self.assertIn("T3: VPN kapalı", r["kapilar"][2]["engeller"])
        self.assertEqual(MK.cikis_kodu("BLOCKED"), 2)
        self.assertEqual({z["e"]["durum"] for z in r["zincir"] if z["t"] == 3}, {"engel"})

    def test_kapi_fail_engelden_once_gelir(self):
        k = self.tam_is(tler=T_IKI + "\n- **T3:** S2 — canlı — Engel: VPN kapalı", ozet=False)
        self.assertEqual(MK.kontrol(k)["kapilar"][2]["sonuc"], "FAIL")

    def test_kapi_kritik_yol_karari_denetci_teslim_ister(self):
        k = self.tam_is(kademe="kritik")
        r = MK.kontrol(k)
        self.assertEqual(r["kapilar"][0]["sonuc"], "PASS")  # MD'de Yol kararı var
        self.assertEqual(r["kapilar"][2]["sonuc"], "FAIL")
        self.assertTrue(self.eksik(r, 3, "denetci"))
        self.assertTrue(self.eksik(r, 3, "teslim"))
        r_std = MK.kontrol(self.tam_is(ad="002-std"))
        self.assertEqual(r_std["kapilar"][2]["sonuc"], "PASS")

    def test_kapi_kritik_tam(self):
        k = self.tam_is(kademe="kritik", denetci="**Denetçi:** orkestra:denetci abc123")
        with open(os.path.join(k, "is.json"), encoding="utf-8") as f:
            kayit = json.load(f)
        kayit["teslim"] = {"yerel_birlesme": {"commit": "abc"}}
        self.yaz(k, "is.json", json.dumps(kayit))
        self.assertEqual(MK.kontrol(k)["genel"], "PASS")

    def test_kapi_gap_ve_s_p_bagi(self):
        k = self.tam_is()
        plan = os.path.join(k, "plan.md")
        with open(plan, encoding="utf-8") as f:
            metin = f.read()
        self.yaz(k, "plan.md", metin.replace("**Gap:** G2", "**Gap:** —").replace("**Sözleşme:** S2", "**Sözleşme:** S7"))
        r = MK.kontrol(k)
        self.assertIn("G2: hiçbir P'nin `**Gap:**` alanında yok", self.eksik(r, 2, "gap_kapsama"))
        self.assertIn("P2: S7 sözleşmede yok", self.eksik(r, 2, "s_p_bag"))
        self.assertIn("S2: hiçbir P'nin `**Sözleşme:**` alanında yok", self.eksik(r, 2, "s_p_bag"))

    def test_kapi_sozlesme_sonucu_ozetten_ya_da_sonuc_bolumunden(self):
        k = self.tam_is(sonuc="")
        self.assertEqual(self.eksik(MK.kontrol(k), 3, "sozlesme_sonuc"),
                         [f"S{s}: sonucu ne sözleşme `## Sonuç` bölümünde ne çalışma özetinde anılıyor" for s in (1, 2)])
        self.yaz(k, "calisma_ozeti_20261112.md", OZET + "\n## Plana göre gerçekleşen\n\n- S1 karşılandı (E1)\n")
        self.assertEqual(self.eksik(MK.kontrol(k), 3, "sozlesme_sonuc"),
                         ["S2: sonucu ne sözleşme `## Sonuç` bölümünde ne çalışma özetinde anılıyor"])
        self.yaz(k, "sozlesme_20261112.md", SOZ.format(sonuc="\n## Sonuç\n\n- **S2:** karşılandı — E2\n"))
        self.assertEqual(self.eksik(MK.kontrol(k), 3, "sozlesme_sonuc"), [])

    def test_kapi_sozlesmesiz_iste_sonuc_yinelenmez(self):
        k = self.tam_is()
        os.remove(os.path.join(k, "sozlesme_20261112.md"))
        r = MK.kontrol(k)
        self.assertTrue(self.eksik(r, 1, "sozlesme_kriter"))
        self.assertEqual(self.eksik(r, 3, "sozlesme_sonuc"), [])

    def test_kapi_kontrol_yan_etkisiz(self):
        k = self.tam_is()
        once = sorted(os.listdir(k))
        MK.kontrol(k)
        self.assertEqual(sorted(os.listdir(k)), once)

    def test_kapi_zincir_tam(self):
        r = MK.kontrol(self.tam_is())
        self.assertEqual([(z["g"], z["p"], z["s"], z["t"], z["e"]["e"]) for z in r["zincir"]],
                         [(1, 1, 1, 1, "E1"), (2, 2, 2, 2, "E2")])

    def test_kapi_proje_ezmesi(self):
        k = self.tam_is()
        self.yaz(self.sd, "edel.json", json.dumps({"kapilar": {"1": {"ad": "B", "standart": ["md_var"]},
                                                              "2": {"ad": "G", "standart": ["plan_p"]},
                                                              "3": {"ad": "D", "standart": ["teslim"]}}}))
        r = MK.kontrol(k)
        self.assertEqual(r["kapilar"][2]["kontroller"], ["teslim"])
        self.assertEqual(r["kapilar"][2]["sonuc"], "FAIL")

    def test_kapi_cli_cikis_kodu(self):
        k = self.tam_is()
        self.assertEqual(MK.main(["kontrol", k]), 0)
        self.assertEqual(MK.main(["kontrol", k, "--json"]), 0)


class Olcum(Fikstur):
    def test_olc_kayittaki_sirali_isleri_sayar(self):
        k = self.is_kur(sonuc="\n## Sonuç\n\n- tamam S1 S2\n")
        MK.kanit_al(k, 1)
        MK.kanit_al(k, 2)
        sirasiz = os.path.join(self.proje, "Claude_Orkestrasyon", "002-sirasiz")
        os.makedirs(sirasiz)
        self.yaz(sirasiz, "is.json", json.dumps({"id": "I-002"}))
        self.yaz(self.sd, "isler.json", json.dumps({"sayac": 3, "isler": {
            "I-001": {"klasor": k, "durum": "kapandi"},
            "I-002": {"klasor": sirasiz, "durum": "kapandi"},
            "I-003": {"klasor": os.path.join(self.proje, "silinmis"), "durum": "kapandi"}}}))
        o = MK.olc(self.sd)
        self.assertEqual(o["is_sayisi"], 1)
        self.assertEqual(o["dagilim"]["genel"], {"PASS": 1})
        self.assertEqual(o["dagilim"]["kapali_3"], {"PASS": 1})
        self.assertEqual(o["hatalar"], [])
        self.assertIn("sıralı iş: 1", MK.olcum_metni(o))


class Kapanis(Fikstur):
    def golgeler(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            olaylar = [json.loads(s) for s in f if s.strip()]
        return [o for o in olaylar if o.get("tur") == "kapi_golge" and o.get("kapi") == "edel"]

    def test_kapat_kapi3_fail_golge_yazar(self):
        k = self.is_kur(ozet=False)
        r = MK.kapanis_golge(k)
        self.assertEqual(r["kapilar"][2]["sonuc"], "FAIL")
        g = self.golgeler()
        self.assertEqual(len(g), 1)
        self.assertIn("kapı 3 FAIL", g[0]["neden"])

    def test_kapat_pass_golge_yazmaz(self):
        k = self.is_kur(sonuc="\n## Sonuç\n\n- S1, S2 karşılandı.\n")
        MK.kanit_al(k, 1)
        MK.kanit_al(k, 2)
        MK.kapanis_golge(k)
        self.assertEqual(self.golgeler(), [])

    def test_kapat_bozuk_klasorde_engellemez(self):
        self.assertIsNone(MK.kapanis_golge(os.path.join(self.proje, "yok", "\0")))

    def test_kapat_cli_kapanisi_engellemez(self):
        klasor = os.path.join(self.proje, "Claude_Orkestrasyon", "020-kapat")
        sira = {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_ONAY_KAPISI": "0"}
        r = TC.kos([TC.CLI, "is", "ac", "kapanış", "--klasor", klasor], self.proje, ortam=sira)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            is_id = json.load(f)["id"]
        r = TC.kos([TC.CLI, "is", "kapat", is_id, "--ozetsiz", "edel kapanış testi"], self.proje, ortam=sira)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(len(self.golgeler()), 1)
        self.assertIn("edel", r.stderr)


if __name__ == "__main__":
    unittest.main()
