"""G-161: tek model politikası dosyası (ayarlar/model_politikasi.json), scripts/model_politika.py, orkestra politika goster,
calistir.js saf yardımcıları (basamakModeli/denetciModeli) ve kural metinleri.

`py -3.13 -m pytest plugins/orkestra/tests/test_model_politika.py -q`
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from test_calistir_akisi import BETIK, KOK, NODE, NODE_YOK_GEREKCE

sys.path.insert(0, os.path.join(KOK, "scripts"))
import model_politika as MP  # noqa: E402

AYAR = os.path.join(KOK, "ayarlar", "model_politikasi.json")
ORK = os.path.join(KOK, "scripts", "orkestra.py")


def js_kaynagi():
    with open(BETIK, encoding="utf-8") as f:
        return f.read()


def js_parcasi():
    """Sabit tablolar + 'model politikası' saf yardımcı bölümü (calistir.js kaynak metninden)."""
    js = js_kaynagi()
    sabitler = js[js.index("const DENETCI = {"): js.index("const DENETCI_OPUS_RET_ESIGI")]
    esik = re.search(r"^const DENETCI_OPUS_RET_ESIGI = \d+$", js, re.M).group(0)
    blok = js[js.index("// ---- model politikası (saf"): js.index("// ---- model politikası sonu")]
    return sabitler + esik + "\n" + blok


def js_calistir(ifade, politika=None):
    """ifade: JS ifadesi; `politika` değişkeni verilen nesne (None → null). JSON sonucu döner."""
    with tempfile.TemporaryDirectory(prefix="ork_pol_") as tmp:
        yol = os.path.join(tmp, "k.js")
        with open(yol, "w", encoding="utf-8") as f:
            f.write(js_parcasi() + "\nconst politika = " + json.dumps(politika) + "\n"
                    "process.stdout.write(JSON.stringify(" + ifade + "))\n")
        p = subprocess.run([NODE, yol], capture_output=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError(p.stderr.decode("utf-8", "replace"))
    return json.loads(p.stdout.decode("utf-8"))


class DosyaVeCli(unittest.TestCase):
    def test_k1_dosya_sema(self):
        with open(AYAR, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["surum"], 1)
        self.assertEqual(d["ana_ajan"]["varsayilan"], "claude-sonnet-5-5")
        self.assertEqual(d["yasak"], ["claude-fable-5-1"])
        self.assertEqual(d["planlayici_yukseltme"], {"kosul": ["belirsiz", "cok-modul"], "model": "opus"})
        self.assertEqual(d["basamak"]["T3"], {"model": "opus", "effort": "medium"})
        self.assertEqual(d["basamak"]["T4"], {"model": "opus", "effort": "xhigh"})
        self.assertEqual(d["karar"], {"min_n": 20, "ilk_gecis_fark": 0.05, "usd_fark": 0.10, "dk_fark": 0.10})
        self.assertEqual(d["yukseltme_sirasi"], ["effort", "model"])

    def test_k1_cli_goster_ve_json(self):
        p = subprocess.run([sys.executable, ORK, "politika", "goster", "--json"], capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        with open(AYAR, encoding="utf-8") as f:
            self.assertEqual(json.loads(p.stdout.decode("utf-8")), json.load(f))
        q = subprocess.run([sys.executable, ORK, "politika", "goster"], capture_output=True, timeout=60)
        self.assertEqual(q.returncode, 0)
        metin = q.stdout.decode("utf-8")
        self.assertIn("T3: model=opus effort=medium", metin)
        self.assertIn("claude-fable-5-1", metin)


class PythonModulu(unittest.TestCase):
    def test_k2_yukle_tablo_yasak(self):
        self.assertEqual(MP.basamak_tablosu()["T2"], {"model": "sonnet", "effort": "medium"})
        self.assertTrue(MP.yasak_mi("claude-fable-5-1"))
        self.assertTrue(MP.yasak_mi("fable"))
        self.assertFalse(MP.yasak_mi("claude-sonnet-5-5"))
        self.assertFalse(MP.yasak_mi(""))

    def test_k2_proje_ezmesi(self):
        with tempfile.TemporaryDirectory(prefix="ork_pol_") as sd:
            with open(os.path.join(sd, "model_politikasi.json"), "w", encoding="utf-8") as f:
                json.dump({"basamak": {"T3": {"effort": "high"}}, "yasak": ["claude-x-1"], "karar": {"min_n": 5}}, f)
            c = MP.yukle(sd)
            self.assertEqual(c["basamak"]["T3"], {"model": "opus", "effort": "high"})
            self.assertEqual(c["basamak"]["T1"]["model"], "haiku")
            self.assertEqual(c["karar"]["min_n"], 5)
            self.assertEqual(c["karar"]["usd_fark"], 0.10)
            self.assertTrue(MP.yasak_mi("claude-x-1", sd))
            self.assertFalse(MP.yasak_mi("claude-fable-5-1", sd))
        # ezme yoksa taban aynen
        self.assertEqual(MP.yukle("/yok/klasor")["basamak"]["T3"]["effort"], "medium")

    def test_k2_dosya_bozuksa_yedek(self):
        eski = MP.AYAR_DOSYASI
        try:
            MP.AYAR_DOSYASI = os.path.join(tempfile.gettempdir(), "yok_model_politikasi.json")
            self.assertEqual(MP.basamak_tablosu()["T4"]["effort"], "xhigh")
        finally:
            MP.AYAR_DOSYASI = eski


class CalistirJs(unittest.TestCase):
    def setUp(self):
        if not NODE:
            self.fail(NODE_YOK_GEREKCE)
        with open(AYAR, encoding="utf-8") as f:
            self.dosya = json.load(f)

    def test_k3_dosyadan_tablo(self):
        pol = copy.deepcopy(self.dosya)
        pol["basamak"]["T2"] = {"model": "opus", "effort": "low"}
        self.assertEqual(js_calistir("basamakModeli('T2', {}, politika)", pol), {"model": "opus", "effort": "low"})

    def test_k3_dosya_yoksa_sabit_yedek(self):
        self.assertEqual(js_calistir("basamakModeli('T2', {}, null)"), {"model": "sonnet", "effort": "medium"})
        self.assertEqual(js_calistir("basamakModeli('T4', {}, null)"), {"model": "opus", "effort": "xhigh"})
        self.assertEqual(js_calistir("basamakModeli('T1', {}, null)"), {"model": "haiku"})

    def test_k3_yedek_dosyayla_ayni(self):
        for b, v in self.dosya["basamak"].items():
            y = js_calistir(f"basamakModeli('{b}', {{}}, null)")
            self.assertEqual(y["model"], v["model"], b)
            if b != "T1":  # T1 yedekte effort'suz (haiku); dosyada medium
                self.assertEqual(y["effort"], v["effort"], b)

    def test_k3_ezme_birlestirme(self):
        y = js_calistir("basamakModeli('T3', {}, politikaBirlestir(politika, {basamak: {T3: {effort: 'high'}}}))", self.dosya)
        self.assertEqual(y, {"model": "opus", "effort": "high"})

    def test_k4_kart_effort_oncelik(self):
        self.assertEqual(js_calistir("basamakModeli('T2', {effort: 'high'}, politika)", self.dosya),
                         {"model": "sonnet", "effort": "high"})
        self.assertEqual(js_calistir("denetciModeli('T2', 0, {effort: 'xhigh'}, politika)", self.dosya),
                         {"model": "sonnet", "effort": "xhigh"})
        # geçersiz ya da boş kart effort'u yok sayılır
        self.assertEqual(js_calistir("basamakModeli('T2', {effort: 'bilinmez'}, politika)", self.dosya)["effort"], "medium")
        self.assertEqual(js_calistir("basamakModeli('T2', {}, politika)", self.dosya)["effort"], "medium")

    def test_k4_t3_isci_md_ile_ayni(self):
        with open(os.path.join(KOK, "agents", "isci-t3.md"), encoding="utf-8") as f:
            md = f.read()
        md_effort = re.search(r"^effort:\s*(\S+)", md, re.M).group(1)
        self.assertEqual(js_calistir("basamakModeli('T3', {}, politika)", self.dosya)["effort"], md_effort)
        self.assertEqual(js_calistir("denetciModeli('T3', 0, {}, politika)", self.dosya)["effort"], md_effort)
        self.assertEqual(js_calistir("denetciModeli('T3', 0, {}, null)")["effort"], md_effort)

    def test_k4_cagrilara_baglandi(self):
        js = js_kaynagi()
        self.assertIn("...basamakModeli(basamak, k)", js)
        self.assertIn("denetciModeli(basamak, toplamRet, k)", js)
        self.assertIn("POLITIKA = await politikaYukle(args)", js)

    def test_k4_ret_esigi_sonrasi_denetci_opus(self):
        self.assertEqual(js_calistir("denetciModeli('T2', 2, {}, politika)", self.dosya), {"model": "opus", "effort": "high"})

    def test_k5_yasak_model_varsayilana_duser(self):
        pol = copy.deepcopy(self.dosya)
        pol["basamak"]["T2"] = {"model": "claude-fable-5-1", "effort": "medium"}
        self.assertEqual(js_calistir("basamakModeli('T2', {}, politika)", pol)["model"], "sonnet")
        self.assertEqual(js_calistir("denetciModeli('T2', 0, {}, politika)", pol)["model"], "sonnet")
        pol["basamak"]["T3"] = {"model": "fable", "effort": "medium"}
        self.assertEqual(js_calistir("basamakModeli('T3', {}, politika)", pol)["model"], "opus")
        self.assertTrue(js_calistir("yasakMi('claude-fable-5-1', politika)", self.dosya))
        self.assertFalse(js_calistir("yasakMi('sonnet', politika)", self.dosya))

    def test_k5_yasak_hicbir_basamakta_cikmaz(self):
        pol = copy.deepcopy(self.dosya)
        for b in pol["basamak"]:
            pol["basamak"][b]["model"] = "claude-fable-5-1"
        for b in ("T1", "T2", "T3", "T4"):
            y = js_calistir(f"[basamakModeli('{b}', {{}}, politika), denetciModeli('{b}', 3, {{}}, politika)]", pol)
            for d in y:
                self.assertNotIn("fable", d["model"])


class KuralMetinleri(unittest.TestCase):
    DOSYALAR = ("KURALLAR.md", os.path.join("skills", "is", "SKILL.md"), os.path.join("agents", "triyaj.md"))

    def test_k6_sayi_tekrari_yok_ve_yonlendirme_var(self):
        for d in self.DOSYALAR:
            with open(os.path.join(KOK, d), encoding="utf-8") as f:
                m = f.read()
            self.assertEqual(m.count("Opus medium"), 0, d)
            self.assertEqual(len(re.findall(r"^.*ayarlar/model_politikasi\.json.*$", m, re.M)), 1, d)


if __name__ == "__main__":
    unittest.main()
