"""ADR-0068: best in class yöntemi üretim anında bağlama eklenir (scripts/yontem_enjeksiyonu.py) ve hook bağlantıları.
`python -m pytest -q plugins/orkestra/tests/test_yontem_enjeksiyonu.py`
Metin standarttan okunur; testte sabitlenmez. Hepsi geçici projede koşar.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import test_cekirdek as TC

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import soru_sinif  # noqa: E402
import yontem_enjeksiyonu as Y  # noqa: E402

IS_MESAJI = "scripts/hook.py dosyasına yeni bir modül ekle ve testlerini yaz"
SORU_MESAJI = "Bu hook ne demek?"
DEVAM_MESAJI = "tamam"
ISARET = "ORKESTRA YÖNTEM"


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_yontem_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(self.sd)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_YONTEM_ENJEKSIYONU", None)
        self.ayar_yaz({"kontrol_payi": 0})  # aksi söylenmedikçe her oturum yöntem kolunda

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ayar_yaz(self, d):
        with open(os.path.join(self.sd, Y.PROJE_DOSYA), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]


class Siniflar(_Proje):
    def test_mesaj_siniflari_varsayimi(self):
        self.assertEqual(soru_sinif.tur(IS_MESAJI, self.sd), "is")
        self.assertEqual(soru_sinif.tur(SORU_MESAJI, self.sd), "soru")
        self.assertEqual(soru_sinif.tur(DEVAM_MESAJI, self.sd), "devam")


class AnaAjan(_Proje):
    def test_is_mesaji_metin_alir_soru_ve_devam_bos(self):
        self.assertIn(ISARET, Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1"))
        self.assertEqual(Y.ana_ajan_metni(SORU_MESAJI, self.sd, "o1"), "")
        self.assertEqual(Y.ana_ajan_metni(DEVAM_MESAJI, self.sd, "o1"), "")

    def test_kapali_mod_ve_ortam_degiskeni_bos(self):
        self.ayar_yaz({"kontrol_payi": 0, "mod": "kapali"})
        self.assertEqual(Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1"), "")
        self.ayar_yaz({"kontrol_payi": 0})
        os.environ["ORKESTRA_YONTEM_ENJEKSIYONU"] = "0"
        self.assertEqual(Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1"), "")

    def test_standart_degisince_cikti_degisir(self):
        d = os.path.join(self.sd, "standartlar")
        os.makedirs(d)
        with open(os.path.join(d, "best_in_class.md"), "w", encoding="utf-8") as f:
            f.write("# X\n\n## Üretim anı\n\nÖZEL_YONTEM_METNI.\n\n## Başka\n\nbu gelmez\n")
        m = Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1")
        self.assertIn("ÖZEL_YONTEM_METNI.", m)
        self.assertNotIn("bu gelmez", m)

    def test_bolum_yoksa_bos(self):
        d = os.path.join(self.sd, "standartlar")
        os.makedirs(d)
        with open(os.path.join(d, "best_in_class.md"), "w", encoding="utf-8") as f:
            f.write("# X\n\n## Başka\n\nmetin\n")
        self.assertEqual(Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1"), "")

    def test_uzunluk_sinirlari(self):
        d = os.path.join(self.sd, "standartlar")
        os.makedirs(d)
        with open(os.path.join(d, "best_in_class.md"), "w", encoding="utf-8") as f:
            f.write("## Üretim anı\n\n" + "kelime " * 400 + "\n")
        self.assertLessEqual(len(Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1")), 700)
        self.assertLessEqual(len(Y.isci_metni("orkestra:isci-t2", self.sd, "o1")), 600)

    def test_gercek_standart_sinirlar_icinde(self):
        m = Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1")
        self.assertGreater(len(m), 100)
        self.assertLessEqual(len(m), 700)
        self.assertLessEqual(len(Y.isci_metni("orkestra:isci-t1", self.sd, "o1")), 600)

    def test_gunluk_satiri_yazilir(self):
        Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1")
        Y.isci_metni("orkestra:isci-t1", self.sd, "o1")
        k = [x for x in self.gunluk() if x.get("tur") == "yontem_enjekte"]
        self.assertEqual([(x["nokta"], x["kol"]) for x in k], [("ana", "yontem"), ("isci", "yontem")])
        self.assertEqual(k[0]["oturum"], "o1")

    def test_hata_bos_metin_doner(self):
        with mock.patch.object(Y, "_bolum", side_effect=RuntimeError("x")):
            self.assertEqual(Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1"), "")


class Isci(_Proje):
    def test_denetci_bos_isci_dolu(self):
        self.assertEqual(Y.isci_metni("orkestra:denetci", self.sd, "o1"), "")
        for t in ("orkestra:isci-t1", "orkestra:isci-t2", "orkestra:isci-t3", "orkestra:isci-t4", "orkestra:test-yazari"):
            self.assertIn(ISARET, Y.isci_metni(t, self.sd, "o1"), t)


class Kol(_Proje):
    def test_ayni_oturum_ayni_kol(self):
        self.ayar_yaz({"kontrol_payi": 0.5})
        for i in range(50):
            oid = f"oturum-{i}"
            self.assertEqual(Y.kol(oid, self.sd), Y.kol(oid, self.sd))

    def test_kontrol_payi_yuzde_elli(self):
        self.ayar_yaz({"kontrol_payi": 0.5})
        kontrol = sum(Y.kol(f"{i:08x}-0000-4000-8000-{i:012x}", self.sd) == "kontrol" for i in range(1000))
        self.assertTrue(450 <= kontrol <= 550, kontrol)

    def test_kontrol_kolu_bos_doner_ve_gunluge_yazar(self):
        self.ayar_yaz({"kontrol_payi": 1})
        self.assertEqual(Y.ana_ajan_metni(IS_MESAJI, self.sd, "o1"), "")
        self.assertEqual(Y.isci_metni("orkestra:isci-t1", self.sd, "o1"), "")
        k = [x for x in self.gunluk() if x.get("tur") == "yontem_enjekte"]
        self.assertEqual([x["kol"] for x in k], ["kontrol", "kontrol"])

    def test_pay_sifir_kolu_kapatir(self):
        self.ayar_yaz({"kontrol_payi": 0})
        self.assertTrue(all(Y.kol(f"o{i}", self.sd) == "yontem" for i in range(200)))

    def test_oturum_kimligi_yoksa_yontem(self):
        self.ayar_yaz({"kontrol_payi": 1})
        self.assertEqual(Y.kol(None, self.sd), "yontem")


class HookBaglantisi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    hook = TC.Cekirdek.hook
    kart = TC.Cekirdek.kart
    alt_ajan_transkripti = TC.Cekirdek.alt_ajan_transkripti

    def ayar(self, d):
        with open(os.path.join(self.sd, Y.PROJE_DOSYA), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def ups(self, prompt):
        c = self.hook("UserPromptSubmit", {"prompt": prompt})
        return (c.get("hookSpecificOutput") or {}).get("additionalContext", "")

    def test_is_mesajinda_baglamda_soru_mesajinda_yok(self):
        self.ayar({"kontrol_payi": 0})
        self.assertIn(ISARET, self.ups(IS_MESAJI))
        self.assertNotIn(ISARET, self.ups(SORU_MESAJI))

    def test_kontrol_kolunda_baglamda_yok(self):
        self.ayar({"kontrol_payi": 1})
        self.assertNotIn(ISARET, self.ups(IS_MESAJI))

    def _subagent(self, agent_type):
        gorev = self.kart()
        aid = "agent-yontem-1"
        self.alt_ajan_transkripti(aid, gorev, "is")
        c = self.hook("SubagentStart", {"agent_id": aid, "agent_type": agent_type})
        return (c.get("hookSpecificOutput") or {}).get("additionalContext", "")

    def test_isci_subagent_start_yontem_denetci_yok(self):
        self.ayar({"kontrol_payi": 0})
        self.assertIn(ISARET, self._subagent("orkestra:isci-t1"))

    def test_denetci_subagent_start_yontem_yok(self):
        self.ayar({"kontrol_payi": 0})
        self.assertNotIn(ISARET, self._subagent("orkestra:denetci"))


# ---------------------------------------------------------------- P4: ölçüm olayları ve rapor
import is_rapor as R  # noqa: E402
import is_sirasi as S  # noqa: E402

SORULAR = ("Kök neden", "Alternatifler", "Kapsam özü", "Ölçüm")
ALT_TAM = "**Alternatifler:**\n\n- Seçilen: x. Neden: y.\n- Elenen: z. Neden elendi: w.\n"
DENETCI = "a8159550dfebaedf5"


def plan_metni(isaretler=("✔", "✔", "✔", "✔"), denetci=DENETCI):
    satirlar = "\n".join(f"- **{q}:** {i} — gerekçe." for q, i in zip(SORULAR, isaretler))
    return (f"# Plan\n\n## 4. Plan maddeleri\n\n### P1 Madde\n\n**Dayanak:** MD §1\n\n{ALT_TAM}\n**Kabul:** x\n\n"
            f"## Best in class denetimi\n\n{satirlar}\n\n**Denetçi:** orkestra:denetci {denetci}\n")


class OlcumOlaylari(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def is_klasoru(self, plan, oturum="o-yazar"):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", "001-deneme")
        os.makedirs(k)
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-001", "sira": S.SIRA_ADI, "kalite": True, "oturumlar": [{"oturum": oturum}]}, f)
        with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
            f.write(plan)
        return k

    def denetci_kaydi(self):
        with open(os.path.join(self.sd, "zaman.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"tur": "alt", "agent_id": DENETCI, "ajan": "orkestra:denetci"}) + "\n")

    def olaylar(self, tur):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        with open(yol, encoding="utf-8") as f:
            return [o for o in map(json.loads, f) if o.get("tur") == tur]

    def uyar(self, k):
        with mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", "ORKESTRA_BIC_KAPISI": "1"}):
            S.bic_uyari(k)

    def test_bic_ilk_bir_kez_ve_kol_oturumdan(self):
        k = self.is_klasoru(plan_metni(denetci="bekliyor"))
        self.uyar(k)
        self.uyar(k)
        ilk = self.olaylar("bic_ilk")
        self.assertEqual(len(ilk), 1)
        self.assertEqual(ilk[0]["oturum"], "o-yazar")
        self.assertEqual(ilk[0]["kol"], Y.kol("o-yazar", self.sd))
        self.assertEqual(self.olaylar("bic_denetim_ilk"), [])

    def test_bic_denetim_ilk_dolu_blokta_bir_kez(self):
        self.denetci_kaydi()
        k = self.is_klasoru(plan_metni())
        self.uyar(k)
        self.uyar(k)
        d = self.olaylar("bic_denetim_ilk")
        self.assertEqual(len(d), 1)
        self.assertTrue(d[0]["hepsi_ok"])
        self.assertEqual(set(d[0]["kararlar"]), set(SORULAR))

    def test_bic_denetim_ilk_ilk_karar_ret_ise_hepsi_ok_degil(self):
        self.denetci_kaydi()
        k = self.is_klasoru(plan_metni(("✔", "✘", "✔", "✔")))
        self.uyar(k)
        d = self.olaylar("bic_denetim_ilk")
        self.assertFalse(d[0]["hepsi_ok"])
        self.assertEqual(d[0]["kararlar"]["Alternatifler"], "✘")

    def test_kayitsiz_denetci_olay_yazmaz(self):
        k = self.is_klasoru(plan_metni())  # zaman.jsonl'da denetçi kaydı yok
        self.uyar(k)
        self.assertEqual(self.olaylar("bic_denetim_ilk"), [])


class Rapor(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def yaz(self, satirlar):
        with open(os.path.join(self.sd, "gunluk.jsonl"), "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")

    def kol_olaylari(self, kol, n, ok, onek):
        s = []
        for i in range(n):
            o, is_ad = f"{onek}-{i}", f"{onek}-is-{i}"
            s.append({"tur": "bic_ilk", "oturum": o, "is": is_ad, "kol": kol})
            s.append({"tur": "bic_denetim_ilk", "oturum": o, "is": is_ad, "kol": kol, "hepsi_ok": i < ok})
        return s

    def test_fisher_bilinen_tablo(self):
        self.assertAlmostEqual(R.fisher_tek_yonlu(24, 1, 15, 10), 0.0023, delta=0.001)
        self.assertAlmostEqual(R.fisher_tek_yonlu(5, 5, 5, 5), 0.5 + 0.5 * 0.0, delta=0.5)  # simetrik tabloda p > 0,3
        self.assertGreater(R.fisher_tek_yonlu(5, 5, 5, 5), 0.3)

    def test_kol_sayilari_orani_ve_p(self):
        self.yaz(self.kol_olaylari("yontem", 25, 24, "y") + self.kol_olaylari("kontrol", 25, 15, "k"))
        y = R.rapor(self.sd)["yontem"]
        self.assertEqual(y["kol"]["yontem"], {"plan": 25, "denetimli": 25, "ok": 24})
        self.assertEqual(y["kol"]["kontrol"], {"plan": 25, "denetimli": 25, "ok": 15})
        self.assertAlmostEqual(y["p"], 0.0023, delta=0.001)
        self.assertFalse(y["karar_zamani"])
        m = R.metin(R.rapor(self.sd))
        self.assertIn("24/25 (%96)", m)
        self.assertIn("15/25 (%60)", m)
        self.assertIn("karar için her kolda 30", m)

    def test_oturum_basina_yalniz_ilk_plan_sayilir(self):
        s = self.kol_olaylari("yontem", 3, 3, "y")
        s.append({"tur": "bic_ilk", "oturum": "y-0", "is": "y-ikinci", "kol": "yontem"})
        s.append({"tur": "bic_denetim_ilk", "oturum": "y-0", "is": "y-ikinci", "kol": "yontem", "hepsi_ok": False})
        self.yaz(s)
        self.assertEqual(R.rapor(self.sd)["yontem"]["kol"]["yontem"]["plan"], 3)

    def test_her_kol_otuza_ulasinca_karar_zamani(self):
        self.yaz(self.kol_olaylari("yontem", 30, 27, "y") + self.kol_olaylari("kontrol", 30, 18, "k"))
        self.assertTrue(R.rapor(self.sd)["yontem"]["karar_zamani"])
        self.assertIn("karar zamanı", R.metin(R.rapor(self.sd)))

    def test_olay_yoksa_bolum_yok(self):
        self.assertNotIn("yöntem enjeksiyonu", R.metin(R.rapor(self.sd)))
