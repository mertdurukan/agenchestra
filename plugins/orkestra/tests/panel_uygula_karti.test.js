// node tests/panel_uygula_karti.test.js — "Şimdi uygula" kartı koşulu (app.js uygulaOgeleri) ve toast metni
const fs = require('fs'), path = require('path'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '..', 'assets', 'app.js'), 'utf8');
const m = src.match(/function uygulaOgeleri\(ozetler\) \{[\s\S]*?\n  \}\n/);
assert(m, 'uygulaOgeleri bulunamadı');
const uygulaOgeleri = new Function(m[0] + '; return uygulaOgeleri;')();
const sayac = n => ({ panelden_uygulanabilir: n });
const kosu = { idler: ['O-1', 'O-2'] };
let r = uygulaOgeleri([{ alan: null, sayac: sayac(3) }]);          assert.deepStrictEqual([r.length, r[0].kosu, r[0].n], [1, false, 3]);
r = uygulaOgeleri([{ alan: null, sayac: sayac(3), uygulama: kosu }]); assert.deepStrictEqual([r.length, r[0].kosu, r[0].n], [1, true, 3]);
r = uygulaOgeleri([{ alan: null, sayac: sayac(0), uygulama: kosu }]); assert.deepStrictEqual([r.length, r[0].kosu, r[0].n], [1, true, 2]);
r = uygulaOgeleri([{ alan: null, sayac: sayac(0) }]);              assert.strictEqual(r.length, 0);
assert(/perspektif: on\.perspektif, uygulama: on\.uygulama \}\]/.test(src), 'tek alan kipi on.uygulama taşımıyor');
assert(src.includes('Uygulama arka planda başladı'), 'pozitif toast metni yok');
assert(!/yeni sohbet açılıyor/.test(src.split('data-eylem="uygula"')[0] + src.slice(src.indexOf("ey === 'uygula'"), src.indexOf("ey === 'uygula'") + 400)), 'eski toast kaldı');
console.log('5 vaka + toast: geçti');
