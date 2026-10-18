'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { esc, B, E } = O;
  const { yerlestir } = O;
  const NOT_GORUNUR = 4;   // şu an kartında baştan açık gösterilen not sayısı
  const SEKMELER = [
    { k: 'planda_kart_yok', ad: 'Planda' },
    { k: 'yapildi', ad: 'Yapıldı' },
    { k: 'iptal', ad: 'İptal' },
  ];

  // İş türü süzgeçleri (tek tıkla). "yuruyen": şu an yürüyen adımı olan, kapanmamış iş.
  const yuruyor = i => i.durum !== 'kapandi' && dizi(i.kovalar && i.kovalar.simdi).length > 0;
  // Kapanmamış, beklemede olmayan işleri todo durumuna göre üçe böler (üçü birbirini dışlar):
  // Açık = todo'su kalan; Özet ve kapanış = todo'ları bitmiş, kapatılmayı bekleyen; Todo gerektirmeyen = hiç todo'su yok.
  const acikIs = i => i.durum !== 'kapandi' && i.durum !== 'beklemede';
  const todoToplam = i => Number(i.ilerleme && i.ilerleme.toplam) || 0;
  const todoKalan = i => todoToplam(i) - (Number(i.ilerleme && i.ilerleme.biten) || 0);
  const FILTRELER = [
    { k: 'acik', ad: 'Açık', f: i => acikIs(i) && todoToplam(i) > 0 && todoKalan(i) > 0 },
    { k: 'ozet', ad: 'Özet ve kapanış', f: i => acikIs(i) && todoToplam(i) > 0 && todoKalan(i) <= 0 },
    { k: 'gerektirmeyen', ad: 'Todo gerektirmeyen', f: i => acikIs(i) && todoToplam(i) === 0 },
    { k: 'yuruyen', ad: 'Yürüyen', f: yuruyor },
    { k: 'beklemede', ad: 'Beklemede', f: i => i.durum === 'beklemede' },
    { k: 'kapandi', ad: 'Tamamlanan', f: i => i.durum === 'kapandi' },
    { k: 'hepsi', ad: 'Hepsi', f: () => true },
  ];

  const S = {
    filtre: O.depo.al('orkestra.isler.filtre') || 'acik',
    veri: null,
    secili: new URL(location.href).searchParams.get('is') || O.depo.al('orkestra.isler.secili') || '',
    sekme: O.depo.al('orkestra.isler.sekme') || 'planda_kart_yok',
    kartSuz: O.depo.al('orkestra.isler.kartSuz') || 'hepsi',
    ara: '',
    acik: new Set(),   // açık <details> / genişletilmiş not kimlikleri (yeniden çizimde korunur)
  };
  let K = null;

  const dizi = v => Array.isArray(v) ? v : [];
  const reEsc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const MADDE_DURUM = { suruyor: { ad: 'Sürüyor', renk: 'var(--s1)' }, acik: { ad: 'Açık', renk: 'var(--neutral)' }, bitti: { ad: 'Bitti', renk: 'var(--good)' } };
  const rozet = d => `<span class="rozet" style="--renk:${esc(d.renk)}"><i></i>${esc(d.ad)}</span>`;
  const durumOf = o => o.tur === 'kart' ? E.durum(o.durum) : (MADDE_DURUM[o.durum] || MADDE_DURUM.suruyor);

  // Metin adım belirteciyle başlıyorsa baştaki tekrar atılır ("G0 Langfuse" + adım G0 → "Langfuse").
  function metinKirp(metin, adim) {
    const m = String(metin ?? '');
    if (!adim) return m;
    const kes = m.replace(new RegExp('^\\s*' + reEsc(adim) + '(?![\\w-])[\\s:.)\\-–—·]*', 'i'), '');
    return kes || m;
  }
  const adimOf = o => o.tur === 'kart' ? (o.adim || '') : (dizi(o.adimlar)[0] || '');
  const cipHtml = a => a ? `<span class="adim">${esc(a)}</span>` : '';
  const yuzdeOf = il => { const t = Number(il && il.toplam) || 0, b = Number(il && il.biten) || 0; return { t, b, y: t ? Math.max(0, Math.min(100, Math.round(b / t * 100))) : 0 }; };
  const barHtml = (il, buyuk) => {
    const { t, b, y } = yuzdeOf(il);
    return `<div class="bar${buyuk ? ' buyuk' : ''}"><span class="yol" role="progressbar" aria-label="İlerleme" aria-valuemin="0" aria-valuemax="${t}" aria-valuenow="${b}"><i style="width:${y}%"></i></span>` +
      `<span>${buyuk ? `%${y} · ${b}/${t} tamamlandı` : `${b} / ${t}`}</span></div>`;
  };
  // Arama vurgusu: metin önce kaçışlanır, sonra eşleşme <mark> ile sarılır.
  const vurgu = metin => {
    const e = esc(metin);
    if (!S.ara) return e;
    return e.replace(new RegExp(reEsc(esc(S.ara)), 'gi'), m => `<mark>${m}</mark>`);
  };
  const eslesir = o => !S.ara || [o.metin, o.kart, o.bolum, ...dizi(o.alt)].some(x => String(x ?? '').toLocaleLowerCase('tr').includes(S.ara.toLocaleLowerCase('tr')));

  // Son etkinliğe göre sıralı açık işler (en yeni üstte).
  const sirala = a => [...a].sort((x, y) => String(y.son || '').localeCompare(String(x.son || '')));

  // ---------------------------------------------------------------- sol liste
  function isSatiri(is) {
    const simdi = dizi(is.kovalar && is.kovalar.simdi);
    const ilk = simdi[0];
    const simdiMetin = ilk
      ? `<div class="is-simdi" title="${esc(metinKirp(ilk.metin, adimOf(ilk)))}"><span class="nokta" aria-hidden="true"></span>${esc(metinKirp(ilk.metin, adimOf(ilk)))}${simdi.length > 1 ? ` <span class="meta">+${simdi.length - 1}</span>` : ''}</div>`
      : `<div class="is-simdi bosta">${is.durum === 'kapandi' ? '✓ Tamamlandı' : is.durum === 'beklemede' ? 'Beklemede' : 'Şu an yürüyen adım yok'}</div>`;
    const secili = is.id === S.secili;
    const sh = isSohbetleri(is.id).filter(r => ETKIN.has(r.bekleyen));
    const shMetin = sh.length ? `<div class="is-sohbet" style="--renk:${bekleyenD(sh[0].bekleyen).renk}"><i></i>${sh.length} sohbet · ${esc(bekleyenD(sh[0].bekleyen).ad.toLocaleLowerCase('tr'))}</div>` : '';
    return `<li><button type="button" class="is-sec" data-is="${esc(is.id)}" data-anahtar="is:${esc(is.id)}" aria-current="${secili}">
      <span class="is-ust"><span class="is-id">${esc(is.id)}</span><span class="is-ad">${esc(is.ad || is.baslik || is.id)}</span><span class="is-zaman" title="Son etkinlik ${esc(B.tarih(is.son))}">${esc(B.once(is.son))}</span></span>
      ${barHtml(is.ilerleme)}${simdiMetin}${shMetin}</button></li>`;
  }

  function filtreHtml(tum) {
    return FILTRELER.map(f => {
      const n = tum.filter(f.f).length, sec = f.k === S.filtre;
      return `<button type="button" class="cip" data-filtre="${f.k}" data-anahtar="f:${f.k}" aria-pressed="${sec}">${esc(f.ad)}<span class="n">${n}</span></button>`;
    }).join('');
  }

  function listeHtml(gorunen, kartsiz) {
    const ad = (FILTRELER.find(f => f.k === S.filtre) || FILTRELER[0]).ad.toLocaleLowerCase('tr');
    let h = gorunen.length ? `<ul class="isler">${gorunen.map(isSatiri).join('')}</ul>` : `<p class="bos">${S.filtre === 'hepsi' ? 'Hiç iş yok.' : `“${esc(ad)}” türünde iş yok.`}</p>`;
    const ka = dizi(kartsiz && kartsiz.acik);
    if (ka.length) {
      const id = 'd:kartsiz';
      const sat = ka.map(k => `<li><span class="satir"><span class="adim">${esc(k.kart)}</span><span class="metin">${esc(k.baslik)}</span>${rozet(E.durum(k.durum))}</span></li>`).join('');
      h += `<details class="yan" data-d="${id}"${S.acik.has(id) ? ' open' : ''}><summary data-anahtar="${id}">İşe bağlı olmayan açık kartlar (${ka.length})</summary><ul class="satirlar">${sat}</ul></details>`;
    }
    return h;
  }

  // ---------------------------------------------------------------- sağ detay: başlık + odak
  function notlarHtml(alt, id) {
    if (!alt.length) return '';
    const hepsi = S.acik.has(id);
    const gor = hepsi ? alt : alt.slice(0, NOT_GORUNUR);
    const dugme = alt.length > NOT_GORUNUR
      ? `<button type="button" class="daha" data-genislet="${esc(id)}" data-anahtar="${esc(id)}">${hepsi ? 'Daha az göster' : `+${alt.length - NOT_GORUNUR} not daha`}</button>` : '';
    return `<ul class="notlar">${gor.map(a => `<li>${esc(a)}</li>`).join('')}</ul>${dugme}`;
  }

  function kartHtml(o, isId, i, kova) {
    const adim = adimOf(o);
    const d = durumOf(o);
    const alt = [];
    if (o.tur === 'kart') alt.push(esc(o.kart) + (o.basamak ? ' · ' + esc(o.basamak) : '') + (o.usd > 0 ? ' · ' + esc(B.deger(o.usd, o.token)) : ''));
    if (o.bolum) alt.push(esc(o.bolum));
    if (kova === 'sirada' && dizi(o.bekledigi).length) alt.push(`← ${esc(o.bekledigi.join(', '))} bekleniyor`);
    return `<div class="kart" style="--renk:${esc(kova === 'simdi' ? d.renk : 'var(--neutral)')}">
      <div class="kart-ust">${cipHtml(adim)}<span class="kart-metin">${esc(metinKirp(o.metin, adim))}</span>${rozet(d)}</div>
      ${alt.length ? `<div class="kart-alt">${alt.join(' · ')}</div>` : ''}
      ${notlarHtml(dizi(o.alt), `n:${isId}:${kova}:${o.kart || i}`)}</div>`;
  }

  function basHtml(is) {
    const k = is.kovalar || {};
    const simdi = dizi(k.simdi), sirada = dizi(k.sirada);
    const meta = [
      `<span>${esc(is.id)}</span>`,
      is.son ? `<span title="${esc(B.tarih(is.son))}">son etkinlik <b>${esc(B.once(is.son))}</b></span>` : '',
      `<span title="${esc(B.kalem(is.kalem))}">maliyet <b>${esc(B.deger(is.usd, is.token))}</b></span>`,
    ].filter(Boolean).join('');
    const odak = `<div class="odak">
      <div><h3>Şu an</h3>${simdi.length ? simdi.map((o, i) => kartHtml(o, is.id, i, 'simdi')).join('') : '<p class="bos-not">Şu an yürüyen bir adım yok.</p>'}</div>
      ${sirada.length ? `<div><h3>Sırada</h3>${sirada.map((o, i) => kartHtml(o, is.id, i, 'sirada')).join('')}</div>` : ''}
    </div>`;
    const sohbetler = isSohbetleri(is.id);
    const shHtml = `<div class="is-sohbetler"><h3>Sohbetler</h3>${sohbetler.length
      ? sohbetler.map(r => { const d = bekleyenD(r.bekleyen); return `<button type="button" class="bag sohbet-chip" style="--renk:${d.renk}" data-sohbet-ac="${esc(r.oturum)}" data-anahtar="h:${esc(r.oturum)}" title="Sohbeti Claude uygulamasında aç"><i></i>${esc(kisalt(r.sohbet, 46))}<span class="meta">${esc(d.ad)} · ${B.once(r.son_zaman)}</span></button>`; }).join('')
      : '<span class="meta">Bu işe bağlı sohbet yok.</span>'}</div>`;
    return `<header><h2>${esc(is.ad || is.baslik || is.id)}</h2><div class="detay-meta">${meta}</div>${barHtml(is.ilerleme, true)}${shHtml}</header>
      ${is.hata ? `<p class="is-hata">Bu iş okunamadı: ${esc(O.yolGizle(O.hataMetni(is.hata)))}</p>` : ''}${odak}`;
  }

  // ---------------------------------------------------------------- sağ detay: görev kartları tablosu
  // Seçili işin kart kayıtları (tur=kart) tüm kovalardan toplanır; süzgeç E.durum anahtarlarına göre.
  const KART_SUZGEC = [
    { k: 'hepsi', ad: 'Tümü', d: null },
    { k: 'calisan', ad: 'Çalışan', d: ['isleniyor'] },
    { k: 'denetimde', ad: 'Denetimde', d: ['denetimde'] },
    { k: 'bekleyen', ad: 'Bekleyen', d: ['planlandi', 'beklemede'] },
    { k: 'reddedilen', ad: 'Reddedilen', d: ['reddedildi'] },
    { k: 'teslim', ad: 'Teslim', d: ['onaylandi', 'teslim'] },
  ];
  const KART_SIRA = ['isleniyor', 'denetimde', 'reddedildi', 'planlandi', 'beklemede', 'onaylandi', 'teslim', 'iptal'];
  const kartlariTopla = is => Object.values(is.kovalar || {}).flatMap(dizi).filter(o => o.tur === 'kart')
    .sort((a, b) => (KART_SIRA.indexOf(a.durum) + 1 || 99) - (KART_SIRA.indexOf(b.durum) + 1 || 99));

  function kartTabloHtml(is) {
    const tum = kartlariTopla(is);
    if (!tum.length) return '';
    const suz = KART_SUZGEC.find(f => f.k === S.kartSuz) || KART_SUZGEC[0];
    const gor = suz.d ? tum.filter(o => suz.d.includes(o.durum)) : tum;
    const cipler = KART_SUZGEC.map(f => {
      const n = f.d ? tum.filter(o => f.d.includes(o.durum)).length : tum.length;
      return `<button type="button" class="cip" data-kart-suz="${f.k}" data-anahtar="ks:${f.k}" aria-pressed="${f.k === suz.k}">${esc(f.ad)}<span class="n">${n}</span></button>`;
    }).join('');
    const satirlar = gor.map(o => {
      const adim = adimOf(o);
      return `<tr><td class="kt-id"><span class="adim">${esc(o.kart)}</span></td>` +
        `<td class="kt-metin">${esc(metinKirp(o.metin, adim))}</td>` +
        `<td class="kt-bas">${esc(o.basamak || '')}</td>` +
        `<td class="kt-durum">${rozet(E.durum(o.durum))}</td>` +
        `<td class="kt-usd" title="${esc(B.kalem(o.kalem))}">${o.usd > 0 ? esc(B.deger(o.usd, o.token)) : ''}</td>` +
        `<td class="kt-teknik"><a href="/teknik?is=${encodeURIComponent(is.id)}" title="Bu işin teknik ayrıntısı (H7)">Teknik ayrıntı</a></td></tr>`;
    }).join('');
    const tablo = gor.length
      ? `<div class="kt-kap"><table><thead><tr><th>Kart</th><th>Görev</th><th>Basamak</th><th>Durum</th><th class="kt-usd">Maliyet</th><th class="kt-teknik">Teknik</th></tr></thead><tbody>${satirlar}</tbody></table></div>`
      : '<p class="bos">Bu süzgeçte kart yok.</p>';
    return `<h3>Görev kartları <span class="n">${tum.length}</span></h3><div class="cipler filtre" role="group" aria-label="Kart durumuna göre süz">${cipler}</div>${tablo}`;
  }

  // ---------------------------------------------------------------- sağ detay: sekmeler + liste
  function sekmeHtml(is) {
    const k = is.kovalar || {};
    const gor = SEKMELER.filter(s => s.k !== 'iptal' || dizi(k.iptal).length);
    if (!gor.some(s => s.k === S.sekme)) S.sekme = gor[0].k;
    return gor.map(s => {
      const n = dizi(k[s.k]).length, sec = s.k === S.sekme;
      return `<button type="button" role="tab" id="t-${s.k}" data-sekme="${s.k}" data-anahtar="t:${s.k}" aria-selected="${sec}" aria-controls="dListe" tabindex="${sec ? 0 : -1}">${esc(s.ad)}<span class="n">${n}</span></button>`;
    }).join('');
  }

  function satirHtml(o, kova, anahtar) {
    const adim = adimOf(o);
    const sag = o.tur === 'kart' ? [esc(o.kart), o.basamak ? esc(o.basamak) : ''].filter(Boolean).join(' · ') : '';
    const isaret = kova === 'yapildi' ? '<span class="isaret ok" aria-hidden="true">✓</span>' : kova === 'iptal' ? '<span class="isaret" aria-hidden="true">⊘</span>' : '<span class="isaret" aria-hidden="true">○</span>';
    const alt = dizi(o.alt);
    const govde = isr => `<span class="satir">${isr}${cipHtml(adim)}<span class="metin">${vurgu(metinKirp(o.metin, adim))}</span>${sag ? `<span class="sag">${sag}</span>` : ''}</span>`;
    if (alt.length) {
      const id = 'd:' + anahtar;
      const ac = S.acik.has(id) || (S.ara && alt.some(a => String(a).toLocaleLowerCase('tr').includes(S.ara.toLocaleLowerCase('tr'))));
      return `<li><details class="madde" data-d="${esc(id)}"${ac ? ' open' : ''}><summary data-anahtar="${esc(id)}">${govde('<span class="isaret" aria-hidden="true"></span>')}</summary>` +
        `<ul class="notlar">${alt.map(a => `<li>${vurgu(a)}</li>`).join('')}</ul></details></li>`;
    }
    return `<li>${govde(isaret)}</li>`;
  }

  // Bölüme göre gruplu liste; Yapıldı en yeni üstte.
  function kovaHtml(is) {
    const kova = S.sekme;
    let oge = dizi((is.kovalar || {})[kova]).map((o, i) => ({ o, i }));
    if (kova === 'yapildi') oge.reverse();
    oge = oge.filter(x => eslesir(x.o));
    if (!oge.length) return `<p class="bos">${S.ara ? `“${esc(S.ara)}” için sonuç yok.` : 'Burada madde yok.'}</p>`;
    const gruplar = new Map();
    for (const x of oge) {
      const b = x.o.bolum || (x.o.tur === 'kart' ? 'Kartlar' : 'Diğer');
      if (!gruplar.has(b)) gruplar.set(b, []);
      gruplar.get(b).push(x);
    }
    const tekGrup = gruplar.size === 1;
    return [...gruplar].map(([b, xs]) => `<div class="grup">${tekGrup ? '' : `<h4>${esc(b)}<span class="n">${xs.length}</span></h4>`}` +
      `<ul class="satirlar">${xs.map(x => satirHtml(x.o, kova, `${is.id}:${kova}:${x.o.kart || x.i}`)).join('')}</ul></div>`).join('');
  }

  // ---------------------------------------------------------------- sohbetler: ortak yardımcılar
  // Ekrana giden serbest metin: markdown soyulur, tam yollar kısaltılır, kaçışlanır.
  const metin = s => esc(O.yolGizle(O.temizMetin(s)));
  const kisalt = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s; };
  const zamanMs = s => { const t = Date.parse(s || ''); return isNaN(t) ? 0 : t; };
  const sat = (ad, deger) => `<div class="sat"><span>${esc(ad)}</span><span>${deger}</span></div>`;
  const sRozet = (d, ek = '') => `<span class="rozet${ek}" style="--renk:${d.renk}"><i></i>${esc(d.ad)}</span>`;
  // Sohbet durumu (iş durumundan ayrı): SS.simdi = /simdi.json'un SON İYİ verisi; KS = O.veri kontrol nesnesi.
  let KS = null;
  const SS = { simdi: null, filtre: O.depo.al('orkestra.simdi.filtre') || 'hepsi', eskilerAcik: false };
  const BEKLEYEN_SIRA = { sen: 0, claude: 1, notr: 2, bitti: 3, beklemede: 4, kapandi: 5 };
  const ETKIN = new Set(['sen', 'claude', 'notr', 'bitti']);
  // notr: tur sonuçsuz bitti, soru/karar/izin yok → 'Seni bekliyor' sayacına girmez, sakin gri rozet (G-095)
  const bekleyenD = k => k === 'notr' ? { ad: 'Yanıt hazır', renk: 'var(--neutral)' } : E.bekleyen(k);
  const oturumlar = () => (SS.simdi && Array.isArray(SS.simdi.oturumlar)) ? SS.simdi.oturumlar : [];
  function sohbetBayatCiz() { yerlestir($('#sohbetBayat'), O.bayatIsaret(KS)); }

  // ---------------------------------------------------------------- sohbetler (üst bölüm; simdi.html'den taşındı)
  // Sohbet ↔ iş bağı: sohbetin kartları hangi işe bağlıysa o iş (aynı çalışma alanındaysa tıklanabilir).
  const yolAnahtar = s => String(s || '').replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase();
  const alanYol = () => yolAnahtar(S.veri && S.veri.alan && S.veri.alan.yol);
  const buAlanda = r => !!alanYol() && yolAnahtar(r.proje_yol) === alanYol();
  const isSohbetleri = id => oturumlar().filter(r => buAlanda(r) && dizi(r.isler).some(x => x.id === id))
    .sort((a, b) => ((BEKLEYEN_SIRA[a.bekleyen] ?? 9) - (BEKLEYEN_SIRA[b.bekleyen] ?? 9)) || (zamanMs(b.son_zaman) - zamanMs(a.son_zaman)));

  function sohbetKarti(r) {
    const d = bekleyenD(r.bekleyen);
    const k = r.kartlar || { acik: 0, toplam: 0, teslim: 0, aktif: [] };
    const kartIp = k.aktif && k.aktif.length ? k.aktif.map(x => `<div class="meta">${esc(x.id)} · ${metin(x.baslik)}</div>`).join('') : '';
    // Sade kart: gövdede yalnız sohbetin amacı yazar (niyet kaydındaki hedef cümlesi = neden; yoksa ne; niyet yoksa yedek/son istek).
    // Sonuç, bekleme nedeni, son istek ve kart sayısı kartta çizilmez; ayrıntı üzerine gelince açılan ipucundadır.
    const govde = `<div class="amac">${metin(r.niyet_var ? (r.neden || r.ne) : (r.yedek || r.son_istek || 'Amaç henüz yazılmadı'))}</div>`;
    const acIpucu = r.link ? 'Tıkla: sohbeti Claude uygulamasında aç' : 'Tıkla: terminalde başlamış sohbeti uygulamada sürdür';
    const ip = `<b>${esc(r.proje)} › ${esc(r.sohbet)}</b>` + sat('Durum', esc(d.ad)) + sat('Son etkinlik', B.tarih(r.son_zaman)) +
      sat('Başlangıç', B.tarih(r.baslangic)) + sat('İstek', B.sayi(r.istek_sayisi)) + kartIp +
      (r.son_istek ? `<div class="meta">Son istek: ${metin(kisalt(r.son_istek, 220))}</div>` : '') + `<div class="meta">${acIpucu}</div>`;
    return `<div class="sohbet" style="--renk:${d.renk}" data-oturum="${esc(r.oturum)}" data-anahtar="s:${esc(r.oturum)}" tabindex="0" role="button"
        aria-label="${esc(r.proje + ' › ' + r.sohbet + ' · ' + d.ad + ' · sohbeti aç')}" data-ipucu="${esc(ip)}">
      <div class="ust">${sRozet(d, r.bekleyen === 'claude' ? ' nabiz' : '')}<span data-once="${esc(r.son_zaman || '')}">${B.once(r.son_zaman)}</span></div>
      ${govde}</div>`;
  }

  function sohbetCiz() {
    if (!SS.simdi && KS && KS.durum === 'hata') {      // tam hata satırı yalnız son iyi veri yokken
      $('#sohbetSayi').textContent = '';
      yerlestir($('#sohbetCip'), '');
      yerlestir($('#sohbetListe'), `<p class="bos">Sohbet verisi üretilemedi: ${metin(kisalt(KS.hata, 200))}</p>`);
      return;
    }
    const d = SS.simdi;
    if (!d) return;
    const tum = oturumlar().slice().sort((a, b) =>
      ((BEKLEYEN_SIRA[a.bekleyen] ?? 9) - (BEKLEYEN_SIRA[b.bekleyen] ?? 9)) || (zamanMs(b.son_zaman) - zamanMs(a.son_zaman)));
    const projeler = [...new Set(tum.map(r => r.proje))];
    const say = {};
    tum.forEach(r => { say[r.bekleyen] = (say[r.bekleyen] || 0) + 1; });
    const cipler = [['hepsi', `Hepsi · ${tum.length}`]]
      .concat(['sen', 'claude', 'notr', 'bitti', 'beklemede', 'kapandi'].filter(k => say[k]).map(k => [k, `${bekleyenD(k).ad} · ${say[k]}`]))
      .concat(projeler.length > 1 ? projeler.map(p => ['p:' + p, p]) : []);
    if (!cipler.some(([v]) => v === SS.filtre)) SS.filtre = 'hepsi';
    yerlestir($('#sohbetCip'), cipler.map(([v, ad]) =>
      `<button type="button" class="cip" data-sfiltre="${esc(v)}" data-anahtar="c:${esc(v)}" aria-pressed="${SS.filtre === v}">${esc(ad)}</button>`).join(''));
    $('#sohbetSayi').textContent = say.sen ? `${say.sen} seni bekliyor` : '';

    const f = SS.filtre;
    const liste = tum.filter(r => f === 'hepsi' || r.bekleyen === f || 'p:' + r.proje === f);
    let html;
    if (!tum.length) {
      html = '<p class="bos">Son günlerde sohbet kaydı yok.</p>';
    } else if (f === 'hepsi') {
      const etkin = liste.filter(r => ETKIN.has(r.bekleyen)), eski = liste.filter(r => !ETKIN.has(r.bekleyen));
      html = etkin.length ? `<div class="sohbet-liste">${etkin.map(sohbetKarti).join('')}</div>` : '<p class="bos">Şu an etkin sohbet yok.</p>';
      if (eski.length) {
        html += `<div class="eskiler"><button type="button" id="eskiDugme" data-anahtar="eski" aria-expanded="${SS.eskilerAcik}" aria-controls="eskiListe">${SS.eskilerAcik ? 'Eski sohbetleri gizle' : `Eski sohbetler · ${eski.length}`}</button></div>` +
          (SS.eskilerAcik ? `<div class="sohbet-liste eskiler" id="eskiListe">${eski.map(sohbetKarti).join('')}</div>` : '');
      }
    } else {
      html = liste.length ? `<div class="sohbet-liste">${liste.map(sohbetKarti).join('')}</div>` : '<p class="bos">Bu süzgeçte sohbet yok.</p>';
    }
    if (d.niyetsiz > 0) html += `<p class="meta alt-not">${d.niyetsiz} etkin sohbette niyet satırı yok; Claude bir sonraki istekte kendisi yazar.</p>`;
    yerlestir($('#sohbetListe'), html);
  }

  // ---------------------------------------------------------------- çizim
  const filtreOf = () => FILTRELER.find(f => f.k === S.filtre) || FILTRELER[0];
  // Seçili iş süzgeçte görünmüyorsa görünen ilk iş seçilir.
  function seciliIs(gorunen) {
    return gorunen.find(i => i.id === S.secili) || gorunen[0] || null;
  }

  // Durum şeridi: süren arka plan sohbetleri (yalnız varsa).
  function durumSeridiCiz() {
    const kap = $('#durumSeridi'); if (!kap) return;
    const v = S.veri;
    if (!v || v.acik === false || v.hata) { yerlestir(kap, ''); return; }
    const bp = dizi(v.arka_plan);
    let html = '';
    if (bp.length) {
      html += `<p class="persp-satir"><b>Arka plan görevleri · ${bp.length} sürüyor</b></p><ul>` +
        bp.map(x => `<li>Sohbet: ${esc(x.ad)}${x.baslangic ? ` <span class="meta">· ${esc(O.tarih ? O.tarih(x.baslangic) : x.baslangic)}</span>` : ''}</li>`).join('') + '</ul>';
    }
    yerlestir(kap, html);
  }

  function sayfaCiz() {
    durumSeridiCiz();
    const sayi = $('#iSayi');
    const bosDetay = metin => { yerlestir($('#dBas'), metin); $('#gecmis').classList.add('gizli'); $('#kartTablo').classList.add('gizli'); };
    if (!S.veri) {
      sayi.textContent = '';
      let metin = '<p class="bos">Yükleniyor…</p>';
      if (K && K.durum === 'hata') metin = `<p class="bos">İşler alınamadı: ${esc(O.yolGizle(K.hata))}</p>`;
      yerlestir($('#liste'), metin); bosDetay('');
      return;
    }
    const v = S.veri;
    if (v.acik === false || v.hata) {
      sayi.textContent = '';
      yerlestir($('#liste'), `<p class="bos">${v.hata ? 'Veri üretilemedi: ' + esc(O.hataMetni(v.hata)) : 'Bu çalışma alanında orkestra kapalı.'}</p>`);
      bosDetay('');
      return;
    }
    const tum = dizi(v.isler);
    const gorunen = sirala(tum.filter(filtreOf().f));
    sayi.textContent = String(tum.length);
    yerlestir($('#filtre'), filtreHtml(tum));
    const is = seciliIs(gorunen);
    if (is) S.secili = is.id;
    yerlestir($('#liste'), listeHtml(gorunen, v.kartsiz));
    if (!is) { bosDetay('<p class="bos">Bu süzgeçte iş yok; üstten başka bir tür seçin.</p>'); return; }
    yerlestir($('#dBas'), basHtml(is));
    $('#gecmis').classList.remove('gizli');
    yerlestir($('#sekmeler'), sekmeHtml(is));
    const kt = kartTabloHtml(is);
    $('#kartTablo').classList.toggle('gizli', !kt);
    yerlestir($('#kartTablo'), kt);
    const panel = $('#dListe');
    panel.setAttribute('aria-labelledby', 't-' + S.sekme);
    yerlestir(panel, kovaHtml(is));
  }

  function sec(id, odakla) {
    if (!id || id === S.secili) return;
    S.secili = id; S.ara = ''; $('#ara').value = '';
    O.depo.koy('orkestra.isler.secili', id);
    const u = new URL(location.href); u.searchParams.set('is', id); history.replaceState(null, '', u);
    sayfaCiz();
    if (odakla) { const b = document.querySelector(`button.is-sec[data-is="${CSS.escape(id)}"]`); if (b) b.focus(); }
    if (matchMedia('(max-width: 860px)').matches) $('#detay').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // Sohbet kartından işe: iş süzgeçte gizliyse "Hepsi"ye geçilir, detay görünür yere kaydırılır.
  function isaGit(id) {
    const g = S.veri && dizi(S.veri.isler).find(i => i.id === id);
    if (!g) return O.bildirim('Bu iş bu çalışma alanında yok');
    if (!filtreOf().f(g)) { S.filtre = 'hepsi'; O.depo.koy('orkestra.isler.filtre', S.filtre); }
    S.secili = ''; sec(id);
    $('.duzen').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function sekmeSec(k, odakla) {
    S.sekme = k; O.depo.koy('orkestra.isler.sekme', k); sayfaCiz();
    if (odakla) { const b = $('#t-' + k); if (b) b.focus(); }
  }

  // ---------------------------------------------------------------- sohbet olayları
  async function sohbetAc(oturum) {
    if (!oturum) return;
    O.ipucu.gizle();
    // Uygulama bağlantısı varsa tarayıcı açar (tıklama anında, await'ten önce): Windows yalnız öndeki sürecin
    // başlattığı uygulamayı öne getirir; sunucunun os.startfile'ı Claude'u arkada bırakıyordu.
    const r0 = oturumlar().find(x => x.oturum === oturum);
    const link = r0 && typeof r0.link === 'string' && /^claude:\/\/claude\.ai\/epitaxy\/[\w-]+$/.test(r0.link) ? r0.link : '';
    // Bu görünümde hangi yolun çalıştığı ilk tıklamada öğrenilir; sonraki tıklamalar beklemeden doğru yola gider.
    const yol = O.depo.al('orkestra.acYolu');
    if (link && yol === 'link') {
      location.href = link;
      return O.bildirim(`Açılıyor: ${r0.sohbet || 'sohbet'}`);
    }
    if (link && yol !== 'sunucu') {
      // Bağlantıyı işletim sistemine iletmeyen gömülü görünümlerde sayfa odağı kaybetmez → sunucu yoluna düş.
      let gitti = false;
      const kayip = () => { gitti = true; };
      window.addEventListener('blur', kayip, { once: true });
      document.addEventListener('visibilitychange', kayip, { once: true });
      location.href = link;
      O.bildirim(`Açılıyor: ${r0.sohbet || 'sohbet'}`);
      await new Promise(c => setTimeout(c, 1500));
      window.removeEventListener('blur', kayip);
      document.removeEventListener('visibilitychange', kayip);
      O.depo.koy('orkestra.acYolu', gitti ? 'link' : 'sunucu');
      if (gitti) return;
    }
    O.bildirim('Sohbet açılıyor…');
    try {
      const r = await fetch('/ac?oturum=' + encodeURIComponent(oturum), { method: 'POST', headers: { 'X-Orkestra': '1' } }).then(x => x.json());
      O.bildirim(r.tamam ? (r.yol === 'cli' ? 'Sohbet Claude uygulamasında sürdürülüyor' : `Açıldı: ${r.baslik || 'sohbet'}`) : 'Açılamadı: ' + O.yolGizle(O.hataMetni(r.hata || 'bilinmeyen hata')));
    } catch (e) { O.bildirim('Sunucuya ulaşılamadı'); }
  }
  function sohbetFiltreSec(v) {
    SS.filtre = v; O.depo.koy('orkestra.simdi.filtre', v === 'hepsi' ? '' : v);
    sohbetCiz();
  }
  // Sohbet bölümünün işleyicileri #sohbetler ile sınırlı: iş süzgeci ([data-filtre]) ile karışmaz.
  $('#sohbetler').addEventListener('click', e => {
    const f = e.target.closest('[data-sfiltre]');
    if (f) return sohbetFiltreSec(f.dataset.sfiltre);
    if (e.target.closest('#eskiDugme')) { SS.eskilerAcik = !SS.eskilerAcik; return sohbetCiz(); }
    const git = e.target.closest('[data-git-is]');
    if (git) return isaGit(git.dataset.gitIs);
    const el = e.target.closest('[data-oturum]');
    if (el) sohbetAc(el.dataset.oturum);
  });
  // role="button" öğeleri (div) için Enter ve Space; gerçek <button> bunu kendisi yapar.
  $('#sohbetler').addEventListener('keydown', e => {
    const el = e.target.closest('[data-oturum][role="button"]');
    if (el && el === e.target && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); sohbetAc(el.dataset.oturum); }
  });

  // ---------------------------------------------------------------- olaylar (iş bölümü)
  $('main').addEventListener('click', e => {
    if (e.target.closest('#sohbetler')) return;
    const so = e.target.closest('[data-sohbet-ac]');
    if (so) { sohbetAc(so.dataset.sohbetAc); return; }
    const fl = e.target.closest('[data-filtre]');
    if (fl) { S.filtre = fl.dataset.filtre; O.depo.koy('orkestra.isler.filtre', S.filtre); sayfaCiz(); return; }
    const isB = e.target.closest('button.is-sec');
    if (isB) { sec(isB.dataset.is); return; }
    const ks = e.target.closest('[data-kart-suz]');
    if (ks) { S.kartSuz = ks.dataset.kartSuz; O.depo.koy('orkestra.isler.kartSuz', S.kartSuz); sayfaCiz(); return; }
    const sk = e.target.closest('[data-sekme]');
    if (sk) { sekmeSec(sk.dataset.sekme); return; }
    const g = e.target.closest('[data-genislet]');
    if (g) { const id = g.dataset.genislet; if (S.acik.has(id)) S.acik.delete(id); else S.acik.add(id); sayfaCiz(); }
  });

  // Klavye: listede ↑/↓ işi değiştirir; sekmelerde ←/→ sekme değiştirir; "/" aramaya odaklar.
  $('main').addEventListener('keydown', e => {
    const isB = e.target.closest && e.target.closest('button.is-sec');
    if (isB && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      const tum = [...document.querySelectorAll('button.is-sec')];
      const j = tum.indexOf(isB) + (e.key === 'ArrowDown' ? 1 : -1);
      if (tum[j]) { e.preventDefault(); sec(tum[j].dataset.is, true); }
      return;
    }
    const sk = e.target.closest && e.target.closest('[role="tab"]');
    if (sk && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
      const tum = [...document.querySelectorAll('[role="tab"]')];
      const j = (tum.indexOf(sk) + (e.key === 'ArrowRight' ? 1 : tum.length - 1)) % tum.length;
      e.preventDefault(); sekmeSec(tum[j].dataset.sekme, true);
    }
  });
  document.addEventListener('keydown', e => {
    if (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && !$('#gecmis').classList.contains('gizli')) { e.preventDefault(); $('#ara').focus(); }
  });

  let araZaman = 0;
  $('#ara').addEventListener('input', e => { clearTimeout(araZaman); araZaman = setTimeout(() => { S.ara = e.target.value.trim(); sayfaCiz(); }, 120); });
  $('#ara').addEventListener('keydown', e => { if (e.key === 'Escape' && e.target.value) { e.target.value = ''; S.ara = ''; sayfaCiz(); } });

  // Açık/kapalı durumu kimlikle saklanır (toggle olayı kabarmaz; yakalama aşamasında dinlenir).
  $('main').addEventListener('toggle', e => {
    const id = e.target && e.target.dataset && e.target.dataset.d;
    if (!id) return;
    if (e.target.open) S.acik.add(id); else S.acik.delete(id);
    const kap = e.target.closest('#liste, #dListe'); if (kap) kap.__html = null;   // DOM kullanıcı eliyle değişti
  }, true);

  O.kabuk({ sayfa: 'isler' });
  // Sohbetler: kendi kaynağı (/simdi.json, tüm çalışma alanları); alan değişiminden etkilenmez.
  KS = O.veri(() => '/simdi.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'Sohbet verisi', aralik: 5000, tumDestek: true,
    gecerli: v => Array.isArray(v.oturumlar) && (!v.alan || !v.alan.id || v.alan.id === O.alan),
    cizici: v => { SS.simdi = v; sohbetCiz(); sohbetBayatCiz(); if (S.veri) sayfaCiz(); },
    durum: () => { sohbetBayatCiz(); if (!SS.simdi) sohbetCiz(); },
  });
  K = O.veri(() => '/isler.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'İşler', aralik: 5000,
    gecerli: v => v.acik === false || (Array.isArray(v.isler) && (!v.alan || !v.alan.id || v.alan.id === O.alan)),
    cizici: v => { S.veri = v; sayfaCiz(); bugunCiz(); },
    durum: () => { yerlestir($('#iBayat'), O.bayatIsaret(K)); if (!S.veri) sayfaCiz(); },
  });

  // Bugün şeridi: dağınık sayıları tek satırda toplar (sohbet, harcama, onay, açık iş); her karo ilgili sayfaya bağlanır.
  const BG = { analitik: null, onay: null };
  function bugunCiz() {
    const kap = $('#bugunKaro'); if (!kap) return;
    const sohbet = oturumlar().filter(buAlanda), sen = sohbet.filter(r => r.bekleyen === 'sen').length;
    const gun = BG.analitik && BG.analitik.trend ? dizi(BG.analitik.trend.gunluk) : [];
    const tk = O.B.olcu() === 'token', gd = x => Number(tk ? x.token : x.usd) || 0;   // USD/token düğmesi
    const bugun = gun.length ? gd(gun[gun.length - 1]) : null;
    const ib = O.B.isBasina(BG.analitik && BG.analitik.is_basina);
    const bekl = BG.onay && BG.onay.sayac ? Number(BG.onay.sayac.bekliyor) || 0 : null;
    const acik = S.veri && Array.isArray(S.veri.isler) ? S.veri.isler.filter(i => i.durum !== 'kapandi').length : null;
    const karolar = [
      G.karo({ etiket: 'Seni bekleyen sohbet', deger: String(sen), alt: sohbet.length + ' sohbet bu alanda', durum: sen ? 'uyari' : 'iyi', href: '#sohbetler' }),
      G.karo({ etiket: 'Bugünkü harcama', deger: bugun == null ? '–' : O.B.bicim()(bugun), alt: 'son 7 gün eğilimi', spark: { degerler: gun.slice(-7).map(gd), etiket: 'Son 7 günlük harcama' }, href: '/maliyet#g=ozet' }),
      G.karo({ etiket: 'Tamamlanan iş başına', deger: ib ? ib.deger : '–', alt: ib ? ib.alt : 'tamamlanan iş yok', href: '/maliyet#g=ozet' }),
      G.karo({ etiket: 'Onay bekleyen', deger: bekl == null ? '–' : String(bekl), alt: 'öneri ve karar', durum: bekl ? 'uyari' : 'iyi', href: '/onaylar' }),
      G.karo({ etiket: 'Açık iş', deger: acik == null ? '–' : String(acik), alt: 'kapanmamış işler', href: '#liste' }),
    ];
    yerlestir(kap, G.karolar(karolar));
  }
  O.veri(() => '/analitik.json?alan=' + encodeURIComponent(O.alan), { ad: 'Günlük harcama', aralik: 30000, gecerli: v => !!v.trend, cizici: v => { BG.analitik = v; bugunCiz(); } });
  O.veri(() => '/onaylar.json?alan=' + encodeURIComponent(O.alan), { ad: 'Onay ve todo sayımı', aralik: 15000, gecerli: v => !!v.sayac, cizici: v => { BG.onay = v; bugunCiz(); } });
  window.addEventListener('orkestra:alan', () => { SS.simdi = null; SS.eskilerAcik = false; sohbetCiz(); S.veri = null; S.secili = ''; S.ara = ''; $('#ara').value = ''; S.acik.clear(); sayfaCiz(); });
})();
