"""Şimdi sayfasında asılı ajan satırı (G-006).

Kabul kriterleri:
  K1  simdi.html asili_ajanlar doluyken ajan başına satır gösterir, boşken hiçbir şey göstermez
      (node ile sahte DOM üzerinde çalıştırılarak doğrulanır).
  K2  simdi.html asili_ajanlar alanını okuyan kodu içerir; ozet.yaz çıktısında alan vardır.
  K3  Tarayıcı yerine node: sayfanın satır içi betiği sahte O/DOM ile çalıştırılır, çizilen HTML denetlenir.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import datetime
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ozet  # noqa: E402

SIMDI = os.path.join(KOK, "assets", "simdi.html")
NODE = shutil.which("node")

# Sahte ortam: O.veri çağrılarını yakalar, cizici'ye veri verir, tüm innerHTML/textContent yazımlarını toplar.
HARNES = r"""
const fs = require('fs');
const [,, htmlYol, ozetJson] = process.argv;
const html = fs.readFileSync(htmlYol, 'utf8');
const betikler = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const kod = betikler[betikler.length - 1];
const kaplar = {};
function kap(ad) {
  if (kaplar[ad]) return kaplar[ad];
  const k = {
    ad, _html: '', _text: '', hidden: false, dataset: {}, style: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    set innerHTML(v) { this._html = String(v); }, get innerHTML() { return this._html; },
    set textContent(v) { this._text = String(v); }, get textContent() { return this._text; },
    contains: () => false, querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
    closest: () => null, setAttribute() {}, removeAttribute() {}, focus() {}, scrollIntoView() {},
  };
  return (kaplar[ad] = k);
}
const proxyFn = new Proxy(function () {}, { get: (t, p) => (p === 'then' ? undefined : proxyFn), apply: () => proxyFn });
global.document = { querySelector: s => kap(s), querySelectorAll: () => [], activeElement: null, addEventListener() {}, getElementById: s => kap('#' + s) };
global.matchMedia = () => ({ matches: false });
const dinleyici = [];
global.window = { addEventListener: (a, f) => dinleyici.push([a, f]), location: { hash: '' }, matchMedia };
const veriler = {};
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const O0 = {
  alan: 'a1',
  B: new Proxy({}, { get: () => (x => String(x ?? '')) }),
  E: { bekleyen: () => ({ renk: 'var(--neutral)', ad: 'x' }), durum: () => ({ renk: 'var(--neutral)', ad: 'x' }) },
  esc, yolGizle: s => String(s ?? ''), temizMetin: s => String(s ?? ''),
  depo: { al: () => '', koy() {} },
  kabuk() {}, alanBilgi: () => ({ ad: 'p' }),
  veri(url, ayar) { veriler[typeof url === 'function' ? 'ozet' : url] = ayar; return { durum: 'tamam', uzunHata: false }; },
};
const O = new Proxy(O0, { get: (t, p) => (p in t ? t[p] : (p === 'then' ? undefined : (() => ''))) });
global.O = O; window.O = O;
new Function('window', 'document', 'O', 'matchMedia', kod)(window, document, O, matchMedia);
const o = JSON.parse(ozetJson);
const ozetAyar = veriler.ozet;
const simdiAyar = veriler['/simdi.json'];
if (simdiAyar) simdiAyar.cizici({ oturumlar: [], akis: [], sayac: {} });
ozetAyar.cizici(o);
const cikti = Object.values(kaplar).map(k => k._html + ' ' + k._text + (k.hidden ? ' [GIZLI]' : '')).join('\n');
process.stdout.write(JSON.stringify({ cikti }));
"""


def temel_ozet(**ek):
    d = {"surum": 1, "acik": True, "orkestra": True, "proje": "p", "kartlar": [], "sayac": {},
         "maliyet": {"bugun": 0, "toplam": 0, "surec": {}, "model": {}, "ajan_surec": [], "oturumlar": []},
         "sohbetler": [], "defter": [], "perspektif": {"rapor": False}, "onaylar": []}
    d.update(ek)
    return d


class SimdiHtmlStatik(unittest.TestCase):
    def test_html_alani_okuyor(self):
        with open(SIMDI, encoding="utf-8") as f:
            h = f.read()
        self.assertIn("asili_ajanlar", h)
        # alan bir koşul/okuma içinde kullanılmalı (yalnız yorum değil)
        kodsuz = re.sub(r"/\*[\s\S]*?\*/|<!--[\s\S]*?-->|^\s*//.*$", "", h, flags=re.M)
        self.assertIn("asili_ajanlar", kodsuz)

    def test_html_yorum_disinda_dk_metni(self):
        with open(SIMDI, encoding="utf-8") as f:
            h = f.read()
        self.assertRegex(h, r"bitmeyen")


class OzetYazAlan(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_simdi_asili_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def _kayit(self, aid, dk):
        z = (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=dk)).isoformat(timespec="seconds")
        with open(os.path.join(self.sd, "oturumlar", f"acik_ajan_{aid}.json"), "w", encoding="utf-8") as f:
            json.dump({"zaman": z, "oturum": "o", "agent_id": aid, "ajan": "orkestra:isci-t2", "gorev": "G-001", "surec": "is"}, f)

    def test_ozet_yaz_alan_var_bos(self):
        o = ozet.yaz(self.sd, self.proje)
        self.assertIn("asili_ajanlar", o)
        self.assertEqual(o["asili_ajanlar"], [])

    def test_ozet_yaz_alan_dolu(self):
        self._kayit("x1", 50)
        self._kayit("taze", 2)
        ozet.yaz(self.sd, self.proje)
        with open(os.path.join(self.sd, "ozet.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual([a["agent_id"] for a in d["asili_ajanlar"]], ["x1"])
        a = d["asili_ajanlar"][0]
        for anahtar in ("ajan", "gorev", "dakika"):
            self.assertIn(anahtar, a)


@unittest.skipUnless(NODE, "node yok")
class SimdiNodeCizim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dizin = tempfile.mkdtemp(prefix="ork_simdi_node_")
        cls.harnes = os.path.join(cls.dizin, "harnes.js")
        with open(cls.harnes, "w", encoding="utf-8") as f:
            f.write(HARNES)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dizin, ignore_errors=True)

    def calistir(self, o):
        r = subprocess.run([NODE, self.harnes, SIMDI, json.dumps(o)], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        return json.loads(r.stdout)["cikti"]

    def test_dolu_ajan_basina_satir(self):
        c = self.calistir(temel_ozet(asili_ajanlar=[
            {"agent_id": "a1", "ajan": "orkestra:isci-zzq", "gorev": "G-777", "surec": "is", "oturum": "o", "dakika": 47},
            {"agent_id": "a2", "ajan": "orkestra:denetci-yyw", "gorev": "G-888", "surec": "is", "oturum": "o", "dakika": 93},
        ]))
        for parca in ("orkestra:isci-zzq", "G-777", "47", "orkestra:denetci-yyw", "G-888", "93"):
            self.assertIn(parca, c)
        self.assertIn("bitmeyen", c)
        self.assertIn("dk", c)

    def test_bos_liste_hicbir_sey_gostermez(self):
        c = self.calistir(temel_ozet(asili_ajanlar=[]))
        self.assertNotIn("bitmeyen", c)

    def test_alan_yoksa_gizli_ve_hatasiz(self):
        c = self.calistir(temel_ozet())
        self.assertNotIn("bitmeyen", c)

    def test_bozuk_alan_hata_vermez(self):
        for bozuk in (None, "x", {"a": 1}, 5):
            c = self.calistir(temel_ozet(asili_ajanlar=bozuk))
            self.assertNotIn("bitmeyen", c)

    def test_html_kacislanir(self):
        c = self.calistir(temel_ozet(asili_ajanlar=[
            {"agent_id": "a1", "ajan": "<img src=x onerror=1>", "gorev": "<b>G</b>", "surec": "is", "oturum": "o", "dakika": 31}]))
        self.assertNotIn("<img src=x", c)
        self.assertNotIn("<b>G</b>", c)
        self.assertIn("31", c)

    def test_gorevsiz_ajan_cizilir(self):
        c = self.calistir(temel_ozet(asili_ajanlar=[
            {"agent_id": "a1", "ajan": "Explore", "gorev": "-", "surec": None, "oturum": None, "dakika": 35}]))
        self.assertIn("Explore", c)
        self.assertIn("35", c)


if __name__ == "__main__":
    unittest.main()
