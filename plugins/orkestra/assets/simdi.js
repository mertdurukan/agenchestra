'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { B, E, esc } = O;
  const { bayatCiz, ciz, yerlestir } = O;
  // Ekrana giden serbest metin: markdown soyulur, tam yollar kısaltılır (kaçışlama çizim anında esc ile).
  const metin = s => O.yolGizle(O.temizMetin(s));
  const zamanMs = s => { const t = Date.parse(s || ''); return isNaN(t) ? 0 : t; };
  const rozet = (d, ek = '') => `<span class="rozet${ek}" style="--renk:${d.renk}"><i></i>${esc(d.ad)}</span>`;

  // S.simdi / S.ozet: SON İYİ veri; hata anında silinmez (yalnız alan değişince ozet sıfırlanır).
  // Kaynak durumu (durum, sonBasari, hataBaslangic, ardisikHata, hata, bayat, uzunHata) O.veri kontrol nesnelerinde: KS, KO.
  let KS = null, KO = null;
  const S = { simdi: null, ozet: null };

  // simdi.json alanlarına korumalı erişim: biçim bozuksa boş liste
  const oturumlar = () => (S.simdi && Array.isArray(S.simdi.oturumlar)) ? S.simdi.oturumlar : [];
  const akis = () => (S.simdi && Array.isArray(S.simdi.akis)) ? S.simdi.akis : [];

  // oturum id → sohbet adı (simdi.json önce, sonra ozet.json sohbetleri)
  function sohbetAdi(oturum) {
    if (!oturum) return null;
    const r = oturumlar().find(x => x.oturum === oturum);
    if (r) return r.sohbet;
    const s = S.ozet && (S.ozet.sohbetler || []).find(x => x.oturum === oturum);
    return s ? s.baslik : null;
  }
  // Başlıktaki bayatlık işareti (gövdeye dokunmaz)
  function bayatBolumu() {
    bayatCiz({ olayBayat: O.bayatIsaret(KS, KO) });
  }

  // ------------------------------------------------------------ Son olaylar: her satır bir iş
  // Bir sohbetin niyeti ile sonucu tek işte birleşir. Durum: sonuç yazıldıysa Bitti; yoksa sohbetin o anki hali
  // (Çalışıyor / Seni bekliyor). Aynı sohbette sonradan başka işe geçildiyse eski, sonuçsuz iş gösterilmez.
  const GUN = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'];
  function gunEtiketi(z) {
    const t = new Date(zamanMs(z)), b = new Date();
    const g0 = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    const fark = Math.round((g0(b) - g0(t)) / 86400000);
    return fark <= 0 ? 'Bugün' : fark === 1 ? 'Dün' : `${GUN[t.getDay()]} · ${B.tarih(z).slice(0, 5)}`;
  }
  const DURUM_IS = {
    bitti: { ad: 'Bitti', renk: 'var(--good)', simge: '✓', dolu: true },
    claude: { ad: 'Çalışıyor', renk: 'var(--s1)', simge: '', nabiz: true },
    sen: { ad: 'Seni bekliyor', renk: 'var(--warning)', simge: '!', dolu: true },
    belirsiz: { ad: 'Sonuç yazılmadı', renk: 'var(--neutral)', simge: '' },
  };
  function isleriKur() {
    const hal = Object.fromEntries(oturumlar().map(o => [o.oturum, o.bekleyen]));
    const isler = [], son = {};   // son[oturum] = o sohbetin en son işi
    akis().slice().sort((a, b) => zamanMs(a.zaman) - zamanMs(b.zaman)).forEach(a => {
      if (a.tur !== 'niyet' && a.tur !== 'sonuc') return;
      const ne = metin(a.ne);
      const sonuc = a.tur === 'sonuc' ? metin(a.sonuc) : '';
      if (!ne || (a.tur === 'sonuc' && !sonuc)) return;
      let is = isler.find(x => x.oturum === a.oturum && x.ne === ne && !x.sonuc);
      if (!is) {
        is = { oturum: a.oturum, ne, neden: '', sohbet: a.sohbet || sohbetAdi(a.oturum) || '', zaman: a.zaman, sonuc: '' };
        isler.push(is); son[a.oturum] = is;
      }
      is.zaman = a.zaman;
      if (a.tur === 'niyet') is.neden = metin(a.neden);
      else is.sonuc = sonuc;
    });
    return isler.filter(x => x.sonuc || son[x.oturum] === x).map(x => {
      const h = x.sonuc ? 'bitti' : (hal[x.oturum] === 'claude' || hal[x.oturum] === 'sen') ? hal[x.oturum] : 'belirsiz';
      return { ...x, durum: DURUM_IS[h], h };
    }).sort((a, b) => zamanMs(b.zaman) - zamanMs(a.zaman));
  }

  function olayCiz() {
    // kaynak henüz hiç veri getirmedi ve hata da vermedi (ilk yükleme)
    const bekleniyor = !(KS && KS.durum === 'hata');
    if (!S.simdi) {
      yerlestir($('#olayOzet'), '');
      yerlestir($('#olayListe'), bekleniyor ? '<li class="bos">Yükleniyor…</li>'
        : '<li class="bos">Olaylar alınamadı; birkaç saniyede bir yeniden deneniyor.</li>');
      return;
    }
    const tum = isleriKur();
    const say = (h, f = () => true) => tum.filter(x => x.h === h && f(x)).length;
    const ozet = [['claude', 'çalışıyor', say('claude')], ['sen', 'seni bekliyor', say('sen')],
      ['bitti', 'bugün bitti', say('bitti', x => gunEtiketi(x.zaman) === 'Bugün')]]
      .filter(([, , n]) => n > 0)
      .map(([h, ad, n]) => `<span><i style="--renk:${DURUM_IS[h].renk}"></i><b>${n}</b> ${ad}</span>`).join('');
    yerlestir($('#olayOzet'), ozet);
    let onceki = '';
    const html = tum.length ? tum.slice(0, 20).map(x => {
      const gun = gunEtiketi(x.zaman);
      const baslik = gun !== onceki ? `<li class="gun" role="presentation">${esc(gun)}</li>` : '';
      onceki = gun;
      const d = x.durum, ayrinti = x.sonuc || x.neden;
      const anahtar = 'o:' + x.oturum + '|' + x.ne.slice(0, 60);
      const ac = x.oturum ? ` data-oturum="${esc(x.oturum)}" data-anahtar="${esc(anahtar)}" tabindex="0" role="button" aria-label="${esc(x.ne + ' · ' + d.ad + ' · sohbeti aç')}" title="Sohbeti aç"` : '';
      return `${baslik}<li class="is"${ac} style="--renk:${d.renk}">
        <span class="sim${d.dolu ? ' dolu' : ''}${d.nabiz ? ' nabiz' : ''}" aria-hidden="true">${d.simge}</span>
        <div><div class="baslik">${esc(x.ne)}</div>
        ${ayrinti ? `<div class="ayrinti">${esc(ayrinti)}</div>` : ''}
        <div class="alt"><span class="durum">${d.ad}</span> · <span title="${esc(B.tarih(x.zaman))}">${B.saat(x.zaman)}</span></div></div></li>`;
    }).join('') : bekleniyor ? '<li class="bos">Yükleniyor…</li>'
      : '<li class="bos">Henüz olay yok. Claude her yeni işin başında tek satır niyet yazar.</li>';
    yerlestir($('#olayListe'), html);
  }

  const hepsi = () => ciz(olayCiz, bayatBolumu);

  // ------------------------------------------------------------ etkileşim
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
  const ana = $('main');
  ana.addEventListener('click', e => {
    const el = e.target.closest('[data-oturum]');
    if (el) sohbetAc(el.dataset.oturum);
  });
  // role="button" öğeleri (div/li) için Enter ve Space; gerçek <button> bunu kendisi yapar.
  ana.addEventListener('keydown', e => {
    const el = e.target.closest('[data-oturum][role="button"]');
    if (el && el === e.target && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); sohbetAc(el.dataset.oturum); }
  });

  // ------------------------------------------------------------ veri
  O.kabuk({ sayfa: 'simdi' });
  // Yeni veri → ilgili bölümler çizilir. Durum değişimi (hata/toparlanma) → yalnız başlık işaretleri;
  // son iyi veri yokken ilgili bölüm tam hata satırına geçer. Kısa kopuklukta gövde DOM'u değişmez.
  KS = O.veri(() => '/simdi.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'Sohbet verisi', aralik: 5000,
    gecerli: v => Array.isArray(v.oturumlar) && (!v.alan || !v.alan.id || v.alan.id === O.alan),
    cizici: v => { S.simdi = v; hepsi(); },
    durum: () => ciz(bayatBolumu, ...(S.simdi ? [] : [olayCiz])),
  });
  // maliyet tutarları bu sayfada kullanılmaz: imzaya girmez, her kuruş artışında yeniden çizilmez.
  // sohbetler (ad yedeği) imzada kalır ki ad bayatlamasın; DOM'u yerlestir() yalnız HTML değişince kurar.
  KO = O.veri(() => '/ozet.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'Görev verisi', aralik: 3000, yoksay: ['uretim', 'maliyet'],
    cizici: v => { S.ozet = v; ciz(olayCiz, bayatBolumu); },
    durum: () => ciz(bayatBolumu, ...(S.ozet ? [] : [olayCiz])),
  });
  // Alan değişince eski alanın kartları "son iyi veri" değildir. KO'nun dinleyicisi (yukarıda kayıtlı, önce çalışır)
  // sifirla() + yeni istek yapmıştır; burada AYNI olay turunda eski alanın kartları ve
  // defter satırları kaldırılır: olaylarda yalnız sohbet akışı kalır.
  window.addEventListener('orkestra:alan', () => {
    S.simdi = null; S.ozet = null;
    try { ciz(olayCiz, bayatBolumu); } catch (e) { /* ciz hatayı konsola yazdı; veri gelince yeniden çizilir */ }
  });
})();
