"""ADR-0029: perspektif girdisi (satır sayısı, düzeltme tekrarı) ve rapor kanıt doğrulaması (dogrula, kaydet, duzeltme-tara)."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perspektif as P  # noqa: E402
import ic_kos  # noqa: E402

NOT = "(teyidi 13.10'da kapsam daralması olarak düzeltildi)"


class PerspektifDogrulama(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_pd_")
        self.ev = tempfile.mkdtemp(prefix="ork_pd_ev_")
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(self.proje))
        self.hafiza = os.path.join(self.ev, ".claude", "projects", slug, "memory")
        os.makedirs(self.hafiza)
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        self.assertEqual(self.kos(["baslat"]).returncode, 0)
        self.yaz_hafiza("MEMORY.md", "# Dizin\n- bir\n- iki\n")  # 3 satır, sonda satır sonu
        self.rapor = os.path.join(self.sd, "perspektif", "perspektif_test.md")
        os.makedirs(os.path.dirname(self.rapor), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.ev, ignore_errors=True)

    def kos(self, args):
        env = dict(os.environ, PYTHONUTF8="1", HOME=self.ev, USERPROFILE=self.ev, CLAUDE_CODE_SESSION_ID="pd-oturum")
        env.pop("CLAUDE_PROJECT_DIR", None)
        return ic_kos.kos([CLI] + args, cwd=self.proje, env=env)

    def yaz_hafiza(self, ad, metin):
        with open(os.path.join(self.hafiza, ad), "w", encoding="utf-8") as f:
            f.write(metin)

    def yaz_rapor(self, metin):
        with open(self.rapor, "w", encoding="utf-8") as f:
            f.write(metin)

    def oku_rapor(self):
        with open(self.rapor, encoding="utf-8") as f:
            return f.read()

    # ---- girdi
    def test_satir_sayisi_sondaki_satir_sonunu_saymaz(self):
        g = P.girdi(self.sd, self.proje, self.hafiza)
        self.assertEqual(g["hafiza"]["memory_md"]["satir"], 3)

    def test_satir_sayisi_satir_sonsuz_dosya(self):
        self.yaz_hafiza("MEMORY.md", "a\nb\nc")
        self.assertEqual(P.girdi(self.sd, self.proje, self.hafiza)["hafiza"]["memory_md"]["satir"], 3)

    def test_girdi_duzeltme_tekrari_alani(self):
        for ad in ("a.md", "b.md", "c.md"):
            self.yaz_hafiza(ad, "- ML çöküşü " + NOT + "\n")
        d = P.girdi(self.sd, self.proje, self.hafiza)["duzeltme_tekrari"]
        self.assertEqual((d["sayi"], d["bulgular"][0]["adet"]), (1, 3))
        self.assertEqual(len(d["bulgular"][0]["yerler"]), 3)

    def test_girdi_imzasi_tekrarla_degisir(self):
        once = P.girdi(self.sd, self.proje, self.hafiza)["imza"]
        for ad in ("a.md", "b.md"):
            self.yaz_hafiza(ad, "- ML çöküşü " + NOT + "\n")
        self.assertNotEqual(once, P.girdi(self.sd, self.proje, self.hafiza)["imza"])

    # ---- rapor_dogrula
    def test_tutan_kanit(self):
        self.yaz_rapor('1. öneri\n   Kanıt: ara "iki" MEMORY.md => 1\n')
        o = P.rapor_dogrula(self.rapor, self.hafiza, self.proje)
        self.assertEqual((o["toplam"], o["tutan"], o["tutmayan"]), (1, 1, []))

    def test_tutmayan_kanit(self):
        self.yaz_rapor('1. öneri\n   Kanıt: ara "iki" MEMORY.md => 5\n')
        o = P.rapor_dogrula(self.rapor, self.hafiza, self.proje)
        self.assertEqual((len(o["tutmayan"]), o["tutmayan"][0]["satir"]), (1, 2))

    def test_dosya_kaniti_alinti_tutmazsa(self):
        self.yaz_rapor('   Kanıt: dosya MEMORY.md:2 "olmayan alıntı metni burada"\n')
        self.assertEqual(len(P.rapor_dogrula(self.rapor, self.hafiza, self.proje)["tutmayan"]), 1)

    def test_komut_kaniti_kosulmaz_dogrulanmadi_sayilir(self):
        self.yaz_rapor("   Kanıt: komut `echo merhaba` => merhaba\n")
        o = P.rapor_dogrula(self.rapor, self.hafiza, self.proje)
        self.assertEqual((o["dogrulanmadi"], o["tutmayan"]), (1, []))

    def test_bilinmeyen_kanit_turu_tutmadi(self):
        self.yaz_rapor("   Kanıt: uydurma xyz\n")
        self.assertEqual(len(P.rapor_dogrula(self.rapor, self.hafiza, self.proje)["tutmayan"]), 1)

    # ---- girdi Kanıt türü (ADR-0094)
    def _girdi(self):
        with open(os.path.join(os.path.dirname(self.rapor), "girdi.json"), "w", encoding="utf-8") as f:
            json.dump({"gunluk": {"kapi_ret": {"uretim_noktasi": 44}, "denetim_payi": 0.0284},
                       "anomali": {"ilk": [{"pay": 0.8723}]}, "trend": {"kpi": {"a": 1, "b": 2}},
                       "kpi": {"ret_orani": 0.13731}}, f)

    def _girdi_sonuc(self, satirlar):
        self._girdi()
        self.yaz_rapor("".join(f"   Kanıt: {s}\n" for s in satirlar))
        return P.rapor_dogrula(self.rapor, self.hafiza, self.proje)

    def test_girdi_kaniti_tam_sayi_ve_ondalik_tutar(self):
        o = self._girdi_sonuc(["girdi gunluk.kapi_ret.uretim_noktasi => 44", "girdi kpi.ret_orani => 0,1373",
                               "girdi anomali.ilk[0].pay => 0.87", "girdi gunluk.denetim_payi => %2,84",
                               "girdi trend.kpi => 2", "girdi gunluk.kapi_ret.uretim_noktasi => >=40"])
        self.assertEqual((o["toplam"], o["tutan"], o["tutmayan"]), (6, 6, []))

    def test_girdi_kaniti_yanlis_deger_tutmaz(self):
        o = self._girdi_sonuc(["girdi gunluk.kapi_ret.uretim_noktasi => 41", "girdi kpi.ret_orani => 0,1517"])
        self.assertEqual(len(o["tutmayan"]), 2)
        self.assertIn("beklenen 41", o["tutmayan"][0]["mesaj"])

    def test_girdi_kaniti_olmayan_alan_ve_bozuk_bicim(self):
        o = self._girdi_sonuc(["girdi gunluk.yok => 1", "girdi gunluk.kapi_ret.uretim_noktasi => 44 (n=28); 52",
                               "girdi anomali.ilk[5].pay => 1"])
        self.assertEqual(len(o["tutmayan"]), 3)
        self.assertIn("alan yok", o["tutmayan"][0]["mesaj"])

    def test_girdi_json_yoksa_tutmaz(self):
        self.yaz_rapor("   Kanıt: girdi gunluk.kapi_ret.uretim_noktasi => 44\n")
        o = P.rapor_dogrula(self.rapor, self.hafiza, self.proje)
        self.assertIn("okunamadı", o["tutmayan"][0]["mesaj"])

    def test_talimat_girdi_bicimini_ve_tek_ifade_kuralini_tasir(self):
        md = open(os.path.join(KOK, "agents", "perspektif-ajani.md"), encoding="utf-8").read()
        self.assertIn("Kanıt: girdi alan.yolu => değer", md)
        self.assertIn("tek ifade", md)

    def test_kanitsiz_rapor_sifir(self):
        self.yaz_rapor("# Rapor\n1. öneri\n")
        self.assertEqual(P.rapor_dogrula(self.rapor, self.hafiza, self.proje)["toplam"], 0)

    def test_rapor_okunamazsa_valueerror(self):
        with self.assertRaises(ValueError):
            P.rapor_dogrula(os.path.join(self.sd, "yok.md"), self.hafiza, self.proje)

    # ---- işaretleme
    def test_isaret_yazilir_ve_idempotent(self):
        self.yaz_rapor('1. öneri\n   Kanıt: ara "iki" MEMORY.md => 5\n2. başka\n')
        P.rapor_isaretle(self.rapor, self.hafiza, self.proje)
        ilk = self.oku_rapor()
        self.assertEqual(ilk.count(P.ISARET), 1)
        self.assertTrue(ilk.splitlines()[2].lstrip().startswith(P.ISARET))
        P.rapor_isaretle(self.rapor, self.hafiza, self.proje)
        self.assertEqual(self.oku_rapor(), ilk)

    def test_duzeltilen_kanit_isareti_kalkar(self):
        self.yaz_rapor('   Kanıt: ara "iki" MEMORY.md => 5\n')
        P.rapor_isaretle(self.rapor, self.hafiza, self.proje)
        self.yaz_rapor(self.oku_rapor().replace("=> 5", "=> 1"))
        P.rapor_isaretle(self.rapor, self.hafiza, self.proje)
        self.assertNotIn(P.ISARET, self.oku_rapor())

    def test_isaret_numarali_madde_baslatmaz(self):
        self.yaz_rapor('1. öneri\n   Kanıt: ara "iki" MEMORY.md => 5\n')
        P.rapor_isaretle(self.rapor, self.hafiza, self.proje)
        self.assertEqual(len([s for s in self.oku_rapor().splitlines() if re.match(r"^\d+\.", s)]), 1)

    # ---- kaydet
    def test_kaydet_isaretler_ve_kaydi_yapar(self):
        self.yaz_rapor('1. öneri\n   Kanıt: ara "iki" MEMORY.md => 5\n')
        os.makedirs(os.path.join(self.sd, "perspektif"), exist_ok=True)
        with open(os.path.join(self.sd, "perspektif", "girdi.json"), "w", encoding="utf-8") as f:
            json.dump({"imza": "x", "hafiza": {"klasor": self.hafiza}}, f)
        o = P.kaydet(self.sd, self.rapor, self.proje)
        self.assertEqual(len(o["tutmayan"]), 1)
        self.assertIn(P.ISARET, self.oku_rapor())
        self.assertEqual(P.durum(self.sd)["son_rapor"], os.path.abspath(self.rapor))

    # ---- CLI
    def test_cli_dogrula_cikis_kodlari(self):
        self.yaz_rapor('   Kanıt: ara "iki" MEMORY.md => 1\n')
        self.assertEqual(self.kos(["perspektif", "dogrula", self.rapor]).returncode, 0)
        self.yaz_rapor('   Kanıt: ara "iki" MEMORY.md => 9\n')
        r = self.kos(["perspektif", "dogrula", self.rapor])
        self.assertEqual(r.returncode, 1)
        self.assertIn("1 tutmadı", r.stdout)

    def test_cli_duzeltme_tara_sentetik_uc_tekrar(self):
        for ad in ("a.md", "b.md", "c.md"):
            self.yaz_hafiza(ad, "- ML çöküşü " + NOT + "\n")
        r = self.kos(["perspektif", "duzeltme-tara", self.hafiza])
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("3 kez", r.stdout)

    def test_cli_duzeltme_tara_temiz_klasor(self):
        self.yaz_hafiza("a.md", "- ML çöküşü " + NOT + "\n")
        r = self.kos(["perspektif", "duzeltme-tara", self.hafiza])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_cli_duzeltme_tara_varsayilan_klasor(self):
        for ad in ("a.md", "b.md"):
            self.yaz_hafiza(ad, "- x " + NOT + "\n")
        self.assertEqual(self.kos(["perspektif", "duzeltme-tara"]).returncode, 1)


if __name__ == "__main__":
    unittest.main()