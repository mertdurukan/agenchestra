'use strict';
/* Kaynaklar sayfası (I-309 P6): makine geneli test kirası (/api/kaynaklar).
   Kim kirayı tutuyor (pid, komut, işçi, süre), bütçe kullanımı, bekleyenler ve bekleme süresi, seçili alanın kilit
   zaman aşımı sayıları (ozet.json dahil). Çizim saf işlevdir (kaynaklarHtml); node testleri module.exports ile çağırır. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function sure(sn) {
    if (sn == null || !isFinite(sn)) return '-';
    sn = Math.max(0, Math.round(sn));
    if (sn < 60) return sn + ' sn';
    if (sn < 3600) return Math.floor(sn / 60) + ' dk ' + (sn % 60) + ' sn';
    return Math.floor(sn / 3600) + ' sa ' + Math.floor((sn % 3600) / 60) + ' dk';
  }

  function satir(x, sureAlan) {
    const durum = x.canli === false ? ' <small>(yanıt vermiyor, sona erince düşer)</small>' : '';
    return `<tr><td>${esc(x.pid)}</td><td><code>${esc(x.komut || '')}</code>${durum}</td>` +
      `<td>${esc(x.isci ?? '-')}</td><td>${esc(sure(x[sureAlan]))}</td></tr>`;
  }

  function tablo(baslik, liste, sureBaslik, sureAlan, bosMetin) {
    const govde = liste.length ? liste.map(x => satir(x, sureAlan)).join('')
      : `<tr><td colspan="4" class="bos">${esc(bosMetin)}</td></tr>`;
    return `<section class="bolum"><h2>${esc(baslik)} <span class="meta">${liste.length}</span></h2>` +
      `<table><thead><tr><th>pid</th><th>Komut</th><th>İşçi</th><th>${esc(sureBaslik)}</th></tr></thead>` +
      `<tbody>${govde}</tbody></table></section>`;
  }

  function kilitHtml(k) {
    if (!k) return '<section class="bolum"><h2>Kilit zaman aşımları</h2><p class="aciklama">Kilit sayıları için tek bir çalışma alanı seçin.</p></section>';
    const ad = Object.keys(k.kaynaklar || {});
    const govde = ad.length ? ad.map(a => {
      const v = k.kaynaklar[a];
      return `<tr><td><code>${esc(a)}</code></td><td>${esc(v.kayit)}</td><td>${esc(v.son_gun || '-')}</td>` +
        `<td>${esc(v.ort_bekleme_ms == null ? '-' : v.ort_bekleme_ms + ' ms')}</td></tr>`;
    }).join('') : '<tr><td colspan="4" class="bos">Zaman aşımı günlüğü yok.</td></tr>';
    return `<section class="bolum"><h2>Kilit zaman aşımları <span class="meta">ozet.json: ${esc(k.ozet_json_zaman_asimi ?? 0)}</span></h2>` +
      `<table><thead><tr><th>Kaynak</th><th>Kayıt</th><th>Son gün</th><th>Ort. bekleme</th></tr></thead>` +
      `<tbody>${govde}</tbody></table></section>`;
  }

  function kaynaklarHtml(v) {
    if (!v || v.acik === false) return `<p class="bos">${esc((v && v.hata) || 'Kaynak verisi alınamadı.')}</p>`;
    const sah = v.sahipler || [], bek = v.bekleyenler || [];
    const ust = `<p class="aciklama">Test koşusu kirası · mod: <b>${esc(v.mod)}</b> · işçi: ${esc(v.kullanilan ?? 0)}` +
      ` / ${esc(v.butce ?? '-')} · ${sah.length} koşu sürüyor, ${bek.length} bekliyor. Tam takım: <code>scripts/test_paralel.py</code>.</p>`;
    return ust + tablo('Kirayı tutanlar', sah, 'Süre', 'sure_s', 'Şu an kiralı test koşusu yok.')
      + tablo('Bekleyenler', bek, 'Bekleme', 'bekleme_s', 'Kuyrukta bekleyen yok.') + kilitHtml(v.kilit);
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { kaynaklarHtml, sure };
  if (typeof window === 'undefined' || typeof document === 'undefined' || !window.O) return;

  const O = window.O;
  const yer = () => document.getElementById('kaynaklar') || document.querySelector('main');
  const yol = () => '/api/kaynaklar?alan=' + encodeURIComponent(O.alan || '');
  O.kabuk({ sayfa: 'kaynaklar' });
  O.veri(yol, { ad: 'kaynaklar', aralik: 3000, cizici: v => { const e = yer(); if (e) e.innerHTML = kaynaklarHtml(v); } });
})();
