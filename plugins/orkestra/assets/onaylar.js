'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { esc } = O;
  const { yerlestir } = O;

  const TURLER = [['hepsi', 'Tümü'], ['perspektif', 'Perspektif'], ['skill', 'Skill'], ['kural', 'Kural'], ['karar', 'Karar']];
  const TUR_AD = { perspektif: 'Perspektif', skill: 'Skill', kural: 'Kural', karar: 'Karar' };
  const TUR_RENK = { perspektif: 'var(--s7)', skill: 'var(--s3)', kural: 'var(--s4)', karar: 'var(--s1)' };
  const GORUNUMLER = [
    ['bekleyen', 'Bekleyen', ['bekliyor']],
    ['uygulanacak', 'Uygulanacak', ['onaylandi', 'uygulaniyor']],
    ['gecmis', 'Geçmiş', ['uygulandi', 'reddedildi', 'eskidi', 'iptal']],
  ];
  const BOS_METIN = { bekleyen: 'Bekleyen onay yok.', uygulanacak: 'Uygulanmayı bekleyen karar yok.', gecmis: 'Geçmişte kayıt yok.' };
  const DURUM_RENK = { bekliyor: 'var(--warning)', onaylandi: 'var(--focus)', uygulaniyor: 'var(--focus)', uygulandi: 'var(--good)' };

  // Durum: veri sunucudan gelir; taslak (seçim, not), katlama, hata ve yoldaki istekler yeniden çizimde korunur.
  const S = { veri: null, tur: 'hepsi', gorunum: 'bekleyen', acik: new Set(), taslak: {}, hata: {}, yolda: new Set() };
  let K = null;

  const kayitlar = () => (S.veri && Array.isArray(S.veri.kayitlar)) ? S.veri.kayitlar : [];
  const gorunumDurumlari = g => (GORUNUMLER.find(x => x[0] === g) || GORUNUMLER[0])[2];
  const gorunumde = (k, g) => gorunumDurumlari(g).includes(k.durum);
  const tabanAd = s => String(s ?? '').split(/[\\/]/).filter(Boolean).pop() || '';

  // Kaçışlı satır içi biçim: önce HTML kaçışı, sonra yalnız `kod` ve **kalın** işaretleri etikete çevrilir.
  const satirIci = s => esc(s).replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
  const diffBlok = kod => '<pre class="diff">' + String(kod).replace(/\n$/, '').split('\n').map(l => {
    const sinif = /^\+(?!\+\+)/.test(l) ? 'ek' : /^-(?!--)/.test(l) ? 'cik' : 'sat';
    return `<span class="${sinif}">${esc(l) || ' '}</span>`;
  }).join('') + '</pre>';
  // Güvenli markdown: ``` çitleri <pre> olur (diff renklenir), kalan metin kaçışlı paragraflardır.
  function metinHtml(m) {
    const paragraflar = t => t.split(/\n{2,}/).map(p => p.trim()).filter(Boolean)
      .map(p => '<p>' + p.split('\n').map(l => (/^#{1,6}\s/.test(l) ? '<b>' + satirIci(l.replace(/^#{1,6}\s+/, '')) + '</b>' : satirIci(l))).join('\n') + '</p>').join('');
    const kodHtml = (dil, satirlar) => (dil === 'diff' || dil === 'patch' ? diffBlok(satirlar.join('\n')) : '<pre>' + esc(satirlar.join('\n')) + '</pre>');
    let html = '', duz = [], kod = null, dil = '';
    const duzBosalt = () => { html += paragraflar(duz.join('\n')); duz = []; };
    for (const satir of String(m ?? '').replace(/\r\n?/g, '\n').split('\n')) {
      const cit = satir.match(/^```[ \t]*([\w-]*)[ \t]*$/);
      if (kod === null) {
        if (cit) { duzBosalt(); kod = []; dil = cit[1].toLowerCase(); } else duz.push(satir);
      } else if (cit && !cit[1]) {
        html += kodHtml(dil, kod);
        kod = null;
      } else kod.push(satir);
    }
    if (kod !== null) html += kodHtml(dil, kod);   // kapanmamış çit
    duzBosalt();
    return html || '<p class="meta">(metin yok)</p>';
  }

  function durumHtml(k) {
    const kr = k.karar || {}, u = k.uygulama || {};
    const notu = kr.not ? ` <span class="meta">Not: ${esc(kr.not)}</span>` : '';
    const secim = kr.secim ? ` · seçim: <b>${esc(kr.secim)}</b>` : '';
    switch (k.durum) {
      case 'onaylandi': return `Onaylandı${secim}. Claude'un uygulaması bekleniyor — sohbette <code>/orkestra:onay</code>.${notu}`;
      case 'uygulaniyor': return `Uygulanıyor — oturum <code>${esc(String(u.oturum || '?').slice(0, 8))}</code> aldı${u.alma_zamani ? ' · ' + esc(O.B.tarih(u.alma_zamani)) : ''}.${notu}`;
      case 'uygulandi': return `Uygulandı${u.ozet ? ': ' + esc(u.ozet) : '.'}${secim}${notu}`;
      case 'reddedildi': return `Reddedildi.${notu}`;
      case 'eskidi': return 'Eskidi: daha yeni bir rapor geldi.';
      case 'iptal': return `İptal edildi.${notu}`;
      default: return esc(k.durum);
    }
  }

  function eylemHtml(k) {
    const t = S.taslak[k.id] || {};
    const yolda = S.yolda.has(k.id), kilit = yolda ? ' disabled' : '';
    const secenekler = Array.isArray(k.secenekler) ? k.secenekler : [];
    const radyo = secenekler.length
      ? `<fieldset><legend>Seçim (onaylamak için gerekli)</legend>${secenekler.map((s, i) =>
          `<label class="sec"><input type="radio" name="sec-${esc(k.id)}" value="${esc(s)}" data-secim="${esc(k.id)}"${t.secim === s ? ' checked' : ''}${kilit}> ${esc(s)}</label>`).join('')}</fieldset>`
      : '';
    return `<div class="onay-eylem">${radyo}
      <label class="meta" for="not-${esc(k.id)}">Not (isteğe bağlı)</label>
      <textarea id="not-${esc(k.id)}" rows="2" data-not="${esc(k.id)}" data-anahtar="not-${esc(k.id)}"${kilit}>${esc(t.not || '')}</textarea>
      <div class="dugmeler">
        <button type="button" class="onayla" data-karar="onay" data-id="${esc(k.id)}" data-anahtar="onay-${esc(k.id)}"${kilit}>Onayla</button>
        <button type="button" class="reddet" data-karar="ret" data-id="${esc(k.id)}" data-anahtar="ret-${esc(k.id)}"${kilit}>Reddet</button>
      </div>
      <p class="hata-satir" role="status" aria-live="polite" data-hata="${esc(k.id)}">${esc(S.hata[k.id] || '')}</p>
    </div>`;
  }

  function kartHtml(k) {
    const sonuk = ['reddedildi', 'eskidi', 'iptal'].includes(k.durum);
    const uzun = String(k.metin || '').length > 500 || String(k.metin || '').split('\n').length > 10;
    const acik = S.acik.has(k.id), katli = uzun && !acik;
    const kaynak = tabanAd(k.kaynak);
    const ust = [kaynak, O.B.tarih(k.guncelleme || k.olusturma)].filter(s => s && s !== '–').map(esc).join(' · ');
    return `<article class="onay-kart${sonuk ? ' sonuk' : ''}" style="--renk:${DURUM_RENK[k.durum] || 'var(--neutral)'}" data-kayit="${esc(k.id)}" aria-labelledby="b-${esc(k.id)}">
      <header><span class="tur-etiket" style="color:${TUR_RENK[k.tur] || 'var(--text-secondary)'}">${esc(TUR_AD[k.tur] || k.tur)}</span>
        <h3 id="b-${esc(k.id)}">${esc(k.baslik)}</h3><span class="meta">${ust}</span></header>
      <div class="onay-metin${katli ? ' kati' : ''}" id="m-${esc(k.id)}">${metinHtml(k.metin)}</div>
      ${uzun ? `<button type="button" class="cip katla" data-katla="${esc(k.id)}" data-anahtar="katla-${esc(k.id)}" aria-expanded="${acik}" aria-controls="m-${esc(k.id)}">${acik ? 'katla' : 'devamını göster'}</button>` : ''}
      ${k.durum === 'bekliyor' ? eylemHtml(k) : `<p class="durum-satir">${durumHtml(k)}</p>`}
    </article>`;
  }

  function perspektifBaslik(bekleyen) {
    const p = S.veri && S.veri.perspektif;
    if (!p || !p.rapor) return '';
    const ad = tabanAd(p.rapor);
    const m = ad.match(/(\d{4})-?(\d{2})-?(\d{2})/);
    const tarih = m ? ` · ${m[3]}.${m[2]}.${m[1]}` : '';
    const calisiyor = p.durum && p.durum.calisiyor;
    return `<h3 class="grup-baslik">Perspektif raporu: ${esc(ad)}${esc(tarih)} · ${bekleyen} madde bekliyor</h3>` +
      (calisiyor ? '<p class="meta">Perspektif şu an çalışıyor; yeni öneriler gelebilir.</p>' : '');
  }

  function cipHtml(grup, kimlik, ad, n, secili) {
    return `<button type="button" class="cip" data-${grup}="${kimlik}" aria-pressed="${secili}">${esc(ad)} · ${n}</button>`;
  }

  function sayfaCiz() {
    const kap = $('#liste');
    if (!S.veri) {
      yerlestir($('#gorunumCipler'), ''); yerlestir($('#turCipler'), ''); $('#oSayi').textContent = '';
      let metin = '<p class="bos">Yükleniyor…</p>';
      if (K && K.durum === 'hata') metin = `<p class="bos">Onaylar alınamadı: ${esc(O.yolGizle(K.hata))}</p>`;
      yerlestir(kap, metin);
      return;
    }
    const tum = kayitlar();
    yerlestir($('#gorunumCipler'), GORUNUMLER.map(([id, ad]) =>
      cipHtml('gorunum', id, ad, tum.filter(k => gorunumde(k, id)).length, S.gorunum === id)).join(''));
    const gk = tum.filter(k => gorunumde(k, S.gorunum));
    yerlestir($('#turCipler'), TURLER.map(([id, ad]) =>
      cipHtml('tur', id, ad, id === 'hepsi' ? gk.length : gk.filter(k => k.tur === id).length, S.tur === id)).join(''));
    const bek = (S.veri.sayac && S.veri.sayac.bekliyor) || 0;
    $('#oSayi').textContent = bek ? bek + ' bekliyor' : '';
    const goster = gk.filter(k => S.tur === 'hepsi' || k.tur === S.tur);
    if (!goster.length) {
      const m = S.tur !== 'hepsi' && gk.length ? 'Bu türde kayıt yok.' : BOS_METIN[S.gorunum];
      yerlestir(kap, `<p class="bos">${m}</p>`);
      return;
    }
    const persp = goster.filter(k => k.tur === 'perspektif'), diger = goster.filter(k => k.tur !== 'perspektif');
    let html = '';
    if (persp.length) {
      const bekPersp = (S.veri.sayac && S.veri.sayac.tur && S.veri.sayac.tur.perspektif) || 0;
      html += perspektifBaslik(bekPersp) + persp.map(kartHtml).join('');
    }
    html += diger.map(kartHtml).join('');
    yerlestir(kap, html);
  }

  // ------------------------------------------------------------ etkileşim
  const ana = $('main');
  function hataYaz(id, metin) {
    S.hata[id] = metin || '';
    const el = ana.querySelector(`[data-hata="${CSS.escape(id)}"]`);
    if (el) el.textContent = S.hata[id];
    const kap = $('#liste'); if (kap) kap.__html = null;   // metin DOM'da değişti; bir sonraki çizim yeniden kursun
  }
  function kilitle(id, kilit) {
    const kart = ana.querySelector(`[data-kayit="${CSS.escape(id)}"]`);
    if (kart) kart.querySelectorAll('button, input, textarea').forEach(el => {
      if (el.closest('.onay-eylem')) el.disabled = kilit;
    });
    const kap = $('#liste'); if (kap) kap.__html = null;
  }
  async function karar(id, sonuc) {
    if (S.yolda.has(id)) return;
    const t = S.taslak[id] || {};
    const k = kayitlar().find(x => x.id === id);
    if (sonuc === 'onay' && k && Array.isArray(k.secenekler) && k.secenekler.length && !t.secim) {
      hataYaz(id, 'Onaylamak için önce bir seçenek seç.');
      return;
    }
    S.yolda.add(id); hataYaz(id, ''); kilitle(id, true);
    try {
      await O.gonder('/onay?alan=' + encodeURIComponent(O.alan),
        { islem: 'karar', id, sonuc, secim: t.secim || null, not: (t.not || '').trim() });
      delete S.taslak[id]; delete S.hata[id];
      O.bildirim(sonuc === 'onay' ? id + ' onaylandı.' : id + ' reddedildi.');
      S.yolda.delete(id);
      if (K) await K.zorla();
      sayfaCiz();
    } catch (e) {
      S.yolda.delete(id);
      kilitle(id, false);
      hataYaz(id, 'Karar kaydedilemedi: ' + O.yolGizle(e && e.message ? e.message : String(e)));
    }
  }
  ana.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.karar) return karar(b.dataset.id, b.dataset.karar);
    if (b.dataset.katla) { S.acik.has(b.dataset.katla) ? S.acik.delete(b.dataset.katla) : S.acik.add(b.dataset.katla); return sayfaCiz(); }
    if (b.dataset.tur) { S.tur = b.dataset.tur; return sayfaCiz(); }
    if (b.dataset.gorunum) { S.gorunum = b.dataset.gorunum; return sayfaCiz(); }
  });
  ana.addEventListener('input', e => {
    const n = e.target.dataset && e.target.dataset.not;
    if (n) (S.taslak[n] = S.taslak[n] || {}).not = e.target.value;
  });
  ana.addEventListener('change', e => {
    const n = e.target.dataset && e.target.dataset.secim;
    if (n) { (S.taslak[n] = S.taslak[n] || {}).secim = e.target.value; hataYaz(n, ''); }
  });

  // ------------------------------------------------------------ veri
  O.kabuk({ sayfa: 'onaylar' });
  K = O.veri(() => '/onaylar.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'Onay kuyruğu', aralik: 4000,
    gecerli: v => Array.isArray(v.kayitlar) && (!v.alan || !v.alan.id || v.alan.id === O.alan),
    cizici: v => { S.veri = v; sayfaCiz(); },
    durum: () => { yerlestir($('#oBayat'), O.bayatIsaret(K)); if (!S.veri) sayfaCiz(); },
  });
  window.addEventListener('orkestra:alan', () => { S.veri = null; S.acik.clear(); S.taslak = {}; S.hata = {}; sayfaCiz(); });
})();
