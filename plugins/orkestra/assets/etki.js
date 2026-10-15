'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { esc } = O;
  const { yerlestir } = O;
  const NS = 'http://www.w3.org/2000/svg';

  // gidişat kimliği → [kullanıcı metni, renk]; bilinmeyen değer olduğu gibi görünür
  const GIDISAT = {
    'iyi': ['İyi', 'var(--good)'], 'kotu': ['Kötü', 'var(--critical)'], 'etkisiz': ['Etkisiz', 'var(--neutral)'],
    'yetersiz-veri': ['Yetersiz veri', 'var(--warning)'], 'olculemez': ['Ölçülemez', 'var(--neutral)'],
  };
  const KARAR = { 'dogru-karar': 'doğru karar', 'yanlis-karar': 'yanlış karar', 'belirsiz': 'belirsiz' };
  const IZLEME = { suruyor: 'sürüyor', kapandi: 'kapandı', 'geri-alindi': 'geri alındı', olculemez: 'ölçülemez' };

  const S = { veri: null, secili: null };
  let K = null;

  const rozet = g => {
    const [ad, renk] = GIDISAT[g] || [g == null ? '–' : String(g), 'var(--neutral)'];
    return `<span class="rozet" style="--renk:${renk}"><i></i>${esc(ad)}</span>`;
  };

  // değer biçimi metriğe göre: oranlar yüzde, maliyet dolar, kalan sayı
  const bicim = metrik => {
    const m = String(metrik || '');
    if (/oran|isabet/.test(m)) return v => O.B.yuzde(v, 1);
    if (/maliyet/.test(m)) return v => O.B.usd(v);
    return v => O.B.sayi(v, 2);
  };

  const gunSay = (a, b) => Math.round((Date.parse(a) - Date.parse(b)) / 86400000);

  // ------------------------------------------------------------ özet
  function ozetCiz(v) {
    const o = v.ozet || {};
    const sur = v.kayitlar.filter(k => k.izleme_durum === 'suruyor' && k.olculebilir);
    const say = g => sur.filter(k => k.gidisat === g).length;
    const soru = v.kayitlar.filter(k => k.soru_bekliyor).length;
    $('#eOzet').innerHTML = `
      <div class="karo vurgu" style="--renk:var(--s1)"><b>${o.dogru_karar_orani == null ? '–' : O.B.yuzde(o.dogru_karar_orani)}</b><span>Doğru karar oranı</span>
        <small>${o.kapali ? `yalnız kapatılmış ${O.B.sayi(o.kapali)} izlemeden · ${O.B.sayi(o.dogru)} doğru, ${O.B.sayi(o.yanlis)} yanlış` : 'henüz kapatılmış izleme yok'}</small></div>
      <div class="karo"><b>${O.B.sayi(sur.length)}</b><span>Süren izleme</span>
        <small>${O.B.sayi(say('iyi'))} iyi · ${O.B.sayi(say('kotu'))} kötü · ${O.B.sayi(say('etkisiz'))} etkisiz · ${O.B.sayi(say('yetersiz-veri'))} yetersiz veri</small></div>
      <div class="karo${soru ? ' vurgu' : ''}" style="--renk:var(--warning)"><b>${O.B.sayi(soru)}</b><span>Soru bekliyor</span>
        <small>geri al / sürdür kararı</small></div>`;
    $('#eSayi').textContent = O.B.sayi(v.kayitlar.length) + ' kayıt';
  }

  // ------------------------------------------------------------ liste
  function listeCiz(v) {
    const kap = $('#eListe');
    if (!v.kayitlar.length) { kap.innerHTML = '<p class="bos">Henüz uygulanmış ve izlenen karar yok.</p>'; return; }
    const satir = k => {
      const f = bicim(k.metrik);
      const tb = k.taban ? f(k.taban.deger) : '–';
      const bk = k.birikim ? f(k.birikim.deger) : '–';
      const durum = k.karar && k.karar.sonuc ? `kapandı · ${KARAR[k.karar.sonuc] || k.karar.sonuc}` : (IZLEME[k.izleme_durum] || k.izleme_durum || '–');
      return `<tr class="etki-satir${k.id === S.secili ? ' secili' : ''}${k.soru_bekliyor ? ' soru' : ''}" data-id="${esc(k.id)}">
        <td><button type="button" class="etki-ad" data-id="${esc(k.id)}" aria-pressed="${k.id === S.secili}">${esc(k.id)}</button>
          <span class="meta"> ${esc(O.temizMetin(k.baslik || ''))}</span>${k.soru_bekliyor ? '<span class="etki-soru">soru bekliyor: geri al / sürdür</span>' : ''}</td>
        <td>${esc(O.B.gun(k.uygulama_tarihi))}</td>
        <td class="sayi">${k.olculebilir ? O.B.sayi(k.gun) : '–'}</td>
        <td class="sayi">${k.olculebilir ? `${esc(tb)} → ${esc(bk)}` : '–'}</td>
        <td>${rozet(k.gidisat)}</td>
        <td class="sayi">${k.olculebilir && k.ayni_gidisat_gun ? O.B.sayi(k.ayni_gidisat_gun) + ' gündür' : '–'}</td>
        <td>${esc(durum)}</td></tr>`;
    };
    // Ölçülemez kayıtlar (ör. hafıza düzenlemesi) ana tabloyu doldurmasın: ayrı, kapalı bölümde
    const olculen = v.kayitlar.filter(k => k.olculebilir), olculemez = v.kayitlar.filter(k => !k.olculebilir);
    const tablo = liste => `<div class="tablo-kap"><table class="tablo"><thead><tr>
      <th>Karar</th><th>Uygulama</th><th class="sayi">Gün</th><th class="sayi">Taban → birikim</th><th>Gidişat</th><th class="sayi">Aynı gidişat</th><th>İzleme</th>
      </tr></thead><tbody>${liste.map(satir).join('')}</tbody></table></div>`;
    const acik = olculemez.some(k => k.id === S.secili) || !olculen.length;
    kap.innerHTML = (olculen.length ? tablo(olculen) : '<p class="bos">Ölçülebilir etkisi olan karar yok.</p>')
      + (olculemez.length ? `<details class="etki-olculemez"${acik ? ' open' : ''}><summary>Ölçülemeyen kararlar (${O.B.sayi(olculemez.length)})</summary>${tablo(olculemez)}</details>` : '');
  }

  // ------------------------------------------------------------ grafik
  const el = (ad, oz, ic) => {
    const e = document.createElementNS(NS, ad);
    Object.entries(oz || {}).forEach(([a, b]) => e.setAttribute(a, b));
    if (ic != null) e.textContent = ic;
    return e;
  };

  function grafikCiz(v) {
    const kutu = $('#eGrafikKutu');
    const k = v.kayitlar.find(x => x.id === S.secili);
    if (!k) { kutu.hidden = true; return; }
    kutu.hidden = false;
    const f = bicim(k.metrik);
    $('#eGrafikMeta').textContent = `${k.id} · uygulama ${O.B.gun(k.uygulama_tarihi)}`;
    const kap = $('#eGrafik');
    const not = $('#eGrafikNot');
    not.innerHTML = '';
    if (k.metin) not.innerHTML += `<p class="etki-not">Vaat: ${esc(O.temizMetin(k.metin))}${k.metrik ? ` <span class="meta">(${esc(k.metrik)}${k.yon ? ' · ' + esc(k.yon) : ''})</span>` : ''}</p>`;
    if (k.soru_bekliyor) not.innerHTML += `<p class="etki-not soru">${O.B.sayi(k.ayni_gidisat_gun)} gündür üst üste kötü gidiyor. Geri al ya da sürdür: <code>orkestra onay etki-kapat ${esc(k.id)} --sonuc dogru-karar|yanlis-karar|belirsiz</code></p>`;
    if (!k.olculebilir || !k.seri.length) {
      kap.innerHTML = `<p class="bos">${k.olculebilir ? 'Henüz günlük ölçüm yok.' : 'Bu kararın vaadi ölçülemez: grafik yok.'}</p>`;
      $('#eGosterge').innerHTML = '';
      return;
    }
    const seri = k.seri;
    const digerler = (k.diger_uygulamalar || []).map(d => ({ ...d, x: gunSay(d.tarih, k.uygulama_tarihi) }));
    // x ekseni uygulama gününden itibaren gün sayısı; önce uygulanmış diğer kayıtlar için eksen sola uzar
    const x0 = Math.min(0, ...digerler.map(d => d.x));
    const x1 = Math.max(seri.length - 1, ...digerler.map(d => d.x));
    const W = 760, H = 330, SOL = 56, SAG = 16, UST = 16, ALT_ORNEK = 56, ALT = ALT_ORNEK + 24;
    const gh = H - UST - ALT;
    const xs = x => SOL + (x - x0) / Math.max(1, x1 - x0) * (W - SOL - SAG);
    const degerler = [k.taban && k.taban.deger, ...seri.flatMap(s => [s.gunluk_deger, s.birikim_deger])].filter(d => d != null && isFinite(d));
    let lo = Math.min(...degerler), hi = Math.max(...degerler);
    if (!(hi > lo)) { const pay = Math.abs(hi) * 0.1 || 1; lo -= pay; hi += pay; }
    const pay = (hi - lo) * 0.08;
    lo -= pay; hi += pay;
    const ys = d => UST + (1 - (d - lo) / (hi - lo)) * gh;

    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'etki-grafik', role: 'img',
      'aria-label': `${k.id} gün gün gidişat: taban, günlük ve birikim değeri` });
    // yatay ızgara ve değer etiketleri
    for (let i = 0; i <= 4; i++) {
      const d = lo + (hi - lo) * i / 4, y = ys(d);
      svg.appendChild(el('line', { class: 'izgara', x1: SOL, x2: W - SAG, y1: y, y2: y }));
      svg.appendChild(el('text', { x: SOL - 6, y: y + 4, 'text-anchor': 'end' }, f(d)));
    }
    // altta örnek sayısı sütunları
    const enCok = Math.max(1, ...seri.map(s => s.gunluk_ornek || 0));
    const mins = (k.esik && k.esik.min_ornek) || 20;
    const yTaban = H - 24;
    const sw = Math.max(4, Math.min(34, (W - SOL - SAG) / Math.max(1, x1 - x0 + 1) * 0.6));
    svg.appendChild(el('text', { x: SOL - 6, y: yTaban - ALT_ORNEK + 10, 'text-anchor': 'end' }, 'örnek'));
    seri.forEach((s, i) => {
      const h = Math.max(1, (s.gunluk_ornek || 0) / enCok * (ALT_ORNEK - 14));
      svg.appendChild(el('rect', { class: 'sutun-ornek' + ((s.birikim_ornek || 0) >= mins ? ' yeterli' : ''),
        x: xs(i) - sw / 2, y: yTaban - h, width: sw, height: h }));
      svg.appendChild(el('text', { x: xs(i), y: yTaban - h - 3, 'text-anchor': 'middle' }, String(s.gunluk_ornek ?? 0)));
      svg.appendChild(el('text', { x: xs(i), y: H - 6, 'text-anchor': 'middle' }, O.B.gun(s.tarih)));
    });
    // aynı dönemde uygulanan başka kayıtların dikey işaretleri
    digerler.forEach(d => {
      const x = xs(d.x);
      const g = el('line', { class: 'isaret-diger', x1: x, x2: x, y1: UST, y2: yTaban - ALT_ORNEK });
      const t = el('title', {}, `${d.id} uygulandı · ${O.B.gun(d.tarih)}`);
      g.appendChild(t);
      svg.appendChild(g);
      svg.appendChild(el('text', { x: x + 3, y: UST + 10 + (digerler.indexOf(d) % 3) * 12 }, d.id));
    });
    // uygulama günü işareti (gün 1)
    const xu = xs(0);
    svg.appendChild(el('line', { class: 'isaret-uygulama', x1: xu, x2: xu, y1: UST, y2: yTaban - ALT_ORNEK }));
    svg.appendChild(el('text', { x: xu + 3, y: yTaban - ALT_ORNEK - 4 }, 'uygulama'));
    // dondurulmuş taban çizgisi
    if (k.taban && k.taban.deger != null) {
      const y = ys(k.taban.deger);
      svg.appendChild(el('polyline', { class: 'cizgi-taban', points: `${SOL},${y} ${W - SAG},${y}` }));
      svg.appendChild(el('text', { x: W - SAG, y: y - 5, 'text-anchor': 'end' }, `taban ${f(k.taban.deger)} (n=${k.taban.ornek ?? '–'})`));
    }
    // günlük ve birikim serileri (boş değerler çizgiyi böler)
    const parcalar = (alan, sinif, nokta) => {
      let yol = [];
      const bitir = () => { if (yol.length > 1) svg.appendChild(el('polyline', { class: sinif, points: yol.join(' ') })); yol = []; };
      seri.forEach((s, i) => {
        const d = s[alan];
        if (d == null) { bitir(); return; }
        yol.push(`${xs(i)},${ys(d)}`);
        svg.appendChild(el('circle', { class: nokta, cx: xs(i), cy: ys(d), r: 3 }));
      });
      bitir();
    };
    parcalar('gunluk_deger', 'cizgi-gunluk', 'nokta-gunluk');
    parcalar('birikim_deger', 'cizgi-birikim', 'nokta-birikim');
    // gün başına tıklanabilir/odaklanabilir alan: ipucu değerleri gösterir
    seri.forEach((s, i) => {
      const ip = `<b>Gün ${O.B.sayi(s.gun)} · ${esc(O.B.gun(s.tarih))}</b>`
        + `<div>Günlük: ${esc(f(s.gunluk_deger))} <span class="meta">(n=${O.B.sayi(s.gunluk_ornek)})</span></div>`
        + `<div>Birikim: ${esc(f(s.birikim_deger))} <span class="meta">(n=${O.B.sayi(s.birikim_ornek)})</span></div>`
        + `<div>Gidişat: ${esc((GIDISAT[s.gidisat] || [s.gidisat])[0])}</div>`
        + (s.karisik && s.karisik.length ? `<div class="meta">Karışık: ${s.karisik.map(esc).join(', ')}</div>` : '');
      svg.appendChild(el('rect', { class: 'vurgu-alan', x: xs(i) - Math.max(8, sw / 2), y: UST, width: Math.max(16, sw), height: H - UST - 4,
        tabindex: 0, 'data-ipucu': ip }));
    });
    kap.replaceChildren(svg);
    $('#eGosterge').innerHTML = `
      <span><i class="kesik" style="--renk:var(--text-muted)"></i>Taban (dondurulmuş)</span>
      <span><i style="--renk:var(--s1)"></i>Günlük değer</span>
      <span><i style="--renk:var(--s2)"></i>Birikim değeri</span>
      <span><i style="--renk:var(--text-primary)"></i>Uygulama günü</span>
      <span><i class="noktali" style="--renk:var(--s4)"></i>Aynı dönemde uygulanan başka kayıt</span>
      <span>Altta: günlük örnek sayısı (yeşil: birikim ${O.B.sayi(mins)} örneğe ulaştı)</span>`;
  }

  function sayfaCiz() {
    const v = S.veri;
    if (!v) return;
    if (!v.kayitlar.some(k => k.id === S.secili)) S.secili = v.kayitlar.length ? v.kayitlar[0].id : null;
    ozetCiz(v); listeCiz(v); grafikCiz(v);
  }

  function sec(id) {
    if (!id || id === S.secili) return;
    S.secili = id;
    sayfaCiz();
    const kutu = $('#eGrafikKutu');
    if (kutu && !kutu.hidden && kutu.scrollIntoView) kutu.scrollIntoView({ block: 'nearest' });
  }
  $('#eListe').addEventListener('click', e => {
    const tr = e.target.closest && e.target.closest('tr[data-id]');
    if (tr) sec(tr.dataset.id);
  });


  // ------------------------------------------------------------ veri
  if (!O.sayfa) O.kabuk({ sayfa: 'etki' });   // Onaylar sayfasında kabuğu onaylar.js kurar
  K = O.veri(() => '/api/etki?alan=' + encodeURIComponent(O.alan), {
    ad: 'Etki ölçümü', aralik: 5000,
    gecerli: v => Array.isArray(v.kayitlar) && v.ozet && (!v.alan || !v.alan.id || v.alan.id === O.alan),
    cizici: v => { S.veri = v; sayfaCiz(); },
    durum: () => { yerlestir($('#eBayat'), O.bayatIsaret(K)); },
  });
  window.addEventListener('orkestra:alan', () => { S.veri = null; S.secili = null; });
})();
