"""calistir.js: test kapısı CLI/yapılandırma hatasında yeniden deneme/yükseltme yok (G-013).

`py -3.13 -m pytest plugins/orkestra/tests/test_calistir_cli_hatasi.py -q`

Kapı adımı (kırmızı/yeşil `orkestra kart test-kos`) çıkış 2 ya da yapılandırma hatası metni döndürürse kart
hemen 'kart-duzeltilmeli' ile ana ajana döner. Gerçek test başarısızlıkları (çıkış 4) eski akışta kalır.
Sahte çalışma zamanında kapı sonuçları senaryodan (kapi_kirmizi / kapi_yesil: tam sonuç nesneleri) gelir.
node yoksa açık gerekçeyle skip edilir.
"""
import json
import os
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
  cagrilar.push({ agentType: o.agentType, phase: o.phase, label: o.label })
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

CLI_HATALARI = [
    (2, "test dosyası yok: test_alani 'tests/test_a.py' hiçbir proje dosyasına uymuyor"),
    (2, "kilit yok: önce kırmızı aşama koşulmalı"),
    (2, "test_komutu/test_alani yok: kart test kapısı için yapılandırılmamış"),
    (2, "test_komutu test_alani dosyalarını kapsamıyor"),
    # çıkış kodu 1/2 dışında gelse de metin yapılandırma hatasını gösteriyorsa aynı kural
    (1, "orkestra: test_alani hiçbir proje dosyasına uymuyor"),
]


def kapi(cikis, ozet, gecti=False, kuyruk=""):
    return {"gecti": gecti, "cikis_kodu": cikis, "ozet": ozet, "cikti_kuyrugu": kuyruk}


@unittest.skipUnless(NODE, NODE_YOK_GEREKCE)
class CliHatasiTestleri(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_cli_hata_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos(self, **senaryo):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=[kod_karti()]), f, ensure_ascii=False)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        p = subprocess.run([NODE, self.kosum, BETIK, yol], capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        c = json.loads(p.stdout.decode("utf-8"))
        return c["sonuc"]["sonuclar"][0], [x for x in c["cagrilar"] if x["phase"] != "Ön kontrol"]

    @staticmethod
    def say(cagrilar, **ol):
        return len([c for c in cagrilar if all(c.get(a) == d for a, d in ol.items())])

    # --- 1) kırmızı aşamada CLI hatası
    def test_kirmizi_cli_hatasi_kart_duzeltilmeli_tek_deneme(self):
        for cikis, mesaj in CLI_HATALARI:
            with self.subTest(mesaj=mesaj):
                s, c = self.kos(kapi_kirmizi=[kapi(cikis, mesaj)] * 5)
                self.assertEqual(s["durum"], "kart-duzeltilmeli")
                self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 1)
                self.assertEqual(self.say(c, phase="Kapı"), 1)
                self.assertEqual(self.say(c, phase="İş"), 0)
                self.assertEqual(self.say(c, phase="Denetim"), 0)
                self.assertIn(mesaj, json.dumps(s, ensure_ascii=False))  # gerekçe: CLI satırı

    def test_kirmizi_cli_hatasi_basamak_yukseltmez(self):
        s, c = self.kos(kapi_kirmizi=[kapi(2, "kilit yok")] * 5)
        self.assertEqual(s["basamak"], "T2")
        self.assertNotEqual(s["durum"], "reddedildi")

    # --- 2) yeşil aşamada CLI hatası
    def test_yesil_cli_hatasi_kart_duzeltilmeli_tek_deneme(self):
        for cikis, mesaj in CLI_HATALARI:
            with self.subTest(mesaj=mesaj):
                s, c = self.kos(kapi_yesil=[kapi(cikis, mesaj)] * 20)
                self.assertEqual(s["durum"], "kart-duzeltilmeli")
                self.assertEqual(self.say(c, phase="İş"), 1)  # işçi yalnız ilk turda; yeniden/yükseltme yok
                self.assertEqual(self.say(c, phase="Kapı", label="G-900 kapı yesil"), 1)
                self.assertEqual(self.say(c, phase="Denetim"), 0)
                self.assertEqual(s["basamak"], "T2")
                self.assertIn(mesaj, json.dumps(s, ensure_ascii=False))

    # --- 3) geriye uyum: gerçek başarısızlıklar eski akışta
    def test_gercek_kirmizi_basarisizligi_eski_davranis(self):
        s, c = self.kos(kapi_kirmizi=[kapi(4, "kırmızı False")] * 5)
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual(s["neden"], "kirmizi-teyit")
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 3)  # 1 + 2 yeniden deneme
        self.assertEqual(self.say(c, phase="İş"), 0)

    def test_gercek_yesil_basarisizligi_eski_davranis(self):
        s, c = self.kos(kapi_yesil=[kapi(4, "yesil False", kuyruk="1 failed")] * 20)
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual([x["agentType"] for x in c if x["phase"] == "İş"],
                         ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2 + ["orkestra:isci-t4"] * 2)
        self.assertEqual(self.say(c, phase="Denetim"), 0)

    def test_kirmizi_gercek_basarisizlik_sonra_gecer_devam_eder(self):
        s, c = self.kos(kapi_kirmizi=[kapi(4, "kırmızı False"), kapi(0, "ok", gecti=True)])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 2)

    def test_yesil_gercek_basarisizlik_sonra_gecer_devam_eder(self):
        s, c = self.kos(kapi_yesil=[kapi(4, "yesil False"), kapi(0, "ok", gecti=True)])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(self.say(c, phase="İş"), 2)


    # --- SON RET: kalıp kelimeler gerçek pytest çıktısında geçse de CLI hatası sayılmaz
    PYTEST_KUYRUGU = "\n".join([
        "FAILED tests/test_agac_test_kapisi.py::T::test_x - AssertionError: assert 'kapsamıyor' in 'ok'",
        "SUBFAILED(mesaj='kapsamıyor') tests/test_test_koku.py::T::test_y",
        "E   AssertionError: kilit yok / hiçbir proje dosyasına uymuyor / test_komutu/test_alani yok",
        "1 failed, 3 passed",
    ])

    def test_gercek_yesil_basarisizligi_pytest_satirinda_kalip_cikis4_eski_akis(self):
        self.yesil_eski_akis(4)

    def test_gercek_yesil_basarisizligi_pytest_satirinda_kalip_cikis1_eski_akis(self):
        self.yesil_eski_akis(1)

    def yesil_eski_akis(self, cikis):
        s, c = self.kos(kapi_yesil=[kapi(cikis, "yesil False", kuyruk=self.PYTEST_KUYRUGU)] * 20)
        self.assertNotEqual(s["durum"], "kart-duzeltilmeli")
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual([x["agentType"] for x in c if x["phase"] == "İş"],
                         ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2 + ["orkestra:isci-t4"] * 2)

    def test_gercek_kirmizi_basarisizligi_pytest_satirinda_kalip_eski_akis(self):
        for cikis in (4, 1):
            with self.subTest(cikis=cikis):
                s, c = self.kos(kapi_kirmizi=[kapi(cikis, "kırmızı False", kuyruk=self.PYTEST_KUYRUGU)] * 5)
                self.assertEqual(s["durum"], "reddedildi")
                self.assertEqual(s["neden"], "kirmizi-teyit")
                self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 3)

    def test_orkestra_onekli_cli_satiri_kuyrukta_cikis1_kart_duzeltilmeli(self):
        cli = "orkestra: test dosyası yok: test_alani ('tests/test_a.py') hiçbir proje dosyasına uymuyor."
        kuyruk = "\n".join(["1 failed", cli])
        s, c = self.kos(kapi_kirmizi=[kapi(1, "kapı geçmedi", kuyruk=kuyruk)] * 5)
        self.assertEqual(s["durum"], "kart-duzeltilmeli")
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 1)
        s, c = self.kos(kapi_yesil=[kapi(1, "kapı geçmedi", kuyruk=kuyruk)] * 20)
        self.assertEqual(s["durum"], "kart-duzeltilmeli")
        self.assertEqual(self.say(c, phase="İş"), 1)


if __name__ == "__main__":
    unittest.main()
