'use strict';
// I-137 P3: panel v2 (assets/app.js) için sahte tarayıcı. Kullanım: node panel_duman.js <app.js> <fixture.json> <senaryolar.json> <cikti.json>
// Her senaryo: { depo: {anahtar: değer|null}, hash, adimlar: [['tikla', eylem, veri] | ['tus', tus]] } → { ray, bas, ana, depo, hash }.
const fs = require('fs');
const vm = require('vm');

const [, , uygulamaYol, fixtureYol, senaryoYol, ciktiYol] = process.argv;
const fx = JSON.parse(fs.readFileSync(fixtureYol, 'utf8'));
const senaryolar = JSON.parse(fs.readFileSync(senaryoYol, 'utf8'));
const hatalar = [];
process.on('uncaughtException', e => hatalar.push(String((e && e.stack) || e)));
process.on('unhandledRejection', e => hatalar.push(String((e && e.stack) || e)));

const el = () => ({ innerHTML: '', className: '', textContent: '', dataset: {}, focus() {}, appendChild() {}, remove() {}, classList: { toggle() {} } });
const ogeler = { ray: el(), bas: el(), ana: el(), bildirimler: el() };
const dinleyici = { document: {}, window: {} };
const depo = new Map();
let hash = '';

const konum = {
  get hash() { return hash; },
  set hash(v) {
    v = String(v).startsWith('#') ? String(v) : '#' + v;
    if (v !== hash) { hash = v; setTimeout(() => (dinleyici.window.hashchange || []).forEach(f => f()), 0); }
  },
  search: '',
};
const belge = {
  getElementById: id => ogeler[id] || null, querySelectorAll: () => [], querySelector: () => null, activeElement: null,
  documentElement: { dataset: {} }, title: '', body: { appendChild() {} }, createElement: () => el(),
  addEventListener: (t, f) => { (dinleyici.document[t] = dinleyici.document[t] || []).push(f); },
};

async function sahteFetch(url) {
  const u = new URL(url, 'http://x');
  const is = u.searchParams.get('is'), kart = u.searchParams.get('kart');
  const anahtar = u.pathname + (is ? '?is=' + is : kart ? '?kart=' + kart : '');
  if (fx[anahtar] === undefined) return { ok: false, status: 404, json: async () => ({ hata: 'fixture yok: ' + anahtar }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(fx[anahtar])) };
}

const kum = {
  document: belge, location: konum, console, navigator: {}, fetch: sahteFetch, AbortController, URLSearchParams,
  localStorage: { getItem: k => (depo.has(k) ? depo.get(k) : null), setItem: (k, v) => { depo.set(k, String(v)); } },
  history: { length: 1, back() {}, replaceState: (a, b, url) => { hash = String(url).replace(/^[^#]*/, ''); } },
  requestAnimationFrame: f => setTimeout(f, 0), setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
};
kum.window = { addEventListener: (t, f) => { (dinleyici.window[t] = dinleyici.window[t] || []).push(f); }, scrollTo() {} };

const bekle = ms => new Promise(r => setTimeout(r, ms));
async function tikla(eylem, veri) {
  const b = { dataset: { eylem, ...(veri || {}) }, disabled: false };
  const e = { target: { closest: s => (s === '[data-eylem]' ? b : null) } };
  for (const f of dinleyici.document.click || []) await f(e);
}
function tus(key) {
  const e = { key, target: { tagName: 'BODY' }, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, preventDefault() {} };
  for (const f of dinleyici.document.keydown || []) f(e);
}

(async () => {
  vm.createContext(kum);
  vm.runInContext(fs.readFileSync(uygulamaYol, 'utf8'), kum, { filename: 'app.js' });
  await bekle(80);
  const cikti = [];
  for (const s of senaryolar) {
    for (const [k, v] of Object.entries(s.depo || {})) { if (v === null) depo.delete(k); else depo.set(k, v); }
    if (s.hash !== undefined) { hash = s.hash; (dinleyici.window.hashchange || []).forEach(f => f()); }
    await bekle(60);
    for (const a of s.adimlar || []) {
      if (a[0] === 'tikla') await tikla(a[1], a[2]); else tus(a[1]);
      await bekle(40);
    }
    cikti.push({ ray: ogeler.ray.innerHTML, bas: ogeler.bas.innerHTML, ana: ogeler.ana.innerHTML, depo: Object.fromEntries(depo), hash });
  }
  fs.writeFileSync(ciktiYol, JSON.stringify({ sonuc: cikti, hatalar }));
  process.exit(0);
})().catch(e => { fs.writeFileSync(ciktiYol, JSON.stringify({ sonuc: [], hatalar: hatalar.concat(String((e && e.stack) || e)) })); process.exit(0); });
