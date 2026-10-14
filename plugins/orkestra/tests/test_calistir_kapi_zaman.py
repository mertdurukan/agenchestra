"""calistir.js: test kapısı --zaman-asimi + zaman aşımı sınıfı (G-046 K1-K3).

`py -3.13 -m pytest plugins/orkestra/tests/test_calistir_kapi_zaman.py -q`

Sahte çalışma zamanı kapı ajanının istemini ve çağrı sayımını kaydeder. Kapı sonuçları senaryodan gelir
(kapi_kirmizi / kapi_yesil: tam sonuç nesneleri; null = ajan sonuç döndürmedi). node yoksa testler FAIL
olur (skip yok): node'suz koşu kırmızı/yeşil aşama için geçersizdir.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from test_calistir_akisi import BETIK, NODE, NODE_YOK_GEREKCE, kod_karti

KOSUM_JS = r"""
const fs = require('fs')
const [betikYolu, senaryoYolu] = process.argv.slice(-2)
const kaynak = fs.readFileSync(betikYolu, 'utf8').replace(/^export\s+const\s+meta/m, 'const meta')
const sen = JSON.parse(fs.readFileSync(senaryoYolu, 'utf8'))
const cagrilar = [], loglar = [], sayac = {}
function sira(ad, liste, varsayilan) {
  const i = (sayac[ad] = (sayac[ad] === undefined ? -1 : sayac[ad]) + 1)
  return Array.isArray(liste) && i < liste.length ? liste[i] : varsayilan
}
async function agent(istem, o) {
  cagrilar.push({ agentType: o.agentType, phase: o.phase, label: o.label, istem })
  if (o.agentType === 'orkestra:test-yazari') return { ozet: 'test yazıldı', ciktilar: ['t.py'], kanit: ['-'] }
  if (o.phase === 'Ön kontrol') return { gecti: true, ihlaller: [] }
  if (o.phase === 'Kapı') {
    const asama = /kirmizi$/.test(o.label) ? 'kirmizi' : 'yesil'
    return sira(asama, sen['kapi_' + asama], { gecti: true, cikis_kodu: 0, ozet: asama + ' gecti', cikti_kuyrugu: '' })
  }
  if (o.agentType === 'orkestra:denetci') return { karar: 'onay', bulgular: [] }
  return { ozet: 'iş yapıldı', ciktilar: ['x'], kanit: ['-'] }
}
async function parallel(fns) { return Promise.all(fns.map(f => f())) }
function log(m) { loglar.push(String(m)) }
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
new AsyncFunction('agent', 'parallel', 'log', 'args', kaynak)(agent, parallel, log, { gorevler: sen.gorevler })
  .then(sonuc => process.stdout.write(JSON.stringify({ sonuc, cagrilar, loglar })))
  .catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1) })
"""


def kapi(cikis, ozet, gecti=False, kuyruk=""):
    return {"gecti": gecti, "cikis_kodu": cikis, "ozet": ozet, "cikti_kuyrugu": kuyruk}


def zaman_asimi_kapisi():
    return kapi(-1, "orkestra: test_komutu zaman aşımına uğradı (600 sn)")


class KapiZamanTabani(unittest.TestCase):
    def setUp(self):
        if not NODE:  # skip yok: node'suz koşu kırmızı/yeşil için geçersizdir
            self.fail(NODE_YOK_GEREKCE)
        self.tmp = tempfile.mkdtemp(prefix="ork_kapi_zaman_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos(self, kart=None, **senaryo):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=[kart or kod_karti()]), f, ensure_ascii=False)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        p = subprocess.run([NODE, self.kosum, BETIK, yol], capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        c = json.loads(p.stdout.decode("utf-8"))
        return c["sonuc"]["sonuclar"][0], [x for x in c["cagrilar"] if x["phase"] != "Ön kontrol"]

    @staticmethod
    def say(cagrilar, **ol):
        return len([c for c in cagrilar if all(c.get(a) == d for a, d in ol.items())])

    @staticmethod
    def kapi_komutlari(cagrilar):
        """Kapı istemlerindeki `orkestra kart test-kos ...` komutları (asama -> komut)."""
        out = {}
        for c in cagrilar:
            if c["phase"] == "Kapı":
                m = re.search(r"`(orkestra kart test-kos [^`]*)`", c["istem"])
                out[c["label"].rsplit(" ", 1)[-1]] = m.group(1) if m else None
        return out


class ZamanAsimiBayragi(KapiZamanTabani):
    """K1"""

    def komutlar(self, **kart_ek):
        _, c = self.kos(kod_karti(**kart_ek))
        k = self.kapi_komutlari(c)
        self.assertEqual(sorted(k), ["kirmizi", "yesil"])
        return k

    def test_k1_kartta_test_zaman_asimi_kullanilir(self):
        for asama, komut in self.komutlar(test_zaman_asimi=900).items():
            with self.subTest(asama=asama):
                self.assertRegex(komut, r"--zaman-asimi 900(\s|$)")
                self.assertNotIn("--zaman-asimi 1800", komut)
                self.assertIn(f"--asama {asama}", komut)

    def test_k1_alan_yoksa_varsayilan_1800(self):
        for asama, komut in self.komutlar().items():
            with self.subTest(asama=asama):
                self.assertRegex(komut, r"--zaman-asimi 1800(\s|$)")

    def test_k1_gecersiz_degerlerde_varsayilan_1800(self):
        for gecersiz in (0, -5, "abc", "900", None, [], 0.0):
            with self.subTest(deger=gecersiz):
                for komut in self.komutlar(test_zaman_asimi=gecersiz).values():
                    self.assertRegex(komut, r"--zaman-asimi 1800(\s|$)")
                    self.assertEqual(komut.count("--zaman-asimi"), 1)

    def test_k1_komut_tek_zaman_asimi_bayragi(self):
        for komut in self.komutlar(test_zaman_asimi=450).values():
            self.assertEqual(komut.count("--zaman-asimi"), 1)
            self.assertTrue(komut.startswith("orkestra kart test-kos G-900 --asama "))


class ZamanAsimiSinifi(KapiZamanTabani):
    """K2"""

    def dogrula_sinif(self, s):
        self.assertEqual(s["durum"], "kart-duzeltilmeli")
        self.assertEqual(s["neden"], "kapi-zaman-asimi")
        self.assertEqual(s["basamak"], "T2")
        metin = json.dumps(s, ensure_ascii=False)
        self.assertIn("test_zaman_asimi", metin)  # düzeltme talimatı
        self.assertIn("test_komutu", metin)
        self.assertIn("zaman-asimi", json.dumps(s.get("gecmis", []), ensure_ascii=False),
                      "gecmis kaydında karar 'zaman-asimi' yok: " + metin)

    def test_k2_kirmizi_kapi_cikis_eksi1(self):
        s, c = self.kos(kapi_kirmizi=[zaman_asimi_kapisi()] * 10)
        self.dogrula_sinif(s)
        self.assertEqual(self.say(c, phase="Kapı"), 1)  # ek kapı denemesi yok
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 1)  # yeniden deneme yok
        self.assertEqual(self.say(c, phase="İş"), 0)
        self.assertEqual(self.say(c, phase="Denetim"), 0)

    def test_k2_yesil_kapi_cikis_eksi1(self):
        s, c = self.kos(kapi_yesil=[zaman_asimi_kapisi()] * 30)
        self.dogrula_sinif(s)
        self.assertEqual(self.say(c, phase="Kapı", label="G-900 kapı yesil"), 1)
        self.assertEqual([x["agentType"] for x in c if x["phase"] == "İş"], ["orkestra:isci-t2"])
        self.assertEqual(self.say(c, phase="Denetim"), 0)

    def test_k2_yukselt_cagrilmaz(self):
        s, c = self.kos(kapi_yesil=[zaman_asimi_kapisi()] * 30)
        self.assertEqual([x for x in c if x["agentType"] in ("orkestra:isci-t3", "orkestra:isci-t4")], [])
        self.assertNotEqual(s["durum"], "reddedildi")

    def test_k2_kuyrukta_orkestra_onekli_zaman_asimi_satiri(self):
        kuyruk = "1 passed\norkestra: komut zaman aşımına uğradı (600 sn)"
        for cikis in (1, 4):
            with self.subTest(cikis=cikis, asama="kirmizi"):
                s, c = self.kos(kapi_kirmizi=[kapi(cikis, "kapı geçmedi", kuyruk=kuyruk)] * 10)
                self.dogrula_sinif(s)
                self.assertEqual(self.say(c, phase="Kapı"), 1)
                self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 1)
            with self.subTest(cikis=cikis, asama="yesil"):
                s, c = self.kos(kapi_yesil=[kapi(cikis, "kapı geçmedi", kuyruk=kuyruk)] * 30)
                self.dogrula_sinif(s)
                self.assertEqual(self.say(c, phase="İş"), 1)

    def test_k2_onekli_olmayan_zaman_asimi_metni_sinifa_girmez(self):
        # pytest çıktısındaki 'zaman aşımı' geçen satır (önek yok) gerçek test başarısızlığıdır
        kuyruk = "E   AssertionError: zaman aşımı bekleniyordu\n1 failed"
        s, c = self.kos(kapi_yesil=[kapi(4, "yesil False", kuyruk=kuyruk)] * 30)
        self.assertNotEqual(s.get("neden"), "kapi-zaman-asimi")
        self.assertEqual(s["durum"], "reddedildi")

    def test_k2_gercek_basarisizlik_eski_akis(self):
        s, c = self.kos(kapi_kirmizi=[kapi(4, "kırmızı False")] * 10)
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual(s["neden"], "kirmizi-teyit")
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 3)

    def test_k2_zaman_asimindan_sonra_gecen_sonuc_beklenmez(self):
        s, c = self.kos(kapi_kirmizi=[zaman_asimi_kapisi(), kapi(0, "ok", gecti=True)])
        self.assertEqual(s["durum"], "kart-duzeltilmeli")
        self.assertEqual(self.say(c, phase="Kapı"), 1)


class KapiAjaniYok(KapiZamanTabani):
    """K3: ajan sonuç döndürmezse (null) bugünkü davranış."""

    def test_k3_kirmizi_ajan_yok_zaman_asimi_sinifina_girmez(self):
        s, c = self.kos(kapi_kirmizi=[None] * 10)
        self.assertNotEqual(s.get("neden"), "kapi-zaman-asimi")
        self.assertNotEqual(s["durum"], "kart-duzeltilmeli")
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual(s["neden"], "kirmizi-teyit")
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 3)
        self.assertEqual(self.say(c, phase="İş"), 0)

    def test_k3_yesil_ajan_yok_eski_yukseltme_akisi(self):
        s, c = self.kos(kapi_yesil=[None] * 30)
        self.assertNotEqual(s.get("neden"), "kapi-zaman-asimi")
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual([x["agentType"] for x in c if x["phase"] == "İş"],
                         ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2 + ["orkestra:isci-t4"] * 2)

    def test_k3_ajan_yok_ozeti_degismez_ve_ayirt_edici_alan(self):
        with open(BETIK, encoding="utf-8") as f:
            satirlar = [l for l in f.read().splitlines() if "kapı ajanı sonuç döndürmedi" in l]
        self.assertEqual(len(satirlar), 1)
        self.assertIn("ajan_yok: true", satirlar[0])
        self.assertIn("cikis_kodu: -1", satirlar[0])


if __name__ == "__main__":
    unittest.main()
