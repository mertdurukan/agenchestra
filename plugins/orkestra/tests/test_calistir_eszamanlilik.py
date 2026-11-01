"""workflows/calistir.js eşzamanlılık sınırlayıcı, altyapı hatası yeniden denemesi, kritik yol önceliği ve ölçüm.

Sahte `agent` ile node'da koşar (test_calistir_paralel.py yöntemi); node yoksa skip edilir.
Kartlar belge sınıfı (kod dışı) T1; işçi kapısı geçer, denetçi onaylar.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BETIK = os.path.join(KOK, "workflows", "calistir.js")
NODE = os.environ.get("ORKESTRA_NODE") or shutil.which("node")

KOSUM_JS = r"""
const fs = require('fs')
const [betikYolu, senaryoYolu] = process.argv.slice(-2)
const kaynak = fs.readFileSync(betikYolu, 'utf8').replace(/^export\s+const\s+meta/m, 'const meta')
const sen = JSON.parse(fs.readFileSync(senaryoYolu, 'utf8'))
const bekle = ms => new Promise(r => setTimeout(r, ms || 0))
let aktif = 0, enCok = 0
const baslama = []   // işçi ajanlarının başlama sırası (kart id)
const hatalar = {}   // kart id -> kalan fırlatılacak hata sayısı
Object.assign(hatalar, sen.hata_say || {})
const bosKalan = Object.assign({}, sen.bos_say || {})
async function agent(istem, o) {
  const id = String(o.label).split(' ')[0]
  aktif++; enCok = Math.max(enCok, aktif)
  try {
    await bekle(sen.gecikme_ms || 5)
    if (o.agentType === 'orkestra:denetci') return { karar: 'onay', bulgular: [] }
    baslama.push(id)
    if (hatalar[id] > 0) { hatalar[id]--; throw new Error('429 aşırı yük') }
    if (bosKalan[id] > 0) { bosKalan[id]--; return null }
    return { ozet: 'iş yapıldı', ciktilar: ['x'], kanit: ['-'], kapi: 'gecti' }
  } finally { aktif-- }
}
async function parallel(fns) { return Promise.all(fns.map(f => f())) }
const loglar = []
function log(m) { loglar.push(String(m)) }
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const args = Object.assign({ gorevler: sen.gorevler }, sen.args || {})
new AsyncFunction('agent', 'parallel', 'log', 'args', kaynak)(agent, parallel, log, args)
  .then(sonuc => process.stdout.write(JSON.stringify({ sonuc, enCok, baslama, loglar })))
  .catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1) })
"""


def kart(id_, bag=(), alan=None):
    return {"id": id_, "baslik": "iş " + id_, "basamak": "T1", "girdi": "", "sinif": "belge",
            "kabul_kriterleri": ["tamam; kontrol: 1"], "yazma_alani": [alan or f"belge/{id_}.md"],
            "bagimliliklar": list(bag)}


@unittest.skipUnless(NODE, "node bulunamadı: calistir.js eşzamanlılık senaryoları koşturulamadı")
class Eszamanlilik(unittest.TestCase):
    def kos(self, kartlar, **sen):
        with tempfile.TemporaryDirectory() as d:
            js, sy = os.path.join(d, "k.js"), os.path.join(d, "s.json")
            with open(js, "w", encoding="utf-8") as f:
                f.write(KOSUM_JS)
            with open(sy, "w", encoding="utf-8") as f:
                json.dump(dict(gorevler=kartlar, **sen), f)
            r = subprocess.run([NODE, js, BETIK, sy], capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)

    def test_varsayilan_sinirsiz(self):
        c = self.kos([kart(f"G-{i}") for i in range(1, 7)])
        self.assertGreaterEqual(c["enCok"], 6)
        self.assertEqual(c["sonuc"]["olcum"]["son_sinir"], None)
        self.assertEqual(c["sonuc"]["olcum"]["yeniden_deneme"], 0)

    def test_en_cok_ajan_sinirlar(self):
        c = self.kos([kart(f"G-{i}") for i in range(1, 9)], args={"en_cok_ajan": 3})
        self.assertLessEqual(c["enCok"], 3)
        self.assertTrue(all(s["durum"] == "onaylandi" for s in c["sonuc"]["sonuclar"]))
        self.assertGreater(c["sonuc"]["olcum"]["kuyruk_bekleme_ms"], 0)

    def test_istisna_yeniden_denenir_ve_sinir_duser(self):
        kartlar = [kart(f"G-{i}") for i in range(1, 7)]
        c = self.kos(kartlar, hata_say={"G-1": 1, "G-2": 1})
        o = c["sonuc"]["olcum"]
        self.assertEqual(o["yeniden_deneme"], 2)
        self.assertGreaterEqual(o["sinir_dususu"], 1)
        self.assertTrue(all(s["durum"] == "onaylandi" for s in c["sonuc"]["sonuclar"]), c["sonuc"]["sonuclar"])

    def test_istisna_tavan_asilirsa_hata(self):
        c = self.kos([kart("G-1")], hata_say={"G-1": 99}, args={"ajan_yeniden_deneme": 1})
        self.assertEqual(c["sonuc"]["sonuclar"][0]["durum"], "hata")
        self.assertEqual(c["sonuc"]["olcum"]["yeniden_deneme"], 1)

    def test_bos_sonuc_varsayilan_yeniden_denenmez(self):
        c = self.kos([kart("G-1")], bos_say={"G-1": 1})
        self.assertEqual(c["sonuc"]["sonuclar"][0]["durum"], "hata")
        self.assertEqual(c["sonuc"]["olcum"]["yeniden_deneme"], 0)

    def test_bos_sonuc_istenirse_yeniden_denenir(self):
        c = self.kos([kart("G-1")], bos_say={"G-1": 1}, args={"bos_yeniden_deneme": 1})
        self.assertEqual(c["sonuc"]["sonuclar"][0]["durum"], "onaylandi")
        self.assertEqual(c["sonuc"]["olcum"]["yeniden_deneme"], 1)

    def test_kritik_yol_once_girer(self):
        # Sınır 1: G-9 (zincirin başı, yükseklik 3) kuyrukta G-1..G-3 (yükseklik 1) kartlarından önce girmeli.
        kartlar = [kart("G-1"), kart("G-2"), kart("G-3"), kart("G-9"), kart("G-10", ["G-9"]), kart("G-11", ["G-10"])]
        c = self.kos(kartlar, args={"en_cok_ajan": 1})
        self.assertLess(c["baslama"].index("G-9"), c["baslama"].index("G-3"), c["baslama"])


if __name__ == "__main__":
    unittest.main()
