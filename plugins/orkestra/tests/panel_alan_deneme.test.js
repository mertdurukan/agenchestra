// node tests/panel_alan_deneme.test.js — app.js açılışı: /alanlar.json hata verirse en çok 6 kez yeniden denenir (basla), liste gelince dolar;
// hep hata ya da dizi olmayan gövde: 6 çağrı, boş-liste iletisi kalır; alan yokken hashchange veri getirmez.
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '..', 'assets', 'app.js'), 'utf8');

assert(/window\.addEventListener\('hashchange', \(\) => \{ if \(!V\.alan\) return;/.test(src), 'hashchange alan yokken dönmüyor');

async function calistir(cevaplar) {
  let cagri = 0, ana = '';
  const stub = () => new Proxy(function () {}, { get: (t, k) => k === Symbol.toPrimitive ? () => '' : k === 'innerHTML' ? '' : stub(), apply: () => stub(), set: () => true });
  const el = new Proxy({}, { get: (t, k) => k === Symbol.toPrimitive ? () => '' : k === 'classList' ? { add() {}, remove() {}, toggle() {} } : stub(), set: () => true });
  const anaEl = { get innerHTML() { return ana; }, set innerHTML(v) { ana = v; }, focus() {} };
  const doc = { getElementById: id => id === 'ana' ? anaEl : el, querySelector: () => el, querySelectorAll: () => [], createElement: () => el, addEventListener() {}, documentElement: el, body: el, title: '' };
  const win = { addEventListener() {}, location: { search: '', hash: '#/ayarlar' }, scrollTo() {}, matchMedia: () => ({ matches: false, addEventListener() {} }), localStorage: { getItem: () => null, setItem() {} } };
  const ctx = {
    window: win, document: doc, location: win.location, localStorage: win.localStorage, navigator: {}, console, URLSearchParams, AbortController,
    setTimeout: f => setTimeout(f, 0), clearTimeout, setInterval: () => 0, clearInterval() {}, requestAnimationFrame: () => 0,
    EventSource: function () { return { addEventListener() {}, close() {} }; },
    fetch: async u => {
      if (u !== '/alanlar.json') return { ok: true, json: async () => ({}) };
      const c = cevaplar[Math.min(cagri++, cevaplar.length - 1)];
      if (c instanceof Error) throw c;
      return { ok: c.ok !== false, json: async () => c.govde };
    },
  };
  vm.runInNewContext(src, ctx, { timeout: 5000 });
  await new Promise(r => setTimeout(r, 500));
  return { cagri, ana };
}

(async () => {
  const hata = new Error('ağ'), dolu = { govde: [{ id: 'a1', ad: 'p', orkestra: true }] };
  let r = await calistir([hata, hata, dolu]);
  assert.strictEqual(r.cagri, 3, '3. denemede başarı: 3 çağrı beklenir');
  assert(!/Orkestralı çalışma alanı yok/.test(r.ana), 'liste gelince boş-liste iletisi görünmemeli');
  r = await calistir([hata]);
  assert.strictEqual(r.cagri, 6, 'hep hata: tam 6 çağrı');
  assert(/Orkestralı çalışma alanı yok/.test(r.ana), 'hep hata: boş-liste iletisi kalmalı');
  r = await calistir([{ govde: { hata: 1 } }]);
  assert.strictEqual(r.cagri, 6, 'dizi olmayan gövde başarısız sayılır: 6 çağrı');
  assert(/Orkestralı çalışma alanı yok/.test(r.ana), 'dizi olmayan gövde: boş-liste iletisi kalmalı');
  r = await calistir([{ ok: false, govde: [] }]);
  assert.strictEqual(r.cagri, 6, 'HTTP hata durumu başarısız sayılır: 6 çağrı');
  console.log('4 vaka + hashchange koruması: geçti');
})().catch(e => { console.error(e); process.exit(1); });
