'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { esc, B, E } = O;
  const { yerlestir } = O;
  const dizi = v => Array.isArray(v) ? v : [];
  const reEsc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const kucuk = s => String(s ?? '').toLocaleLowerCase('tr');
  const KARAR = { onay: 'onay', ret: 'ret', yok: 'denetim yok' };
  const RET_SUZGEC = ['sinif', 'basamak', 'neden', 'kok'];
  const RET_AD = { sinif: 'sınıf', basamak: 'basamak', neden: 'neden', kok: 'kök' };
  function retSuzgecOku() {
    const p = new URL(location.href).searchParams;
    if (p.get('ret') !== '1') return null;
    return Object.fromEntries(RET_SUZGEC.map(a => [a, p.get(a) || '']));
  }

  const S = {
    isler: null,                 // /teknik.json?alan=  (iş listesi)
    secili: new URL(location.href).searchParams.get('is') || O.depo.al('orkestra.teknik.secili') || '',
    ret: retSuzgecOku(),         // null: iş zaman çizelgesi; nesne: "Reddedilenler" görünümü ({sinif, basamak, neden, kok})
    retVeri: null,               // /teknik.json?ret=1 yanıtı; hata: {hata}
    kartlar: null,               // seçili işin kart özetleri; hata: {hata}
    ara: '',
    sinif: '', basamak: '', denetim: '',
    acik: new Set(),             // genişletilmiş kart kimlikleri
    detay: new Map(),            // kart kimliği -> 7 blok verisi ya da {hata}
  };
  let K = null, isUcus = 0, retUcus = 0;

  const sureMetin = sn => {
    if (sn == null) return '–';
    const n = Math.round(Number(sn));
    if (n < 60) return n + ' sn';
    if (n < 3600) return Math.floor(n / 60) + ' dk ' + (n % 60) + ' sn';
    return Math.floor(n / 3600) + ' sa ' + Math.floor((n % 3600) / 60) + ' dk';
  };
  const url = ek => '/teknik.json?alan=' + encodeURIComponent(O.alan) + ek;
  const retUrl = () => url('&ret=1' + RET_SUZGEC.filter(a => S.ret && S.ret[a]).map(a => '&' + a + '=' + encodeURIComponent(S.ret[a])).join(''));
  const getir = async yol => {
    const r = await fetch(yol, { cache: 'no-store' });
    const v = await r.json().catch(() => ({ hata: 'Yanıt JSON değil (HTTP ' + r.status + ')' }));
    if (!r.ok || v.acik === false || v.hata) throw new Error(v.hata || ('HTTP ' + r.status));
    return v;
  };

  // ---------------------------------------------------------------- sol: iş listesi
  function isListeHtml() {
    const v = S.isler;
    if (!v) return '<p class="bos">Yükleniyor…</p>';
    if (v.acik === false || v.hata) return `<p class="bos">${v.hata ? 'Veri üretilemedi: ' + esc(O.hataMetni(v.hata)) : 'Bu çalışma alanında orkestra kapalı.'}</p>`;
    const l = dizi(v.isler);
    if (!l.length) return '<p class="bos">Bu çalışma alanında iş yok.</p>';
    return '<ul class="t-isler">' + l.map(i => `<li><button type="button" class="t-is" data-is="${esc(i.id)}" data-anahtar="is:${esc(i.id)}" aria-current="${!S.ret && i.id === S.secili}">
      <span class="ad">${esc(i.ad || i.id)}</span>
      <span class="alt"><span>${esc(i.id)}</span><span>${esc(i.kart_sayisi)} kart</span><span title="${esc(B.kalem(i.kalem))}">${esc(B.deger(i.usd, i.token))}</span><span>${i.durum === 'kapandi' ? 'tamamlandı' : 'açık'}</span></span></button></li>`).join('') + '</ul>';
  }

  // ---------------------------------------------------------------- süzgeç
  function secenekler(id, ad, deger, liste) {
    const el = $(id);
    const html = `<option value="">${esc(ad)}</option>` + liste.map(([k, a]) => `<option value="${esc(k)}">${esc(a)}</option>`).join('');
    if (el.__html !== html) { el.innerHTML = html; el.__html = html; }
    el.value = deger;
  }
  const denetimOf = k => k.denetim === 'onay' ? 'onay' : k.denetim === 'ret' ? 'ret' : 'yok';
  function suzgecCiz() {
    const ks = dizi(S.kartlar && S.kartlar.kartlar);
    const uniq = f => [...new Set(ks.map(f).filter(Boolean))].sort();
    secenekler('#fSinif', 'Tüm sınıflar', S.sinif, uniq(k => k.sinif).map(x => [x, x]));
    secenekler('#fBasamak', 'Tüm basamaklar', S.basamak, uniq(k => k.basamak).map(x => [x, x]));
    secenekler('#fDenetim', 'Tüm denetimler', S.denetim, Object.entries(KARAR));
  }
  const eslesir = k => {
    if (S.sinif && k.sinif !== S.sinif) return false;
    if (S.basamak && k.basamak !== S.basamak) return false;
    if (S.denetim && denetimOf(k) !== S.denetim) return false;
    if (!S.ara) return true;
    const a = kucuk(S.ara);
    return [...dizi(k.dosyalar), ...dizi(k.kutuphaneler)].some(x => kucuk(x).includes(a));
  };
  const vurgu = metin => {
    const e = esc(metin);
    if (!S.ara) return e;
    return e.replace(new RegExp(reEsc(esc(S.ara)), 'gi'), m => `<mark>${m}</mark>`);
  };

  // ---------------------------------------------------------------- 7 blok
  const satirlar = (liste, bos) => liste.length ? '<ul>' + liste.map(x => `<li>${x}</li>`).join('') + '</ul>' : `<p class="eksik">${esc(bos)}</p>`;
  const blok = (ad, govde, kimlik) => `<section class="t-blok" data-blok="${kimlik}" aria-label="${esc(ad)}"><h4>${esc(ad)}</h4>${govde}</section>`;
  // Denetçinin serbest gerekçesi: metin olarak (HTML yorumlanmaz), satır sonları korunur.
  const gerekceHtml = (metin, acik) => String(metin || '').trim()
    ? `<details class="t-gerekce"${acik ? ' open' : ''}><summary>Gerekçe</summary><pre class="t-metin">${esc(metin)}</pre></details>` : '';
  const sonAd = c => esc(String(c).split(/[\\/]/).pop());

  function bloklarHtml(d) {
    const ne = d.ne || {}, neden = d.neden || {}, nasil = d.nasil || {}, deg = d.degisen || {}, dg = d.dogrulama || {};
    const ms = d.maliyet_sure || {}, og = d.ogrenilen || {};
    const t = nasil.teknik, o = nasil.otomatik || {}, kut = o.kutuphaneler || {};
    const bNe = `<p>${esc(ne.baslik || '–')} <span class="etiket">· ${esc(ne.sinif || '–')} · ${esc(ne.basamak || '–')}</span></p>` +
      satirlar(dizi(ne.kabul_kriterleri).map(esc), 'Kabul kriteri yok.') +
      (dizi(ne.ciktilar).length ? '<p class="etiket">Çıktılar</p>' + satirlar(dizi(ne.ciktilar).map(c => `<code>${sonAd(c)}</code>`), '') : '');
    const bNeden = `<p>${esc(neden.soru || 'Soru kaydı yok.')}</p>` + (neden.is ? `<p class="etiket">İş: ${esc(neden.is)}</p>` : '');
    let bNasil = '';
    if (t) {
      bNasil += `<p>${esc(t.yaklasim || '')}</p><p class="etiket">Neden bu yol</p><p>${esc(t.neden_bu_yol || '')}</p>`;
      if (dizi(t.alternatifler).length) bNasil += '<p class="etiket">Elenen seçenekler</p>' + satirlar(t.alternatifler.map(a => `${esc(a.secenek)} — ${esc(a.neden_elendi)}`), '');
      if (dizi(t.entegrasyon).length) bNasil += '<p class="etiket">Entegrasyon</p>' + satirlar(t.entegrasyon.map(esc), '');
    } else {
      bNasil += '<p><span class="t-rozet-yok">teknik not yok (eski kart)</span></p>';
    }
    const kutTum = [...dizi(kut.stdlib), ...dizi(kut.ucuncu_taraf), ...dizi(kut.yerel)];
    if (kutTum.length) bNasil += `<p class="etiket">Kütüphaneler (çıktı dosyalarından)</p><p>${kutTum.map(x => `<code>${esc(x)}</code>`).join(' ')}</p>`;
    if (dizi(o.yeni_bagimlilik).length) bNasil += '<p class="etiket">Yeni bağımlılık</p>' + satirlar(o.yeni_bagimlilik.map(esc), '');
    if (dizi(o.entegrasyon_grafi).length) bNasil += '<p class="etiket">Entegrasyon grafı</p>' + satirlar(o.entegrasyon_grafi.map(esc), '');
    const bDeg = dizi(deg.dosyalar).length
      ? satirlar(deg.dosyalar.map(f => `<code>${sonAd(f.dosya)}</code> ${f.ekle == null ? '' : `<span class="etiket">+${esc(f.ekle)} −${esc(f.sil)}</span>`}`), '') +
        (deg.son_commit ? `<p class="etiket">Son commit ${esc(String(deg.son_commit).slice(0, 8))}</p>` : '')
      : '<p class="eksik">Çıktı dosyası kaydı yok.</p>';
    const dl = [
      ...dizi(dg.test_kosulari).map(x => `Test ${esc(x.asama || '')}: ${x.gecti ? 'geçti' : 'kaldı'}`),
      ...dizi(dg.onkontrol_kosulari).map(x => `Ön kontrol: ${x.gecti ? 'geçti' : 'kaldı'}`),
      ...dizi(dg.denetimler).map(x => `Denetim ${esc(x.sira ?? '')}: ${esc(x.karar || '–')}${x.neden ? ' (' + esc(x.neden) + ')' : ''}` +
        (dizi(x.k_satirlari).length ? '<ul>' + x.k_satirlari.map(s => `<li>${esc(s)}</li>`).join('') + '</ul>' : '') + gerekceHtml(x.gerekce)),
    ];
    const su = ms.sureler || {};
    const bMal = `<p>Toplam <b>${esc(B.deger(ms.toplam_usd, ms.toplam_token))}</b></p><p class="etiket">${esc(B.kalem(ms.kalem))}</p>` +
      satirlar(dizi(ms.maliyet).map(m => `${esc(E.ajan(m.ajan))} · ${esc(E.model(m.model))}: ${esc(B.deger(m.usd, m.token))}`), 'Maliyet kaydı yok.') +
      `<p class="etiket">Kuyruk ${esc(sureMetin(su.kuyruk_sn))} · iş ${esc(sureMetin(su.is_sn))} · denetim ${esc(sureMetin(su.denetim_sn))}</p>`;
    const ogr = [
      ...dizi(og.ret_dersleri).map(r => `Ret ${esc(r.sira ?? '')}: ${esc(r.neden || '')}${r.talimat ? ' — ' + esc(r.talimat) : ''}`),
      ...dizi(og.riskler).map(r => `Risk: ${esc(r)}`),
    ];
    return blok('Ne', bNe, 'ne') + blok('Neden', bNeden, 'neden') + blok('Nasıl', bNasil, 'nasil') + blok('Değişen', bDeg, 'degisen') +
      blok('Doğrulama', satirlar(dl, 'Doğrulama kaydı yok.'), 'dogrulama') + blok('Maliyet ve süre', bMal, 'maliyet_sure') +
      blok('Öğrenilen', satirlar(ogr, 'Kayıtlı ders ya da risk yok.'), 'ogrenilen');
  }

  // ---------------------------------------------------------------- sağ: zaman çizelgesi
  function kartHtml(k) {
    const acik = S.acik.has(k.id);
    const d = S.detay.get(k.id);
    let det = '';
    if (acik) {
      det = d ? (d.hata ? `<p class="t-hata">Kart ayrıntısı alınamadı: ${esc(O.yolGizle(O.hataMetni(d.hata)))}</p>` : bloklarHtml(d)) : '<p class="bos">Yükleniyor…</p>';
      det = `<div class="t-detay" data-detay="${esc(k.id)}">${det}</div>`;
    }
    const dr = E.durum(k.durum);
    const eslesen = S.ara ? dizi(k.dosyalar).concat(dizi(k.kutuphaneler)).filter(x => kucuk(x).includes(kucuk(S.ara))).slice(0, 4) : [];
    return `<li style="--renk:${esc(dr.renk)}"><button type="button" class="t-kart" data-kart="${esc(k.id)}" data-anahtar="k:${esc(k.id)}" aria-expanded="${acik}">
      <span class="ust"><span class="kid">${esc(k.id)}</span><span class="bas">${esc(k.baslik || '')}</span>${k.teknik_var ? '' : '<span class="t-rozet-yok">teknik not yok (eski kart)</span>'}</span>
      <span class="alt"><span>${esc(k.basamak || '–')}</span><span>${esc(k.sinif || '–')}</span><span title="${esc(B.kalem(k.kalem))}">${esc(B.deger(k.usd, k.token))}</span><span>${esc(sureMetin(k.sure))}</span><span class="rozet" style="--renk:${esc(dr.renk)}"><i></i>${esc(dr.ad)}</span><span>${esc(k.dosya_sayisi)} dosya</span>${eslesen.length ? `<span>${eslesen.map(vurgu).join(', ')}</span>` : ''}</span></button>${det}</li>`;
  }

  // ---------------------------------------------------------------- sağ: reddedilenler görünümü
  const retSatir = r => `<li><div class="t-ret"><div class="ust"><span class="kid">${esc(r.kart)}</span><span class="bas">${esc(r.baslik || '')}</span></div>
    <div class="alt"><span>Ret ${esc(r.sira ?? '')}</span><span class="rozet" style="--renk:var(--warning)"><i></i>${esc(E.neden(r.neden))}</span><span>kök: ${esc(E.kok(r.kok))}</span><span>${esc(r.sinif || '–')} · ${esc(r.basamak || '–')}</span><span>${esc(B.tarih(r.zaman))}</span><span>${esc(r.is_ad || r.is || '–')}</span></div>
    ${String(r.gerekce || '').trim() ? gerekceHtml(r.gerekce, true) : '<p class="etiket">Gerekçe kaydı yok.</p>'}
    ${String(r.talimat || '').trim() ? `<p class="etiket">Talimat</p><p class="talimat">${esc(r.talimat)}</p>` : ''}
    ${r.is ? `<button type="button" class="t-git" data-is="${esc(r.is)}" data-kart="${esc(r.kart)}" data-anahtar="git:${esc(r.kart)}:${esc(r.sira ?? '')}">Kartın tüm ayrıntısını aç</button>` : ''}</div></li>`;
  function retCiz() {
    $('#tIsBaslik').textContent = 'Reddedilenler';
    $('#tArac').style.display = 'none';
    const cipler = RET_SUZGEC.filter(a => S.ret[a]);
    const cipHtml = cipler.length ? `<div class="t-cipler">${cipler.map(a => `<button type="button" class="t-cip" data-cip="${a}" data-anahtar="cip:${a}" title="Süzgeci kaldır">${esc(RET_AD[a])}: ${esc(a === 'neden' ? E.neden(S.ret[a]) : a === 'kok' ? E.kok(S.ret[a]) : S.ret[a])} ✕</button>`).join('')}</div>` : '';
    const v = S.retVeri;
    let h;
    if (!v) h = '<p class="bos">Yükleniyor…</p>';
    else if (v.hata) h = `<p class="t-hata">Ret listesi alınamadı: ${esc(O.yolGizle(O.hataMetni(v.hata)))}</p>`;
    else {
      const r = v.ret || {}, l = dizi(r.kayitlar);
      h = `<p class="meta">${B.sayi(r.toplam || 0)} ret${r.toplam > r.gosterilen ? ` · en yeni ${B.sayi(r.gosterilen)} gösteriliyor` : ''}</p>` +
        (l.length ? `<ol class="t-ret-liste" aria-label="Reddedilenler, en yeni önce">${l.map(retSatir).join('')}</ol>` : '<p class="bos" id="bosDurum">Eşleşen ret yok.</p>');
    }
    yerlestir($('#tZaman'), cipHtml + h);
  }
  function retGirisCiz() {
    const n = S.retVeri && S.retVeri.ret && !RET_SUZGEC.some(a => S.ret && S.ret[a]) ? S.retVeri.ret.toplam : null;
    yerlestir($('#tRetGiris'), `<button type="button" class="t-ret-giris" data-anahtar="ret-giris" aria-current="${!!S.ret}">Reddedilenler${n == null ? '' : ` <span class="meta">${B.sayi(n)}</span>`}</button>`);
  }
  function retUrlYaz() {
    const u = new URL(location.href);
    ['ret', ...RET_SUZGEC, 'is', 'kart'].forEach(a => u.searchParams.delete(a));
    if (S.ret) { u.searchParams.set('ret', '1'); RET_SUZGEC.forEach(a => { if (S.ret[a]) u.searchParams.set(a, S.ret[a]); }); }
    history.replaceState(null, '', u);
  }
  async function retYukle(sessiz) {
    const n = ++retUcus;
    try {
      const v = await getir(retUrl());
      if (n === retUcus && S.ret) { S.retVeri = v; sagCiz(); retGirisCiz(); }
    } catch (e) {
      if (n === retUcus && S.ret && !sessiz) { S.retVeri = { hata: e.message }; sagCiz(); }
    }
  }
  function retAc(suzgec) {
    S.ret = Object.fromEntries(RET_SUZGEC.map(a => [a, (suzgec && suzgec[a]) || '']));
    S.retVeri = null; S.secili = ''; S.kartlar = null; S.acik.clear(); S.detay.clear();
    retUrlYaz(); sayfaCiz(); retYukle();
  }

  function sagCiz() {
    if (S.ret) { retCiz(); return; }
    $('#tArac').style.display = '';
    const isA = S.isler && dizi(S.isler.isler).find(i => i.id === S.secili);
    $('#tIsBaslik').textContent = isA ? `${isA.id} · ${isA.ad || ''}` : (S.secili || 'Zaman çizelgesi');
    suzgecCiz();
    let h;
    if (!S.secili) h = '<p class="bos">Soldan bir iş seçin.</p>';
    else if (!S.kartlar) h = '<p class="bos">Yükleniyor…</p>';
    else if (S.kartlar.hata) h = `<p class="t-hata">Kartlar alınamadı: ${esc(O.yolGizle(O.hataMetni(S.kartlar.hata)))}</p>`;
    else {
      const tum = dizi(S.kartlar.kartlar), g = tum.filter(eslesir);
      if (!tum.length) h = '<p class="bos">Bu işte kart yok.</p>';
      else if (!g.length) h = '<p class="bos" id="bosDurum">Eşleşen kart yok. Süzgeçleri ya da aramayı değiştirin.</p>';
      else h = `<ol class="t-zaman" aria-label="Kartlar, yapılma sırasıyla">${g.map(kartHtml).join('')}</ol>`;
    }
    yerlestir($('#tZaman'), h);
  }

  function sayfaCiz() {
    retGirisCiz();
    $('#tSayi').textContent = S.isler && S.isler.isler ? String(S.isler.isler.length) : '';
    yerlestir($('#tIsler'), isListeHtml());
    sagCiz();
  }

  async function isYukle(id, sessiz) {
    const n = ++isUcus;
    try {
      const v = await getir(url('&is=' + encodeURIComponent(id)));
      if (n === isUcus && id === S.secili) {
        // Açık kartın ayrıntısı yalnız özeti değiştiyse yenilenir; her yoklamada yenilemek sunucuyu (git) doyuruyordu.
        const onceki = new Map(dizi(S.kartlar && S.kartlar.kartlar).map(k => [k.id, JSON.stringify(k)]));
        S.kartlar = v; sagCiz();
        dizi(v.kartlar).forEach(k => { if (S.acik.has(k.id) && onceki.has(k.id) && onceki.get(k.id) !== JSON.stringify(k)) detayYukle(k.id, true); });
      }
    } catch (e) {
      if (n === isUcus && id === S.secili && !sessiz) { S.kartlar = { hata: e.message }; sagCiz(); }
    }
  }
  const yukleniyor = new Set();   // uçuştaki kart ayrıntı istekleri (aynı kart için istek yığılmasın)
  async function detayYukle(id, zorla) {
    if ((S.detay.has(id) && !zorla) || yukleniyor.has(id)) return;
    yukleniyor.add(id);
    const is = S.secili;
    try {
      const v = await getir(url('&kart=' + encodeURIComponent(id)));
      if (is === S.secili) S.detay.set(id, v);
    } catch (e) {
      // Yenileme hatası eldeki sağlam içeriği silmez (panel hata ile içerik arasında gidip gelmesin).
      const mevcut = S.detay.get(id);
      if (is === S.secili && !(zorla && mevcut && !mevcut.hata)) S.detay.set(id, { hata: e.message });
    } finally { yukleniyor.delete(id); }
    sagCiz();
  }

  function sec(id) {
    if (!id) return;
    S.ret = null; S.retVeri = null; retUcus++;
    S.secili = id; S.kartlar = null; S.acik.clear(); S.detay.clear(); yukleniyor.clear(); S.ara = ''; $('#tAra').value = '';
    O.depo.koy('orkestra.teknik.secili', id);
    const u = new URL(location.href); ['ret', ...RET_SUZGEC].forEach(a => u.searchParams.delete(a)); u.searchParams.set('is', id); history.replaceState(null, '', u);
    sayfaCiz();
    isYukle(id);
    if (matchMedia('(max-width: 860px)').matches) $('#tSag').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ---------------------------------------------------------------- olaylar
  $('main').addEventListener('click', e => {
    const rg = e.target.closest('button.t-ret-giris');
    if (rg) { retAc({}); return; }
    const cip = e.target.closest('button.t-cip');
    if (cip) { S.ret[cip.dataset.cip] = ''; S.retVeri = null; retUrlYaz(); sagCiz(); retYukle(); return; }
    const git = e.target.closest('button.t-git');
    if (git) { sec(git.dataset.is); S.acik.add(git.dataset.kart); detayYukle(git.dataset.kart); return; }
    const ib = e.target.closest('button.t-is');
    if (ib) { sec(ib.dataset.is); return; }
    const kb = e.target.closest('button.t-kart');
    if (kb) {
      const id = kb.dataset.kart;
      if (S.acik.has(id)) S.acik.delete(id); else { S.acik.add(id); detayYukle(id); }
      sagCiz();
    }
  });
  let araZaman = 0;
  $('#tAra').addEventListener('input', e => { clearTimeout(araZaman); araZaman = setTimeout(() => { S.ara = e.target.value.trim(); sagCiz(); }, 120); });
  $('#tAra').addEventListener('keydown', e => { if (e.key === 'Escape' && e.target.value) { e.target.value = ''; S.ara = ''; sagCiz(); } });
  [['#fSinif', 'sinif'], ['#fBasamak', 'basamak'], ['#fDenetim', 'denetim']].forEach(([id, ad]) => $(id).addEventListener('change', e => { S[ad] = e.target.value; sagCiz(); }));

  // ---------------------------------------------------------------- veri
  O.kabuk({ sayfa: 'teknik' });
  K = O.veri(() => url(''), {
    ad: 'Teknik detay', aralik: 10000,
    gecerli: v => v.acik === false || (Array.isArray(v.isler) && (!v.alan || !v.alan.id || v.alan.id === O.alan)),
    cizici: v => {
      const ilk = !S.isler;
      S.isler = v;
      if (!S.secili && !S.ret && dizi(v.isler).length) S.secili = v.isler[0].id;
      sayfaCiz();
      if (S.ret) retYukle(!!S.retVeri);
      else if (S.secili) isYukle(S.secili, !(ilk || !S.kartlar));
    },
    durum: () => { yerlestir($('#tBayat'), O.bayatIsaret(K)); if (!S.isler) sayfaCiz(); },
  });
  window.addEventListener('orkestra:alan', () => { S.isler = null; S.kartlar = null; S.secili = ''; S.retVeri = null; if (S.ret) retYukle(); S.acik.clear(); S.detay.clear(); sayfaCiz(); });
})();
