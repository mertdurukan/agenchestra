'use strict';
// Orkestra paneli: ortak görsel bileşenler (G). Harici kaynak yok; SVG/CSS ile çizer, değerleri O.B ile biçimler.
// Her bileşen HTML metni döndürür (sayfa betiği innerHTML'e yazar). Renk tek başına anlam taşımaz: durum simge + metinle gelir.
(() => {
  const { esc } = O;
  const G = window.G = {};
  const sayi = v => (v == null || v === '' || isNaN(Number(v)) ? null : Number(v));
  const DURUM = { iyi: ['✓', 'Hedefte', 'var(--good)'], uyari: ['!', 'Dikkat', 'var(--warning)'], kotu: ['✕', 'Hedef dışı', 'var(--critical)'], yok: ['–', 'Veri yok', 'var(--neutral)'] };

  // Durum rozeti: simge + metin + renk
  G.durum = (d, metin) => { const t = DURUM[d] || DURUM.yok; return `<span class="g-durum" style="--renk:${t[2]}"><i aria-hidden="true">${t[0]}</i>${esc(metin || t[1])}</span>`; };

  // Mini çizgi: değerler soldan sağa; son nokta işaretlenir
  G.spark = (degerler, { w = 96, h = 28, renk = 'var(--s1)', etiket = '' } = {}) => {
    const v = (degerler || []).map(sayi).filter(x => x != null);
    if (v.length < 2) return '';
    const mn = Math.min(...v, 0), mx = Math.max(...v), ar = (mx - mn) || 1, ad = (w - 6) / (v.length - 1);
    const nok = v.map((x, i) => [3 + i * ad, h - 3 - ((x - mn) / ar) * (h - 6)]);
    const son = nok[nok.length - 1];
    return `<svg class="g-spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${esc(etiket || 'Eğilim')}">` +
      `<polyline points="${nok.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ')}" fill="none" stroke="${renk}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>` +
      `<circle cx="${son[0].toFixed(1)}" cy="${son[1].toFixed(1)}" r="3" fill="${renk}" stroke="var(--surface-1)" stroke-width="2"/></svg>`;
  };

  // Özet karosu: değer + etiket + alt metin + isteğe bağlı mini çizgi, durum ve bağlantı
  // veri: bağlantıya eklenen data-* öznitelikleri ({ 'sohbet-ac': oturum } → data-sohbet-ac="oturum"); sayfa kendi tıklama işleyicisiyle kullanır.
  G.karo = ({ deger, etiket, alt = '', durum = '', spark = null, href = '', ipucu = '', vurgu = '', veri = null }) => {
    const ic = `<span class="g-karo-e">${esc(etiket)}</span><b class="g-karo-d">${esc(deger)}</b>` +
      `<span class="g-karo-a">${alt ? esc(alt) : ''}${durum ? ' ' + G.durum(durum) : ''}</span>` +
      (spark ? `<span class="g-karo-s">${G.spark(spark.degerler, spark)}</span>` : '');
    const oz = (ipucu ? ` data-ipucu="${esc(ipucu)}" tabindex="0"` : '') +
      (veri ? Object.keys(veri).map(k => ` data-${k.replace(/[^\w-]/g, '')}="${esc(veri[k])}"`).join('') : '');
    return href ? `<a class="g-karo ${vurgu}" href="${esc(href)}"${oz}>${ic}</a>` : `<div class="g-karo ${vurgu}"${oz}>${ic}</div>`;
  };
  G.karolar = liste => `<div class="g-karolar">${liste.join('')}</div>`;

  // Hedef göstergesi (bullet): değer çubuğu, hedef çizgisi, isteğe bağlı kabul bandı
  G.hedef = ({ deger, hedef, maks, bicim = x => String(x), durum = 'yok', etiket = '', bant = null }) => {
    const d = sayi(deger), h = sayi(hedef);
    const ust = maks != null ? maks : (Math.max(d || 0, h || 0, bant ? bant[1] : 0) * 1.25 || 1);
    const yz = x => Math.max(0, Math.min(100, (x / ust) * 100));
    const renk = (DURUM[durum] || DURUM.yok)[2];
    return `<div class="g-hedef" role="img" aria-label="${esc(etiket)} ${d == null ? 'veri yok' : bicim(d)}${h != null ? ', hedef ' + bicim(h) : ''}">` +
      `<div class="g-hedef-yol">${bant ? `<span class="g-hedef-bant" style="left:${yz(bant[0])}%;width:${yz(bant[1]) - yz(bant[0])}%"></span>` : ''}` +
      (d != null ? `<span class="g-hedef-dolgu" style="width:${yz(d)}%;background:${renk}"></span>` : '') +
      (h != null ? `<span class="g-hedef-cizgi" style="left:${yz(h)}%"></span>` : '') + `</div></div>`;
  };

  // Pay çubuğu: tek yatay yığılmış çubuk + altında etiketli değer listesi (100% pay)
  G.pay = (ogeler, { bicim = x => String(x), toplamEtiket = '' } = {}) => {
    const l = (ogeler || []).filter(o => sayi(o.deger) > 0);
    const top = l.reduce((a, o) => a + Number(o.deger), 0);
    if (!top) return '<p class="bos">Bu dönemde kayıt yok.</p>';
    const ip = o => esc('<b>' + esc(o.ad) + '</b><div>' + esc(bicim(o.deger)) + ' · ' + O.B.yuzde(Number(o.deger) / top, 1) + '</div>');
    return `<div class="g-pay"><div class="g-pay-cubuk" role="img" aria-label="${esc(toplamEtiket || 'Pay dağılımı')}">` +
      l.map(o => `<span style="flex:${Number(o.deger)};background:${o.renk || 'var(--s1)'}" data-ipucu="${ip(o)}" tabindex="0"></span>`).join('') +
      `</div><ul class="g-pay-liste">` +
      l.map(o => `<li><i style="background:${o.renk || 'var(--s1)'}"></i><span class="g-pay-ad">${esc(o.ad)}</span><span class="g-pay-pay">${O.B.yuzde(Number(o.deger) / top, 0)}</span><span class="g-pay-deger">${esc(bicim(o.deger))}</span></li>`).join('') +
      `</ul></div>`;
  };

  // Isı haritası: satır × sütun matris; hücre koyuluğu değerle orantılı, değer her zaman yazılıdır
  G.isi = ({ satirlar, sutunlar, deger, bicim = x => String(x), satirBasi = '', renk = 'var(--s1)' }) => {
    const m = satirlar.map(s => sutunlar.map(c => sayi(deger(s, c))));
    const mx = Math.max(0, ...m.flat().filter(x => x != null));
    if (!mx) return '<p class="bos">Bu dönemde kayıt yok.</p>';
    return `<div class="tablo-kap" tabindex="0"><table class="tablo g-isi"><thead><tr><th>${esc(satirBasi)}</th>${sutunlar.map(c => `<th class="sayi">${esc(c.ad || c)}</th>`).join('')}<th class="sayi">Toplam</th></tr></thead><tbody>` +
      satirlar.map((s, i) => `<tr><th scope="row">${esc(s.ad || s)}</th>${m[i].map(x => (x == null || x === 0) ? '<td class="sayi g-isi-bos">–</td>' :
        `<td class="sayi" style="background:color-mix(in srgb, ${renk} ${Math.round(8 + 62 * x / mx)}%, transparent)">${esc(bicim(x))}</td>`).join('')}<td class="sayi g-isi-top">${esc(bicim(m[i].reduce((a, x) => a + (x || 0), 0)))}</td></tr>`).join('') +
      `</tbody></table></div>`;
  };

  // İnce ilerleme çubuğu: yapıldı / toplam
  G.ilerleme = (yapildi, toplam, { renk = 'var(--good)', etiket = '' } = {}) => {
    const t = Number(toplam) || 0, y = Math.min(Number(yapildi) || 0, t);
    const yz = t ? y / t * 100 : 0;
    return `<span class="g-ilerleme" role="img" aria-label="${esc(etiket)} ${y} / ${t}"><span style="width:${yz.toFixed(1)}%;background:${renk}"></span></span>`;
  };

  // Dağılım şeridi: medyan, P90 ve en çok değeri tek eksende; üç sayı da yazılıdır
  G.dagilim = ({ medyan, p90, maks, bicim = x => String(x), etiket = '' }) => {
    const m = sayi(medyan), p = sayi(p90), x = sayi(maks);
    const ust = Math.max(m || 0, p || 0, x || 0) || 1;
    const yz = v => (v / ust * 100).toFixed(1);
    const b = v => (v == null ? '–' : esc(bicim(v)));
    return `<div class="g-dag" role="img" aria-label="${esc(etiket)}: medyan ${m == null ? '–' : bicim(m)}, P90 ${p == null ? '–' : bicim(p)}, en çok ${x == null ? '–' : bicim(x)}">` +
      `<div class="g-dag-yol">${p != null ? `<span class="g-dag-p90" style="width:${yz(p)}%"></span>` : ''}${m != null ? `<span class="g-dag-med" style="left:${yz(m)}%"></span>` : ''}${x != null ? `<span class="g-dag-maks" style="left:${yz(x)}%"></span>` : ''}</div>` +
      `<div class="g-dag-sayi"><span>medyan <b>${b(m)}</b></span><span>P90 <b>${b(p)}</b></span><span>en çok <b>${b(x)}</b></span></div></div>`;
  };

  // Hedef kartı (I-047): aynı soruya cevap veren ölçüler tek kartta toplanır. Kabuk sayfa HTML'inde durur
  // (.g-hk[data-hedef]); soru başlığı yazılır, ayrıntıya taşınacak mevcut bölümler kimlikleriyle birlikte
  // taşınır (betikler yazmaya devam eder), ayrıntı açılınca boyuta bağlı çizimler için resize yayılır.
  G.hedefKarti = ({ hedef, soru, tasi = [] }) => {
    const k = document.querySelector(`.g-hk[data-hedef="${hedef}"]`);
    if (!k) return null;
    const s = k.querySelector('.g-hk-soru'); if (s) s.textContent = soru;
    const ayr = k.querySelector('.g-hk-ayr'), govde = k.querySelector('.g-hk-govde');
    tasi.forEach(sec => { const e = document.querySelector(sec); if (e && govde && !govde.contains(e)) govde.appendChild(e); });
    if (ayr) {
      ayr.hidden = !(govde && govde.children.length);
      if (!ayr.__hk) { ayr.__hk = true; ayr.addEventListener('toggle', () => window.dispatchEvent(new Event('resize'))); }
    }
    return { kart: k, ust: k.querySelector('.g-hk-ust'), ek: k.querySelector('.g-hk-ek') };
  };

  // Kart dışı çözümler (I-047): kabuk yerine tek kaynak ya da bağlantı ile tekilleştirilen hedefler.
  // cozum: 'tek-kaynak' = veri tek bölümde, diğer yerden kaldırıldı; 'baglanti' = iki sayfa birbirine bağlı, veri iki yerde farklı alanlarla duruyor.
  G.HEDEF_COZUM = [
    { hedef: 'H5', cozum: 'tek-kaynak', yer: '#kota', not: 'Kota karoları yalnız Kota bölümünde; Harcama bölümünden kaldırıldı (aynı değer ve daha çok ayrıntı)' },
    { hedef: 'H11', cozum: 'tek-serit', yer: '#canli', not: 'Sayfa başına tek tazelik şeridi kabuktaki canlı göstergedir (O.canli); bölüm içi …Bayat işareti yalnız yenilenemeyince görünür (O.bayatIsaret bayat değilse boş döner)' },
    { hedef: 'H12', cozum: 'tek-kaynak', yer: 'G.pencere', not: 'Hedef panosu ve Sohbetler dönemi aynı G.pencere seçimini kullanır (maliyet.js PENCERE_DONEM)' },
    { hedef: 'H7', cozum: 'baglanti', yer: '/teknik', not: 'Dashboard kart tablosu her satırda işin Teknik ayrıntı sayfasına bağlanır (?is=); kart listesi tek yerde okunur' },
    { hedef: 'H8', cozum: 'tek-kaynak', yer: '/isler', not: 'Sohbetin canlı durumu (çalışıyor, seni bekliyor) yalnız Dashboard Sohbetler bölümünde; Son olaylar yalnız olay akışıdır' },
    { hedef: 'H10', cozum: 'baglanti', yer: '/onaylar', not: 'Sağlık karosu ile Onaylar şeridi farklı alanlar taşır; birbirine bağlandı' },
  ];

  // Sayfa içi görünümler: .g-gorunum[data-g] bölümlerinden yalnız seçileni gösterir; seçim URL karmasında (#g=ad) tutulur.
  // Kimlikli bölümler yerinde kalır; betikler gizli bölüme de yazar. Boyuta bağlı çizimler için görünüm açılınca
  // 'orkestra:gorunum' ve resize olayı yayılır.
  G.sekmeler = (nav, liste, { varsayilan = null } = {}) => {
    const kap = typeof nav === 'string' ? document.querySelector(nav) : nav;
    if (!kap) return null;
    const ids = liste.map(x => x[0]);
    const karma = () => { const m = /(?:^|[#&])g=([\w-]+)/.exec(location.hash); return m && ids.includes(m[1]) ? m[1] : null; };
    let secili = karma() || varsayilan || ids[0];
    kap.classList.add('g-sekmeler'); kap.setAttribute('role', 'tablist');
    kap.innerHTML = liste.map(([id, ad]) => `<button type="button" role="tab" id="gs-${id}" data-g="${id}" aria-selected="false"><span class="g-sekme-ad">${esc(ad)}</span><span class="g-sekme-rozet" data-rozet="${id}" hidden></span></button>`).join('');
    const goster = (id, yaz) => {
      secili = id;
      kap.querySelectorAll('[role=tab]').forEach(b => { const a = b.dataset.g === id; b.setAttribute('aria-selected', a); b.tabIndex = a ? 0 : -1; });
      document.querySelectorAll('.g-gorunum').forEach(e => { e.hidden = e.dataset.g !== id; });
      if (yaz) history.replaceState(null, '', location.pathname + location.search + '#g=' + id);
      requestAnimationFrame(() => { window.dispatchEvent(new CustomEvent('orkestra:gorunum', { detail: { id } })); window.dispatchEvent(new Event('resize')); });
    };
    kap.addEventListener('click', e => { const b = e.target.closest('[role=tab]'); if (b) goster(b.dataset.g, true); });
    kap.addEventListener('keydown', e => {
      const i = ids.indexOf(secili);
      const yeni = e.key === 'ArrowRight' ? ids[(i + 1) % ids.length] : e.key === 'ArrowLeft' ? ids[(i - 1 + ids.length) % ids.length] : null;
      if (!yeni) return;
      e.preventDefault(); goster(yeni, true); kap.querySelector('#gs-' + yeni).focus();
    });
    window.addEventListener('hashchange', () => { const k = karma(); if (k && k !== secili) goster(k, false); });
    goster(secili, false);
    return { git: id => goster(id, true), aktif: () => secili };
  };
  // Sekme başlığına sayı/uyarı rozeti: metin boşsa gizlenir; renk durum belirtecidir
  G.rozet = (id, metin, renk) => {
    const e = document.querySelector(`[data-rozet="${id}"]`);
    if (!e) return;
    e.hidden = !metin; e.textContent = metin || ''; if (renk) e.style.setProperty('--renk', renk);
  };
  // Pencere seçici (segmented radiogroup): tek seçim, ok tuşları ve 1-N kısayolu, seçim alan başına saklanır.
  // Sayfadaki bütün pencereli bölümler 'orkestra:pencere' olayını dinler; kaynak tek yerde durur (G.pencere.al()).
  const PENCERELER = [['bugun', 'Bugün', 'Bugün'], ['son_3_gun', '3 gün', 'Son 3 gün'], ['son_7_gun', '7 gün', 'Son 7 gün'], ['bu_ay', 'Ay', 'Bu ay'], ['tum_zaman', 'Tümü', 'Tüm zaman']];
  const PENCERE_ANAHTAR = () => 'orkestra.pencere.' + O.alan;
  G.pencere = (nav, { varsayilan = 'son_3_gun', aralik = null } = {}) => {
    const kap = typeof nav === 'string' ? document.querySelector(nav) : nav;
    if (!kap) return null;
    const idler = PENCERELER.map(p => p[0]);
    let secili = (() => { const v = O.depo.al(PENCERE_ANAHTAR()); return idler.includes(v) ? v : varsayilan; })();
    kap.classList.add('g-pencere'); kap.setAttribute('role', 'radiogroup'); kap.setAttribute('aria-label', 'Zaman penceresi');
    kap.innerHTML = PENCERELER.map(([id, kisa, uzun], i) => `<button type="button" role="radio" data-p="${id}" aria-checked="false" title="${esc(uzun)} (${i + 1})">${esc(kisa)}</button>`).join('') +
      '<span class="g-pencere-aralik" aria-live="polite"></span>';
    const pencereCiz = () => {
      kap.querySelectorAll('[role=radio]').forEach(b => { const a = b.dataset.p === secili; b.setAttribute('aria-checked', a); b.tabIndex = a ? 0 : -1; });
      const ar = kap.querySelector('.g-pencere-aralik');
      if (ar) ar.textContent = aralik ? (aralik(secili) || '') : '';
    };
    const sec = (id, yay = true) => {
      if (!idler.includes(id) || id === secili && yay) return;
      secili = id; try { O.depo.koy(PENCERE_ANAHTAR(), id); } catch (_) {}
      pencereCiz();
      if (yay) window.dispatchEvent(new CustomEvent('orkestra:pencere', { detail: { id } }));
    };
    kap.addEventListener('click', e => { const b = e.target.closest('[role=radio]'); if (b) sec(b.dataset.p); });
    kap.addEventListener('keydown', e => {
      const i = idler.indexOf(secili);
      const y = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? idler[(i + 1) % idler.length] : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? idler[(i - 1 + idler.length) % idler.length] : e.key === 'Home' ? idler[0] : e.key === 'End' ? idler[idler.length - 1] : null;
      if (!y) return;
      e.preventDefault(); sec(y); kap.querySelector(`[data-p="${y}"]`).focus();
    });
    // 1-5 kısayolu: yazı alanında ve değiştirici tuşla çalışmaz
    document.addEventListener('keydown', e => {
      if (e.ctrlKey || e.metaKey || e.altKey || kap.hidden || kap.offsetParent === null) return;
      if (e.target.closest && e.target.closest('input, textarea, select, [contenteditable]')) return;
      const n = Number(e.key); if (n >= 1 && n <= idler.length) sec(idler[n - 1]);
    });
    pencereCiz();
    G.pencere.al = () => secili;
    G.pencere.ad = id => (PENCERELER.find(p => p[0] === id) || [])[2] || id;
    G.pencere.yenile = pencereCiz;
    return { al: () => secili, sec, yenile: pencereCiz };
  };
  G.pencere.al = () => { const v = O.depo.al(PENCERE_ANAHTAR()); return PENCERELER.some(p => p[0] === v) ? v : 'son_3_gun'; };
  G.pencere.ad = id => (PENCERELER.find(p => p[0] === id) || [])[2] || id;
})();
