"""Jira görev bağımlılığı girdi kapısı (ADR-0086, I-231 P3): gölge/ihlal modu, K4 durumları, kapatma; gerçek PE yanıtı fixture'ıyla.

Kapı gölgede açılır (P-028): eksik uyarılır ve `kapi_golge` yazılır, iş engellenmez. `ihlal` modunda eksik plan eksiği sayılır.
Okuma saatinin eskiliği (K4c) iki modda da yalnız uyarıdır. `**Jira:**` alanı olmayan plan kapsam dışıdır.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_sirasi as S  # noqa: E402
import jira_bagimlilik as JB  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "jira_ornek_PE.json")


def madde(n, jira=None, once="yok", yazma=None):
    s = f"### P{n} Madde {n}\n\n**Ne:** iş\n\n**Dayanak:** MD §1\n\n"
    if jira:
        s += f"**Jira:** {jira}\n\n"
    return s + f"**Önce:** {once}\n\n**Yazma alanı:** {yazma or f'scripts/m{n}.py'}\n\n**Kabul:** x\n\n"


def plan(*maddeler, hazirlanma="27.10.2026 10:20"):
    return ("# Plan\n\n**Hazırlanma saati:**\n\n" + hazirlanma + "\n\n## 4. Plan maddeleri\n\n" + "".join(maddeler))


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


class JiraBagimlilikKapisi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def klasor(self, metin, jira_dosyasi=True, ad="001-deneme", okuma=None):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", ad)
        os.makedirs(k)
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-" + ad[:3], "sira": S.SIRA_ADI}, f)
        with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
            f.write(metin)
        if jira_dosyasi:
            with open(FIXTURE, encoding="utf-8") as f:
                veri = json.load(f)
            if okuma is not None:
                veri["okuma_saati"] = okuma
            with open(os.path.join(k, JB.DOSYA), "w", encoding="utf-8") as f:
                json.dump(veri, f)
        return k

    def golge_modu(self):
        with open(os.path.join(self.sd, "jira_bagimlilik.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "golge"}, f)  # ayar dosyası ihlal (ADR-0096); gölge davranışı ezmeyle sınanır

    def ihlal_modu(self):
        with open(os.path.join(self.sd, "jira_bagimlilik.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "ihlal"}, f)

    def ortam(self, **ek):
        return mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1", **ek})

    def olaylar(self, tur):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [o for o in (json.loads(s) for s in f if s.strip()) if o.get("tur") == tur and o.get("kapi") == "jira_bagimlilik"]

    def engel(self, k):
        with self.ortam(), contextlib.redirect_stderr(io.StringIO()) as hata:
            return S.jira_bagimlilik_engeli(k), hata.getvalue()

    # ---- kapsam
    def test_jira_alani_olmayan_plan_kapsam_disi(self):
        k = self.klasor(plan(madde(1), madde(2)), jira_dosyasi=False)
        self.ihlal_modu()
        with self.ortam():
            self.assertFalse(S.jira_bagimlilik_kapsaminda_mi(k))
        self.assertEqual(self.engel(k), ([], ""))

    def test_ayar_dosyasi_ihlalde(self):
        kok = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ayarlar", "jira_bagimlilik.json")
        with open(kok, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["mod"], "ihlal")  # ADR-0096

    # ---- PE-770 öncülü PE-783 olmadan tek başına
    def test_oncul_olmadan_tek_basina_gerceksiz_eksik(self):
        k = self.klasor(plan(madde(1, "PE-770")))
        with self.ortam():
            e = S.jira_bagimlilik_eksikleri(k)
        self.assertEqual(len(e), 1)
        self.assertIn("PE-783", e[0])
        self.assertIn("PE-770", e[0])

    @_golge_sabit

    def test_golge_uyarir_kaydeder_engellemez(self):
        k = self.klasor(plan(madde(1, "PE-770")))
        e, hata = self.engel(k)
        self.assertEqual(e, [])
        self.assertIn("PE-783", hata)
        golge = self.olaylar("kapi_golge")
        self.assertEqual(len(golge), 1)
        self.assertIn("PE-783", golge[0]["neden"])
        self.assertEqual(self.olaylar("kapi_ret"), [])

    def test_ihlal_modu_ret_ve_kapi_ret_kaydi(self):
        k = self.klasor(plan(madde(1, "PE-770")))
        self.ihlal_modu()
        e, _ = self.engel(k)
        self.assertEqual(len(e), 1)
        self.assertIn("PE-783", e[0])
        self.assertEqual(len(self.olaylar("kapi_ret")), 1)

    def test_plan_eksikleri_ihlalde_icerir_golgede_icermez(self):
        self.golge_modu()
        k = self.klasor(plan(madde(1, "PE-770")))
        with self.ortam(), contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(any("PE-783" in x for x in S.plan_eksikleri(k)))
        self.ihlal_modu()
        with self.ortam(), contextlib.redirect_stderr(io.StringIO()):
            self.assertTrue(any("PE-783" in x and "ADR-0086" in x for x in S.plan_eksikleri(k)))

    def test_oncul_kumede_ve_once_icinde_gecer(self):
        k = self.klasor(plan(madde(1, "PE-783"), madde(2, "PE-770", once="P1 — Çıktı: PE-783 bloklar")))
        self.ihlal_modu()
        self.assertEqual(self.engel(k)[0], [])

    # ---- K4a / K4b / K4c
    def test_k4a_dosya_yok(self):
        k = self.klasor(plan(madde(1, "PE-770")), jira_dosyasi=False)
        self.ihlal_modu()
        e, _ = self.engel(k)
        self.assertEqual(len(e), 1)
        self.assertIn(JB.DOSYA + " yok", e[0])

    def test_k4a_bozuk_dosya(self):
        k = self.klasor(plan(madde(1, "PE-770")), jira_dosyasi=False)
        with open(os.path.join(k, JB.DOSYA), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.ihlal_modu()
        e, _ = self.engel(k)
        self.assertEqual(len(e), 1)
        self.assertIn("okunamadı", e[0])

    def test_k4b_anahtar_dosyada_yok(self):
        k = self.klasor(plan(madde(1, "PE-999")))
        self.ihlal_modu()
        e, _ = self.engel(k)
        self.assertEqual(len(e), 1)
        self.assertIn("PE-999", e[0])
        self.assertIn("bağımsız sayılamaz", e[0])

    def test_k4b_baglantisiz_ama_okunmus_gorev_gecer(self):
        k = self.klasor(plan(madde(1, "PE-720")))  # fixture'da issuelinks: []
        self.ihlal_modu()
        self.assertEqual(self.engel(k)[0], [])

    def test_k4c_eski_okuma_iki_modda_da_yalniz_uyari(self):
        k = self.klasor(plan(madde(1, "PE-720")), okuma="2026-10-20T09:00:00")
        for ihlal in (False, True):
            if ihlal:
                self.ihlal_modu()
            e, hata = self.engel(k)
            self.assertEqual(e, [], f"ihlal={ihlal}")
        self.assertIn("eski", hata + json.dumps(self.olaylar("kapi_golge")))
        self.assertEqual(len(self.olaylar("kapi_golge")), 1)  # aynı neden bir kez
        self.assertEqual(self.olaylar("kapi_ret"), [])

    def test_k4c_taze_okuma_uyari_vermez(self):
        k = self.klasor(plan(madde(1, "PE-720")))  # fixture 27.10.2026 10:30, plan 27.10.2026 10:20
        self.assertEqual(self.engel(k), ([], ""))

    # ---- kapatma
    def test_kapatma_env(self):
        k = self.klasor(plan(madde(1, "PE-770")))
        self.ihlal_modu()
        with self.ortam(ORKESTRA_JIRA_BAGIMLILIK_KAPISI="0"):
            self.assertFalse(S.jira_bagimlilik_kapsaminda_mi(k))
            self.assertEqual(S.jira_bagimlilik_engeli(k), [])

    # ---- yazım anı raporu (plan_yazim_eksikleri): gölge gölgede, ihlal sertte
    def test_plan_yazim_raporu_modu_izler(self):
        self.golge_modu()
        metin = plan(madde(1, "PE-770"))
        k = self.klasor(metin)
        with self.ortam():
            sert, golge = S.plan_yazim_eksikleri(k, metin)
        self.assertTrue(any("PE-783" in x for x in golge), golge)
        self.assertFalse(any("PE-783" in x for x in sert), sert)
        self.ihlal_modu()
        with self.ortam():
            sert, golge = S.plan_yazim_eksikleri(k, metin)
        self.assertTrue(any("PE-783" in x for x in sert), sert)


if __name__ == "__main__":
    unittest.main()
