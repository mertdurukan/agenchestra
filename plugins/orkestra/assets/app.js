/* Orkestra paneli v2: karar odaklı kontrol odası.
   Görünümler: Gelen kutusu (açılış) · İşler (liste + ayrıntı) · Koşular · Kart izi · Maliyet · Kurallar · Yapılacaklar · Ayarlar.
   Veri: mevcut JSON uçları; canlı güncelleme /akis (SSE). Harici kitaplık yok.
   Adresler: #/gelen  #/isler?f=acik&q=…  #/is/I-003  #/kosular?b=T2&s=sure  #/kart/G-127  #/maliyet?p=son_3_gun  #/kurallar?q=…  #/yapilacaklar  #/araclar  #/ayarlar */
(() => {
  'use strict';

  // ================================================================ 1. Araçlar
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const yaz = v => (v == null || v === false) ? '' : Array.isArray(v) ? v.map(yaz).join('') : (typeof v === 'object' && '__h' in v) ? v.__h : esc(v);
  const H = (s, ...v) => ({ __h: s.reduce((a, p, i) => a + p + (i < v.length ? yaz(v[i]) : ''), '') });
  const ham = s => ({ __h: String(s ?? '') });
  const enc = encodeURIComponent;

  const depo = {
    al(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    koy(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* özel pencere */ } },
  };

  const sayiB = (n, ond = 0) => new Intl.NumberFormat('tr-TR', { minimumFractionDigits: ond, maximumFractionDigits: ond }).format(n);
  const PENCERE = [['bugun', 'Bugün'], ['son_3_gun', 'Son 3 gün'], ['son_7_gun', 'Son 7 gün'], ['bu_ay', 'Bu ay'], ['tum_zaman', 'Tümü']];
  const pencereAd = k => (PENCERE.find(p => p[0] === k) || [])[1] || '';
  // Her para/token değeri B.para ya da B.paraP'den geçer: pencere ve birim seçimi tek yerde uygulanır (I-137).
  // Ham B.usd / B.token yalnız B içinde çağrılır; tests/test_panel_pencere_birim.py bunu denetler.
  const B = {
    usd(v) {
      if (v == null || isNaN(v)) return '–';
      const a = Math.abs(v);
      return (v < 0 ? '−' : '') + '$' + sayiB(a, a < 1000 ? 2 : 0);
    },
    token(n) {
      if (n == null || isNaN(n)) return '–';
      const a = Math.abs(n);
      if (a >= 1e6) return sayiB(a / 1e6, a < 1e7 ? 1 : 0) + ' M';
      if (a >= 1e3) return sayiB(a / 1e3, a < 1e4 ? 1 : 0) + ' K';
      return sayiB(a);
    },
    olcu: () => depo.al('orkestra.olcu') === 'token' ? 'token' : 'usd',   // klasik sayfalarla ortak anahtar
    birim: () => B.olcu() === 'token' ? 'Token' : 'USD',
    pencere() { const v = depo.al('orkestra.v2.pencere'); return PENCERE.some(p => p[0] === v) ? v : 'son_3_gun'; },
    // seçili birimde değer; token verisi yoksa '–' (USD'ye düşmek aynı sütunda iki birimi karıştırır)
    para: (usd, token) => B.olcu() === 'token' ? B.token(token) : B.usd(usd),
    // { pencere: { <pencere>: { usd, token } } } taşıyan kayıt için seçili pencerenin değeri; pencerede harcama yoksa '–'
    paraP(o) { const x = o?.pencere?.[B.pencere()]; return !x || (!x.usd && !x.token) ? '–' : B.para(x.usd, x.token); },
    // pencereden ve birimden bağımsız USD ölçüsü (ör. onaylı kart başına USD): token modunda '$' yerine 'USD' eki
    usdSabit: x => B.olcu() !== 'token' ? B.usd(x) : x == null || isNaN(x) ? '–' : sayiB(x, 2) + ' USD',
    yuzde: (x, ond = 0) => x == null || isNaN(x) ? '–' : '%' + sayiB(x * 100, ond),
    sayi: (x, ond = 0) => x == null || isNaN(x) ? '–' : sayiB(x, ond),
    sure(sn) {
      if (sn == null || isNaN(sn)) return '–';
      sn = Math.round(sn);
      if (sn < 60) return sn + ' sn';
      const dk = Math.round(sn / 60);
      if (dk < 60) return dk + ' dk';
      const sa = Math.floor(dk / 60), kdk = dk % 60;
      if (sa < 48) return sa + ' sa' + (kdk ? ' ' + kdk + ' dk' : '');
      return Math.round(sa / 24) + ' gün';
    },
    goreli(z) {
      if (!z) return '–';
      const t = new Date(z).getTime();
      if (isNaN(t)) return '–';
      const sn = (Date.now() - t) / 1000;
      if (sn < 45) return 'şimdi';
      if (sn < 3600) return Math.round(sn / 60) + ' dk önce';
      if (sn < 86400) return Math.round(sn / 3600) + ' sa önce';
      const g = Math.round(sn / 86400);
      return g === 1 ? 'dün' : g + ' gün önce';
    },
    tarih(z) {
      const d = new Date(z);
      return isNaN(d) ? '–' : d.toLocaleString('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    },
  };
  const kucult = s => String(s ?? '').toLocaleLowerCase('tr-TR');
  const eslesir = (metin, q) => { const m = kucult(metin); return kucult(q).split(/\s+/).filter(Boolean).every(p => m.includes(p)); };
  const kisalt = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  const ilkCumle = s => { const m = String(s ?? '').replace(/^ZORUNLU, istisnasız:\s*/, '').match(/^(.{20,180}?[.!?])(\s|$)/); return m ? m[1] : kisalt(String(s ?? '').replace(/^ZORUNLU, istisnasız:\s*/, ''), 160); };
  const yolKisa = p => String(p ?? '').replace(/\\/g, '/').split('/').slice(-2).join('/');
  const medyan = a => { const s = a.filter(x => x != null).sort((x, y) => x - y); if (!s.length) return null; const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

  // Basit çizgi simgeler (16 px, currentColor)
  const S = {
    gelen: '<path d="M2 9h3.5l1.2 2h2.6l1.2-2H14"/><path d="M3.5 3.5h9L14 9v3.5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V9z"/>',
    isler: '<path d="M8 2 14 5 8 8 2 5z"/><path d="m2 8 6 3 6-3"/><path d="m2 11 6 3 6-3"/>',
    kosular: '<path d="M1.5 8h3l2-5 3 10 2-5h3"/>',
    maliyet: '<path d="M2.5 13.5h11"/><path d="M4 11V8"/><path d="M7 11V4"/><path d="M10 11V6.5"/><path d="M13 11V2.5"/>',
    kurallar: '<path d="M3.5 2.5h7l2 2v9h-9z"/><path d="M5.5 6.5h5M5.5 9h5M5.5 11.5h3"/>',
    araclar: '<path d="M9.5 2.5 13.5 6.5 6.5 13.5 2.5 13.5 2.5 9.5z"/><path d="m8 4 4 4"/>',
    ayarlar: '<path d="M3 4.5h5M11 4.5h2M3 11.5h2M8 11.5h5"/><circle cx="9.5" cy="4.5" r="1.5"/><circle cx="6.5" cy="11.5" r="1.5"/>',
    yapilacaklar: '<path d="M6.5 4.5h7M6.5 8h7M6.5 11.5h7"/><path d="m2 4.5 1 1 1.6-2M2 8l1 1 1.6-2M2 11.5l1 1 1.6-2"/>',
    onay: '<path d="m3 8.5 3 3 7-7"/>',
    sohbet: '<path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/>',
    kart: '<rect x="2.5" y="3" width="11" height="10" rx="1.5"/><path d="M5 6.5h6M5 9.5h3.5"/>',
    uyari: '<path d="M8 2.5 14 13H2z"/><path d="M8 6.5v3M8 11.3v.2"/>',
    hedef: '<circle cx="8" cy="8" r="5.5"/><circle cx="8" cy="8" r="2"/>',
    oynat: '<path d="M5 3.5v9l7-4.5z"/>',
    saat: '<circle cx="8" cy="8" r="5.5"/><path d="M8 5v3l2 1.5"/>',
    kalkan: '<path d="M8 2 13 4v4c0 3-2.2 5-5 6-2.8-1-5-3-5-6V4z"/>',
    test: '<path d="M6 2.5h4M7 2.5v4L3.5 12.5a.8.8 0 0 0 .7 1.2h7.6a.8.8 0 0 0 .7-1.2L9 6.5v-4"/>',
    goz: '<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>',
    tamam: '<path d="m3 8.5 3 3 7-7"/>',
    carpi: '<path d="m4 4 8 8M12 4l-8 8"/>',
    ara: '<circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/>',
    guncelle: '<path d="M13.5 8a5.5 5.5 0 1 1-1.8-4.1"/><path d="M13.5 2.5v3h-3"/>',
  };
  const simge = ad => ham(`<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${S[ad] || ''}</svg>`);

  // ================================================================ 2. Veri
  // V.alan: seçili çalışma alanı kimliği ya da TUM ('Tüm çalışma alanları', ADR-0030). Birleşik kipte sunucu orkestralı alanları
  // birleştirir ve her kayda alan:{id,ad} ekler; iş/kart ayrıntısı ve yazma kaydın kendi alanıyla gider.
  const TUM = '*';
  const V = { alan: '', alanlar: [], onbellek: new Map(), sonBasari: 0, gIzle: 0 };
  const tumMu = () => V.alan === TUM;
  const TEK_ALAN_YOL = /^\/(teknik\.json\?(?:.*&)?(?:is|kart|ret)=|api\/todo)/;   // sunucuda tek alan ister (liste kipi birleşir)
  const orkAlanlar = () => V.alanlar.filter(a => a.orkestra);
  const alanAd = id => (V.alanlar.find(a => a.id === id) || {}).ad || id;
  // son seçilen gerçek alan: klasik sayfalar birleşik kipi bilmez, bağlantıları buna gider
  const gercekAlan = () => { const k = depo.al('orkestra.alan'); return tumMu() ? (orkAlanlar().find(a => a.id === k) || orkAlanlar()[0] || {}).id || '' : V.alan; };
  // birleşik kipte rota alanı: ?alan= ya da yüklü listelerde kimliğin tek bir alanda geçtiği yer
  function rotaAlani(r) {
    if (!tumMu()) return V.alan;
    const a = r.q.get('alan');
    if (a) return a;
    const liste = r.ad === 'isler' ? (d('/isler.json').veri?.isler || [])
      : r.ad === 'kart' ? [...(d('/ozet.json').veri?.kartlar || []), ...(d('/analitik.json').veri?.akis?.kartlar || [])] : [];
    const alanlar = new Set(liste.filter(x => x.id === r.id && x.alan).map(x => x.alan.id));
    return alanlar.size === 1 ? [...alanlar][0] : '';
  }
  const alanAl = yol => tumMu() && TEK_ALAN_YOL.test(yol) ? rotaAlani(rota()) : V.alan;
  const urlAl = (yol, alan) => yol.startsWith('/ac?') ? yol : yol + (yol.includes('?') ? '&' : '?') + 'alan=' + enc(alan || alanAl(yol));   // /ac oturum kimliğiyle çalışır, alan almaz
  // bağlantıya kaydın alanı eklenir (yalnız birleşik kipte); q verilirse mevcut süzgeçler korunur, eski alan düşer
  const ek = (q, o) => {
    const c = new URLSearchParams(q || ''); c.delete('alan');
    if (tumMu() && o?.alan?.id) c.set('alan', o.alan.id);
    const t = c.toString(); return t ? '?' + t : '';
  };
  const alanRozeti = o => tumMu() && o?.alan?.ad ? H`<span class="etiket alan-rozet" title="Çalışma alanı: ${o.alan.ad}">${o.alan.ad}</span>` : '';
  const altAlan = o => (o?.alan?.id || '') + '|' + (o?.id || '');   // kimlikler alanlar arasında çakışabilir
  const imzasi = v => { try { const k = { ...v }; delete k.uretim; return JSON.stringify(k); } catch (e) { return Math.random() + ''; } };

  const anahtar = yol => alanAl(yol) + '|' + yol;   // iş/kart ayrıntısı aynı kimlikle iki alanda çakışmasın
  function kayit(yol) {
    const a = anahtar(yol);
    if (!V.onbellek.has(a)) V.onbellek.set(a, { veri: null, hata: null, zaman: 0, imza: '', istek: null });
    return V.onbellek.get(a);
  }
  async function getir(yol, { taze = false } = {}) {
    const k = kayit(yol);
    if (k.istek) return k.istek;
    if (!taze && k.veri && Date.now() - k.zaman < 2000) return k.veri;
    k.istek = (async () => {
      const ctl = new AbortController();
      const zs = setTimeout(() => ctl.abort(), 30000);
      try {
        if (!alanAl(yol)) throw new Error('Bu ayrıntı için çalışma alanı gerekir; bağlantıda alan yok ve kimlik tek bir alanda bulunamadı.');
        const r = await fetch(urlAl(yol), { signal: ctl.signal });
        const v = await r.json().catch(() => null);
        if (!r.ok || !v) throw new Error((v && v.hata) || 'HTTP ' + r.status);
        const imza = imzasi(v);
        const degisti = imza !== k.imza;
        Object.assign(k, { veri: v, hata: null, zaman: Date.now(), imza });
        V.sonBasari = Date.now();
        if (yol === GUNC_YOL) guncellemeIzle();
        if (degisti) { eksikleriGetir(); planla(); }
        return v;
      } catch (e) {
        k.hata = e.name === 'AbortError' ? 'Zaman aşımı (30 sn)' : (e.message || String(e));
        planla();
        return null;
      } finally { clearTimeout(zs); k.istek = null; }
    })();
    return k.istek;
  }
  const d = yol => kayit(yol);
  // liste yüklenince (ör. kimlikten alan çözülünce) henüz istenmemiş ayrıntı verisini getirir
  function eksikleriGetir() { gerekler(rota()).forEach(y => { const k = kayit(y); if (!k.veri && !k.istek && !k.hata && alanAl(y)) getir(y); }); }
  const tazele = (taze = false) => gerekler(rota()).concat(TEMEL).forEach(y => getir(y, { taze }));
  const GUNC_YOL = '/api/guncelleme';   // eklenti güncelleme durumu: kullanıcı düzeyi, çalışma alanından bağımsız (ADR-0039)
  const GUNC_ARALIK = 1000;             // ms: koşu sürerken ilerleme yoklaması
  const TEMEL = ['/onaylar.json', '/simdi.json', '/ozet.json', '/isler.json', GUNC_YOL];
  const YAP_YOL = '/api/kullanici-todo';
  const ARAC_MCP = '/api/araclar-mcp';       // hazır MCP'ler: kullanıcı düzeyi (claude mcp add/remove --scope user)
  const ARAC_SKILL = '/api/araclar-skill';   // skill'ler: seçili çalışma alanının .claude/settings.local.json'u
  const AYAR_YOL = '/api/ayarlar';   // kullanıcı ayarları (bildirim): makine düzeyi, çalışma alanından bağımsız

  // Güncelleme koşusu sürerken durumu saniyede bir yeniler; koşu bitince (ya da sunucu 'çalışıyor' demeyince) kendiliğinden durur.
  function guncellemeIzle() {
    if (V.gIzle || d(GUNC_YOL).veri?.durum !== 'calisiyor') return;
    V.gIzle = setTimeout(async () => { V.gIzle = 0; await getir(GUNC_YOL, { taze: true }); guncellemeIzle(); }, GUNC_ARALIK);
  }

  async function gonder(yol, govde, alan) {
    const r = await fetch(urlAl(yol, alan), { method: 'POST', headers: { 'X-Orkestra': '1', 'Content-Type': 'application/json' }, body: JSON.stringify(govde || {}) });
    const v = await r.json().catch(() => null);
    if (!r.ok || !v || v.tamam === false) {
      const e = new Error((v && v.hata) || 'HTTP ' + r.status);
      e.veri = v;   // sunucu yanıt gövdesi (ör. is-kapat 422 `kapi`): istemci hata metnini ayrıştırmaz
      throw e;
    }
    return v;
  }

  // Sohbeti Claude masaüstünde açar (isler.js sohbetAc ile aynı yol): uygulama bağlantısı varsa tıklama anında tarayıcı
  // açar (Windows yalnız öndeki sürecin başlattığı uygulamayı öne getirir); bağlantıyı iletmeyen gömülü görünümde
  // sayfa odağı kaybetmez → sunucu yolu (POST /ac). Hangi yolun çalıştığı ilk tıklamada öğrenilir.
  async function sohbetAc(oturum, ad) {
    if (!oturum) return;
    const r0 = ((d('/simdi.json').veri || {}).oturumlar || []).find(x => x.oturum === oturum);
    const link = r0 && typeof r0.link === 'string' && /^claude:\/\/claude\.ai\/epitaxy\/[\w-]+$/.test(r0.link) ? r0.link : '';
    const yol = depo.al('orkestra.acYolu');
    if (link && yol === 'link') { location.href = link; return bildir('Açılıyor: ' + (ad || 'sohbet')); }
    if (link && yol !== 'sunucu') {
      let gitti = false;
      const kayip = () => { gitti = true; };
      window.addEventListener('blur', kayip, { once: true });
      document.addEventListener('visibilitychange', kayip, { once: true });
      location.href = link;
      bildir('Açılıyor: ' + (ad || 'sohbet'));
      await new Promise(c => setTimeout(c, 1500));
      window.removeEventListener('blur', kayip);
      document.removeEventListener('visibilitychange', kayip);
      depo.koy('orkestra.acYolu', gitti ? 'link' : 'sunucu');
      if (gitti) return;
    }
    bildir('Sohbet açılıyor…');
    try {
      const r = await gonder('/ac?oturum=' + enc(oturum));
      bildir(r.yol === 'cli' ? 'Sohbet Claude uygulamasında sürdürülüyor' : 'Açıldı: ' + (r.baslik || ad || 'sohbet'));
    } catch (x) { bildir('Açılamadı: ' + x.message, { hata: true }); }
  }

  // ================================================================ 3. Yönlendirme
  function rota() {
    const h = location.hash.replace(/^#\/?/, '');
    const [yolS, sorgu = ''] = h.split('?');
    const p = yolS.split('/').filter(Boolean).map(decodeURIComponent);
    const q = new URLSearchParams(sorgu);
    if (!p.length || p[0] === 'gelen') return { ad: 'gelen', q };
    if (p[0] === 'is' && p[1]) return { ad: 'isler', id: p[1], q };
    if (p[0] === 'kart' && p[1]) return { ad: 'kart', id: p[1], q };
    if (['isler', 'kosular', 'maliyet', 'kurallar', 'yapilacaklar', 'araclar', 'ayarlar'].includes(p[0])) return { ad: p[0], q };
    return { ad: 'gelen', q };
  }
  const git = h => { if (location.hash !== h) location.hash = h; };
  function sorguKoy(k, v) {
    const r = rota();
    if (v == null || v === '') r.q.delete(k); else r.q.set(k, v);
    const temel = location.hash.split('?')[0] || '#/gelen';
    const s = r.q.toString();
    history.replaceState(null, '', temel + (s ? '?' + s : ''));
    gorunumCiz();
  }
  const sorguEk = (q, haric = []) => { const c = new URLSearchParams(q); haric.forEach(k => c.delete(k)); const s = c.toString(); return s ? '?' + s : ''; };

  // Pencere ve birim seçimi (I-137): üst çubuktan, p / u kısayolundan ve komut paletinden değişir; tüm sayfalar B.pencere() / B.olcu() ile okur.
  const KONTROL_ROTA = ['gelen', 'isler', 'kosular', 'maliyet', 'kart'];
  const kontrolVar = () => KONTROL_ROTA.includes(rota().ad);
  function pencereKoy(v) {
    if (!PENCERE.some(p => p[0] === v)) return;
    depo.koy('orkestra.v2.pencere', v);
    gorunumCiz();
  }
  const pencereSonraki = () => { const i = PENCERE.findIndex(p => p[0] === B.pencere()); pencereKoy(PENCERE[(i + 1) % PENCERE.length][0]); };
  function olcuKoy(v) {
    depo.koy('orkestra.olcu', v === 'usd' || v === 'token' ? v : B.olcu() === 'token' ? 'usd' : 'token');   // klasik sayfalarla ortak anahtar
    gorunumCiz();
  }
  // #/…?p=son_7_gun derin bağlantısı seçimi uygular ve saklar, adresten çıkarır
  function derinBaglanti() {
    const r = rota(), p = r.q.get('p');
    if (p == null) return;
    if (PENCERE.some(x => x[0] === p)) depo.koy('orkestra.v2.pencere', p);
    r.q.delete('p');
    const s = r.q.toString();
    history.replaceState(null, '', (location.hash.split('?')[0] || '#/gelen') + (s ? '?' + s : ''));
  }
  function kontroller(r) {
    if (!KONTROL_ROTA.includes(r.ad)) return '';
    const p = B.pencere(), o = B.olcu(), kart = r.ad === 'kart';
    return H`<div class="kontrol-grup">
      <div class="kontrol" role="group" aria-label="Zaman penceresi">${kart ? H`<span class="soluk kucuk-y">kartın tüm ömrü</span>` : ''}${PENCERE.map(([k, ad]) => H`<button class="cip" data-eylem="pencere" data-v="${k}" aria-pressed="${!kart && p === k ? 'true' : 'false'}" ${kart ? ham('disabled title="Kart izi kartın tüm ömrünü gösterir"') : ''}>${ad}</button>`)}</div>
      <div class="kontrol" role="group" aria-label="Ölçü birimi">${[['usd', 'USD'], ['token', 'Token']].map(([k, ad]) => H`<button class="cip" data-eylem="olcu" data-v="${k}" aria-pressed="${o === k ? 'true' : 'false'}">${ad}</button>`)}</div>
    </div>`;
  }

  function gerekler(r) {
    switch (r.ad) {
      case 'gelen': return ['/onaylar.json', '/simdi.json', '/ozet.json', '/analitik.json'];
      case 'isler': return ['/isler.json'].concat(r.id ? [`/teknik.json?is=${enc(r.id)}`, `/api/todo?is=${enc(r.id)}`] : []);
      case 'kosular': return ['/analitik.json', '/ozet.json'];
      case 'kart': return [`/teknik.json?kart=${enc(r.id)}`, '/analitik.json', '/ozet.json'];
      case 'maliyet': return ['/analitik.json', '/ozet.json'];
      case 'kurallar': return ['/kurallar.json'];
      case 'yapilacaklar': return [YAP_YOL];
      case 'araclar': return tumMu() ? [ARAC_MCP] : [ARAC_MCP, ARAC_SKILL];
      case 'ayarlar': return [AYAR_YOL];
      default: return [];
    }
  }

  // ================================================================ 4. Ortak parçalar
  const DURUM = {
    teslim: ['Teslim', 'r-iyi'], onay: ['Onay', 'r-iyi'], beklemede: ['Beklemede', 'r-uyari'], ret: ['Ret', 'r-kotu'],
    iptal: ['İptal', 'r-notr'], suruyor: ['Sürüyor', 'r-bilgi'], calisiyor: ['Çalışıyor', 'r-bilgi'], denetimde: ['Denetimde', 'r-bilgi'],
    acik: ['Açık', 'r-vurgu'], kapandi: ['Kapandı', 'r-notr'], bitti: ['Bitti', 'r-iyi'], bekliyor: ['Bekliyor', 'r-uyari'],
    iyi: ['İyi', 'r-iyi'], uyari: ['Uyarı', 'r-uyari'], kotu: ['Hedef dışı', 'r-kotu'], 'veri-yok': ['Veri yok', 'r-notr'], 'yetersiz-ornek': ['Az örnek', 'r-notr'],
  };
  const rozet = (durum, metin) => { const [ad, sinif] = DURUM[durum] || [durum || '–', 'r-notr']; return H`<span class="rozet ${sinif}">${metin || ad}</span>`; };
  const iskelet = (n = 4, y = 44) => H`<div class="yigin sik">${Array.from({ length: n }, () => H`<div class="iskelet" style="height:${y}px"></div>`)}</div>`;
  const hataKutu = (metin, yol) => H`<div class="hata-kutu" role="alert">${simge('uyari')}<span>Veri alınamadı: ${metin}</span><button class="dugme kucuk" data-eylem="yenile" data-yol="${yol || ''}">Tekrar dene</button></div>`;
  const bos = (baslik, metin, s = 'tamam') => H`<div class="bos-durum"><div class="buyuk">${simge(s)}</div><b>${baslik}</b><p>${metin || ''}</p></div>`;
  // Veri hazır değilse iskelet ya da hata döner; hazırsa null
  function bekle(...yollar) {
    for (const y of yollar) {
      const k = d(y);
      if (!k.veri && k.hata) return hataKutu(k.hata, y);
      if (!k.veri) return iskelet();
      if (k.veri.acik === false) return bos('Bu çalışma alanında orkestra açık değil', k.veri.hata || '', 'uyari');
    }
    return null;
  }
  function spark(degerler, gen = 96, yuk = 24) {
    const v = degerler.filter(x => x != null);
    if (v.length < 2) return '';
    const mx = Math.max(...v) || 1, adim = gen / (v.length - 1);
    const n = v.map((x, i) => [i * adim, yuk - 2 - (x / mx) * (yuk - 4)]);
    const cizgi = n.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
    return ham(`<svg class="spark" width="${gen}" height="${yuk}" viewBox="0 0 ${gen} ${yuk}" aria-hidden="true"><path class="alan" d="${cizgi} L${gen} ${yuk} L0 ${yuk}Z"/><path d="${cizgi}"/></svg>`);
  }
  const ilerleme = (oran, renk) => H`<div class="ilerleme"><i style="width:${Math.max(0, Math.min(1, oran || 0)) * 100}%;${renk ? `--renk:${renk}` : ''}"></i></div>`;
  const karo = (ad, deger, alt, href) => H`<div class="karo"><span class="ad">${ad}</span><span class="deger">${deger}</span>${alt ? (href ? H`<a class="alt" href="${href}">${alt}</a>` : H`<span class="alt">${alt}</span>`) : ''}</div>`;
  const kartBilgi = (id, alan) => {
    const es = k => k.id === id && (!tumMu() || !alan || k.alan?.id === alan);
    const a = (d('/analitik.json').veri?.akis?.kartlar || []).find(es);
    const o = (d('/ozet.json').veri?.kartlar || []).find(es);
    return { ...(a || {}), ...(o || {}) };
  };

  // ================================================================ 5. Görünüm: Gelen kutusu
  const OLCU_AD = {
    ana_ajan_payi: ['Ana ajan payı', x => B.yuzde(x)], isci_cagrisi_kart: ['İşçi çağrısı / kart', x => B.sayi(x, 2)],
    onayli_kart_usd: ['Onaylı kart başına USD', x => B.usdSabit(x)], ret_orani: ['Ret oranı', x => B.yuzde(x, 1)],
    teknik_not_kapsama: ['Teknik not kapsaması', x => B.yuzde(x)],
  };
  const ertelenen = new Map();   // onay id → { z: zamanlayıcı, sonuc, secim }  (geri al süresi içindeki kararlar)

  // "Şimdi uygula" kartları: bekleyen karar varsa ya da koşu sürüyorsa (kosu=true → durum gösterir, düğme kapalı)
  function uygulaOgeleri(ozetler) {
    const out = [];
    ozetler.forEach(o => {
      const n = o.sayac?.panelden_uygulanabilir || 0, kosu = !!o.uygulama;
      if (n > 0 || kosu) out.push({ tur: 'uygula', n: n || (o.uygulama?.idler || []).length, alan: o.alan, kosu });
    });
    return out;
  }
  // Hedef dışı ölçü kartı "İncele" ya da "Yoksay" ile kalkar; kullanıcı başına tarayıcıda tutulur (ad|pencere)
  const OLCU_GIZLI = 'orkestra.olcu-gizli';
  function olcuGizli() { try { return new Set(JSON.parse(depo.al(OLCU_GIZLI) || '[]')); } catch (e) { return new Set(); } }
  function olcuGizle(ad, pencere) { const s = olcuGizli(); s.add(ad + '|' + pencere); depo.koy(OLCU_GIZLI, JSON.stringify([...s])); planla(); }
  function gelenOgeleri() {
    const on = d('/onaylar.json').veri, sm = d('/simdi.json').veri, oz = d('/ozet.json').veri, an = d('/analitik.json').veri;
    const g = { karar: [], sohbet: [], teslim: [], sahipsiz: [], kart: [], olcu: [] };
    const gu = d(GUNC_YOL).veri;   // eklenti güncellemesi her zaman en üstte; "Sonra" yalnız 'yeni' durumunu gizler (koşu ve hata görünür kalır)
    if (gu && ['yeni', 'calisiyor', 'bitti', 'hata'].includes(gu.durum) && !(gu.durum === 'yeni' && gu.ertelendi)) g.karar.push({ tur: 'guncelleme', g: gu });
    if (on && on.acik !== false) {
      (on.kayitlar || []).filter(k => k.durum === 'bekliyor' && !ertelenen.has(altAlan(k))).forEach(k => g.karar.push({ tur: 'onay', k }));
      // uygulama ve perspektif eylemleri çalışma alanına özeldir: birleşik kipte her alan kendi satırını alır
      const ozetler = tumMu() ? (on.alan_ozetleri || []) : [{ alan: null, sayac: on.sayac, perspektif: on.perspektif, uygulama: on.uygulama }];
      // koşu sürerken kart kalır ama "uygulanıyor" gösterir; koşu kayıtları kapatınca sayaç sıfırlanır, kart kalkar
      uygulaOgeleri(ozetler).forEach(o => g.karar.push(o));
      (on.kayitlar || []).filter(k => k.etki?.soru_bekliyor).forEach(k => g.karar.push({ tur: 'etki', k }));
      ozetler.forEach(o => {   // perspektif elle başlar (ADR-0026): zamanı gelince burada görünür
        const pd = o.perspektif?.durum;
        if (pd?.zamani_geldi && !pd.calisiyor) g.karar.push({ tur: 'perspektif', d: pd, alan: o.alan });
      });
    }
    if (sm) (sm.oturumlar || []).filter(o => o.bekleyen === 'sen' && !o.arsiv).forEach(o => g.sohbet.push({ tur: 'sohbet', o }));
    if (oz && oz.acik !== false) (oz.kartlar || []).filter(k => !['teslim', 'iptal'].includes(k.durum)).forEach(k => (k.durum === 'onaylandi' ? g.teslim : k.sahip_arsivli ? g.sahipsiz : g.kart).push({ tur: 'kart', k }));   // I-145: onaylı = teslim bekliyor; sahibi arşivli = sahipsiz
    if (an?.onbellek?.katman_5dk_son_24s > 0) g.karar.push({ tur: 'katman5', n: an.onbellek.katman_5dk_son_24s });   // 5 dk önbellek katmanı nöbeti (I-144)
    if (an?.hedef_panosu?.olculer) {   // seçili pencerenin hedef dışı ölçüleri
      const w = B.pencere();
      const gizli = olcuGizli();
      Object.entries(an.hedef_panosu.olculer).forEach(([ad, p]) => { if (p[w]?.durum === 'kotu' && !gizli.has(ad + '|' + w)) g.olcu.push({ tur: 'olcu', ad, e: p[w], pencere: w }); });
    }
    return g;
  }
  const gelenSayisi = () => { const g = gelenOgeleri(); return g.karar.length + g.sohbet.length + g.teslim.length + g.sahipsiz.length + g.kart.length + g.olcu.length; };

  // Eklenti güncelleme kartı (ADR-0039): yeni | calisiyor | bitti | hata. Koşu LLM çağırmaz; aynı kod `orkestra update` ile çalışır.
  const kisaSha = s => String(s ?? '').slice(0, 7);
  function guncellemeHtml(gu) {
    const c = gu.kontrol || {}, k = gu.kosu || {};
    const satirlar = (k.satirlar || []).filter(s => String(s).trim());
    if (gu.durum === 'calisiyor') {
      const son = satirlar.length ? satirlar[satirlar.length - 1] : 'Başlatılıyor…';
      return H`<article class="oge oge-guncelleme" data-gez data-guncelleme="calisiyor" aria-busy="true" style="--renk:var(--bilgi)">
        <div class="simge donen">${simge('guncelle')}</div>
        <div class="govde"><div class="baslik">Orkestra güncelleniyor…</div>
          <div class="metin guncelleme-son" role="status" aria-live="polite">${son}</div>
          <div class="meta">${B.sure(k.sure)} · Bu sayfayı kapatsan da güncelleme sürer.</div></div>
        <div class="eylemler"><button class="dugme ana-d kucuk" disabled aria-disabled="true">Güncelleniyor…</button></div></article>`;
    }
    if (gu.durum === 'bitti') {
      return H`<article class="oge oge-guncelleme" data-gez data-guncelleme="bitti" style="--renk:var(--iyi)">
        <div class="simge">${simge('tamam')}</div>
        <div class="govde"><div class="baslik" role="status">Orkestra güncellendi</div>
          <div class="metin">Yeni sürüm yeni oturumda yüklenir: yeni bir oturum aç ya da <code>/reload-plugins</code> yaz.</div>
          <div class="meta">${c.yeni ? H`<span>Sürüm <code>${kisaSha(c.yeni)}</code></span><span>·</span>` : ''}<span>${B.sure(k.sure)} sürdü</span></div></div></article>`;
    }
    if (gu.durum === 'hata') {
      return H`<article class="oge oge-guncelleme" data-gez data-guncelleme="hata" style="--renk:var(--kotu)">
        <div class="simge">${simge('uyari')}</div>
        <div class="govde"><div class="baslik">Güncelleme başarısız</div>
          <div class="metin guncelleme-hata" role="alert">${k.neden || 'Bilinmeyen hata.'}</div>
          ${satirlar.length ? H`<details class="degisiklik"><summary>Koşu çıktısı</summary><pre>${satirlar.join('\n')}</pre></details>` : ''}
          <div class="meta">Aynı işlem terminalde: <code>orkestra update</code></div></div>
        <div class="eylemler"><button class="dugme ana-d kucuk" data-eylem="guncelle">Tekrar dene</button></div></article>`;
    }
    const liste = c.degisiklikler || [], sayi = c.yenilik_say ?? liste.length, fazla = sayi - liste.length;
    return H`<article class="oge oge-guncelleme" data-gez data-guncelleme="yeni" style="--renk:var(--vurgu)">
        <div class="simge">${simge('guncelle')}</div>
        <div class="govde"><div class="baslik">Orkestra güncellemesi var</div>
          <div class="metin">${B.sayi(sayi)} yeni özellik</div>
          ${c.klon_kirli ? H`<div class="meta uyari-satir" role="note">${simge('uyari')}<span>Yayın klonunda commitlenmemiş değişiklik var; güncelleme reddedilebilir.</span></div>` : ''}
          ${liste.length ? H`<details class="degisiklik"><summary>Neler değişti</summary><ul>${liste.map(x => H`<li>${x.konu}</li>`)}${fazla > 0 ? H`<li class="soluk">ve ${B.sayi(fazla)} özellik daha</li>` : ''}</ul></details>` : ''}</div>
        <div class="eylemler"><button class="dugme kucuk" data-eylem="guncelle-ertele" title="Yeni bir sürüm çıkana kadar hatırlatma">Sonra</button> <button class="dugme ana-d kucuk" data-eylem="guncelle">Güncelle</button></div></article>`;
  }

  function ogeHtml(o) {
    if (o.tur === 'guncelleme') return guncellemeHtml(o.g);
    if (o.tur === 'onay') {
      const k = o.k, sec = Array.isArray(k.secenekler) ? k.secenekler : [];
      return H`<article class="oge" data-gez data-onay="${k.id}" style="--renk:var(--vurgu)">
        <div class="simge">${simge('onay')}</div>
        <div class="govde"><div class="yatay"><span class="kimlik">${k.id}</span><span class="etiket">${k.tur}</span>${alanRozeti(k)}</div>
          <div class="baslik">${k.baslik}</div>
          ${k.metin && k.metin !== k.baslik ? H`<div class="metin">${k.metin}</div>` : ''}
          ${k.vaat?.metin ? H`<div class="meta">Beklenen etki: ${k.vaat.metin}</div>` : ''}
          <div class="meta">${B.goreli(k.olusturma)}</div></div>
        <div class="eylemler">${sec.length
          ? H`<div class="secenekler">${sec.map(s => H`<button class="dugme kucuk" data-eylem="karar" data-id="${k.id}" data-alan="${k.alan?.id || ''}" data-sonuc="onay" data-secim="${s}">${s}</button>`)}</div>`
          : H`<button class="dugme ana-d kucuk" data-eylem="karar" data-id="${k.id}" data-alan="${k.alan?.id || ''}" data-sonuc="onay" title="Onayla (a)">Onayla</button>`}
          <button class="dugme kucuk tehlike" data-eylem="karar" data-id="${k.id}" data-alan="${k.alan?.id || ''}" data-sonuc="ret" title="Reddet (r)">Reddet</button></div>
      </article>`;
    }
    if (o.tur === 'uygula') return H`<article class="oge" data-gez style="--renk:var(--bilgi)">
        <div class="simge">${simge('oynat')}</div>
        <div class="govde">${o.alan ? H`<div class="yatay">${alanRozeti(o)}</div>` : ''}<div class="baslik">${o.kosu ? o.n + ' onaylı karar şu an uygulanıyor' : o.n + ' onaylı karar uygulanmayı bekliyor'}</div>
          <div class="metin">${o.kosu ? 'Arka planda, pencere açmadan sürüyor (birkaç dakika); bitince kart kalkar.' : 'Kararlar arka planda, pencere açmadan sırayla uygulanır (komut satırı Claude oturumu gerekir).'}</div></div>
        <div class="eylemler"><button class="dugme ana-d kucuk" data-eylem="uygula" data-alan="${o.alan?.id || ''}" ${o.kosu ? 'disabled' : ''}>${o.kosu ? 'Uygulanıyor…' : 'Şimdi uygula'}</button></div></article>`;
    if (o.tur === 'perspektif') {
      const pd = o.d, gecen = pd.gun_once == null ? 'Perspektif hiç çalışmadı' : `Perspektif ${pd.gun_once} gündür çalışmadı`;
      return H`<article class="oge" data-gez style="--renk:var(--bilgi)">
        <div class="simge">${simge('oynat')}</div>
        <div class="govde">${o.alan ? H`<div class="yatay">${alanRozeti(o)}</div>` : ''}<div class="baslik">${gecen}</div>
          <div class="metin">Son koşudan beri ${B.sayi(pd.oturum_sayaci)} oturum geçti. Perspektif hafıza bakımı ve skill avı yapar; arka planda, pencere açmadan çalışır.</div></div>
        <div class="eylemler"><button class="dugme kucuk" data-eylem="perspektif-yoksay" data-alan="${o.alan?.id || ''}" title="Bir sonraki tetiklemeye kadar sorma">Yoksay</button> <button class="dugme ana-d kucuk" data-eylem="perspektif" data-alan="${o.alan?.id || ''}">Perspektifi başlat</button></div></article>`;
    }
    if (o.tur === 'katman5') return H`<article class="oge" data-gez style="--renk:var(--uyari)">
        <div class="simge">${simge('goz')}</div>
        <div class="govde"><div class="baslik">5 dakikalık önbellek katmanı</div>
          <div class="metin">Son 24 saatte ${B.sayi(o.n)} ana ajan çağrısı 5 dakikalık katmana yazdı. 5 dakikayı aşan her duraksama bağlamı yeniden yazdırır; 1 saatlik katman beklenir.</div></div></article>`;
    if (o.tur === 'etki') return H`<article class="oge" data-gez style="--renk:var(--uyari)">
        <div class="simge">${simge('goz')}</div>
        <div class="govde"><div class="yatay"><span class="kimlik">${o.k.id}</span>${alanRozeti(o.k)}</div><div class="baslik">Etki ölçümü kararını bekliyor</div>
          <div class="metin">${o.k.baslik}</div></div>
        <div class="eylemler"><a class="dugme kucuk" href="/onaylar?alan=${enc(o.k.alan?.id || V.alan)}#etki">Yanıtla</a></div></article>`;
    if (o.tur === 'sohbet') {
      const s = o.o;
      return H`<article class="oge" data-gez style="--renk:var(--uyari)">
        <div class="simge">${simge('sohbet')}</div>
        <div class="govde"><div class="baslik">${s.sohbet || s.kisa}</div>
          ${s.bekleme ? H`<div class="metin">“${s.bekleme}”</div>` : ''}
          <div class="meta"><span>${s.proje}</span><span>·</span><span>${B.goreli(s.son_zaman)}</span>${s.ne ? H`<span>·</span><span>${s.ne}</span>` : ''}</div></div>
        <div class="eylemler">${s.link ? H`<a class="dugme ana-d kucuk" href="${s.link}" data-birincil>Claude'da aç</a>` : ''}</div></article>`;
    }
    if (o.tur === 'kart') {
      const k = o.k, eski = (Date.now() - new Date(k.guncelleme).getTime()) / 864e5;
      const sohbet = k.sahip_arsivli ? null : (k.son_oturum || k.oturum);   // I-145: arşivli sahibe yönlendirme yok
      const ipucu = k.durum === 'onaylandi' ? 'onaylı; teslim: orkestra kart teslim-bekleyen'
        : k.sahip_arsivli ? 'sahibi arşivli sohbet' + (k.is ? '; yeni oturumda: orkestra is devam ' + k.is : '') : '';
      return H`<article class="oge" data-gez${sohbet ? H` data-oturum="${sohbet}" data-ad="${k.baslik}" style="--renk:var(--uyari);cursor:pointer" title="Tıkla: kartı başlatan sohbeti aç"` : H` style="--renk:var(--uyari)"`}>
        <div class="simge">${simge('kart')}</div>
        <div class="govde"><div class="yatay"><span class="kimlik">${k.id}</span><span class="etiket">${k.basamak || ''}</span>${rozet(k.durum)}${alanRozeti(k)}</div>
          <div class="baslik">${k.baslik}</div>
          <div class="meta"><span>${eski >= 1 ? Math.round(eski) + ' gündür hareketsiz' : 'son hareket ' + B.goreli(k.guncelleme)}</span><span>·</span><span>${k.isci ?? 0} işçi çağrısı</span><span>·</span><span>${B.paraP(k)}</span>${ipucu ? H`<span>·</span><span>${ipucu}</span>` : ''}</div></div>
        <div class="eylemler">${sohbet ? H`<button class="dugme ana-d kucuk" data-eylem="sohbet-ac" data-oturum="${sohbet}" data-ad="${k.baslik}" data-birincil>Sohbeti aç</button>` : ''}<a class="dugme kucuk" href="#/kart/${enc(k.id)}${ek('', k)}"${sohbet ? '' : ' data-birincil'}>İzi aç</a></div></article>`;
    }
    if (o.tur === 'olcu') {
      const [ad, f] = OLCU_AD[o.ad] || [o.ad, x => B.sayi(x, 2)];
      const pAd = pencereAd(o.pencere);
      return H`<article class="oge" data-gez style="--renk:var(--kotu)">
        <div class="simge">${simge('hedef')}</div>
        <div class="govde"><div class="baslik">${ad}: ${f(o.e.deger)}</div>
          <div class="meta"><span>Hedef ${o.e.tur === 'ust' ? '≤' : '≥'} ${f(o.e.hedef)}</span><span>·</span><span>${pAd}</span><span>·</span><span>${B.sayi(o.e.ornek)} örnek</span></div></div>
        <div class="eylemler"><a class="dugme kucuk" href="#/maliyet" data-birincil>İncele</a></div></article>`;
    }
    return '';
  }

  function gGelen() {
    const yuk = bekle('/onaylar.json', '/simdi.json', '/ozet.json');
    const g = gelenOgeleri();
    const oz = d('/ozet.json').veri, sm = d('/simdi.json').veri, an = d('/analitik.json').veri, il = d('/isler.json').veri;
    const p = B.pencere(), pw = oz?.maliyet?.pencere?.[p];
    const gun = (an?.trend?.gunluk || []).slice(-14).map(x => B.olcu() === 'token' ? x.token : x.usd);
    const acikIs = (il?.isler || []).filter(i => i.durum === 'acik').length;
    const ust = oz ? H`<div class="karolar">
        ${karo('Harcama · ' + pencereAd(p), pw ? B.para(pw.usd, pw.token) : '–', H`${spark(gun)}<span>son ${gun.length} gün</span>`, '#/maliyet')}
        ${karo('Claude çalışıyor', B.sayi(sm?.sayac?.claude ?? 0), 'sohbet')}
        ${karo('Açık iş', il ? B.sayi(acikIs) : '–', 'İşlere git →', '#/isler')}
        ${karo('Karar bekleyen', B.sayi(g.karar.length), g.karar.length ? 'aşağıda' : 'yok')}
      </div>` : '';
    const toplam = g.karar.length + g.sohbet.length + g.teslim.length + g.sahipsiz.length + g.kart.length + g.olcu.length;
    const grup = (baslik, liste) => liste.length ? H`<section class="gelen-grup"><h2>${baslik} <span class="say">${liste.length}</span></h2>${liste.map(ogeHtml)}</section>` : '';
    const govde = yuk || (toplam === 0
      ? bos('Gelen kutusu boş', 'Senden beklenen bir karar, yanıt ya da müdahale yok.')
      : H`${grup('Karar ver', g.karar)}${grup('Seni bekleyen sohbetler', g.sohbet)}${grup('Teslim bekleyen kartlar', g.teslim)}${grup('Sahipsiz kartlar', g.sahipsiz)}${grup('Takılan kartlar', g.kart)}${grup('Hedef dışı ölçüler', g.olcu)}`);
    const not = tumMu() ? H`<p class="birlesik-not">Hedef dışı ölçüler (oran ve hedef panoları) toplanamaz; tek bir çalışma alanı seçince görünür.</p>` : '';
    return {
      baslik: 'Gelen kutusu',
      govde: H`<div class="icerik yigin" style="max-width:920px">${ust}${govde}${not}</div>`,
    };
  }

  // ================================================================ 6. Görünüm: İşler (liste + ayrıntı)
  const KOVA = [['simdi', 'Şimdi', 'var(--bilgi)'], ['sirada', 'Sırada', 'var(--uyari)'], ['planda_kart_yok', 'Planda', 'var(--notr)'], ['yapildi', 'Yapıldı', 'var(--iyi)'], ['iptal', 'İptal', 'var(--notr)']];

  function gIsler(r) {
    const f = r.q.get('f') || 'acik', q = r.q.get('q') || '';
    const yuk = bekle('/isler.json');
    const tum = d('/isler.json').veri?.isler || [];
    const say = { acik: tum.filter(i => i.durum === 'acik').length, kapandi: tum.filter(i => i.durum === 'kapandi').length, tum: tum.length };
    const liste = tum.filter(i => (f === 'tum' || i.durum === f) && (!q || eslesir(i.id + ' ' + i.ad + ' ' + (i.alan?.ad || ''), q)));
    const sorgu = ek(r.q);   // alan süzgeçlerle taşınmaz; her satır kendi alanını ekler
    const secili = i => i.id === r.id && (!tumMu() || i.alan?.id === rotaAlani(r));
    const satirlar = yuk || (liste.length ? H`<div class="liste" role="listbox" aria-label="İşler">${liste.map(i => {
      const t = i.ilerleme?.toplam || 0, b = i.ilerleme?.biten || 0, surer = (i.kovalar?.simdi || []).length > 0;
      return H`<a class="satir-l" role="option" data-gez href="#/is/${enc(i.id)}${ek(r.q, i)}" aria-selected="${secili(i)}">
        <span class="nokta" style="--renk:${i.durum === 'kapandi' ? 'var(--notr)' : surer ? 'var(--bilgi)' : 'var(--vurgu)'}"></span>
        <span class="kimlik">${i.id}</span>${alanRozeti(i)}<span class="ad" title="${i.ad}">${i.ad}</span>
        <span class="sag">${t ? H`<span class="mini-ilerleme">${ilerleme(b / t, i.durum === 'kapandi' ? 'var(--notr)' : '')}</span>` : ''}<span>${B.paraP(i)}</span><span style="min-width:62px;text-align:right">${B.goreli(i.son)}</span></span></a>`;
    })}</div>` : bos('Eşleşen iş yok', q ? `“${q}” için sonuç yok.` : 'Bu süzgeçte iş yok.', 'ara'));
    const sol = H`<div class="liste-yan" id="isListe" data-kaydir>
      <div class="suzgec">${[['acik', 'Açık'], ['kapandi', 'Kapanan'], ['tum', 'Tümü']].map(([k, ad]) =>
        H`<button class="cip" data-eylem="sorgu" data-k="f" data-v="${k}" aria-pressed="${f === k}">${ad}<span class="say">${say[k]}</span></button>`)}
        <input class="arama" id="isAra" type="search" placeholder="İş ara…  /" value="${q}" data-sorgu="q" aria-label="İş ara"></div>
      ${satirlar}</div>`;
    const sag = H`<section class="ayrinti">${r.id ? isAyrinti(r.id, tum.find(secili)) : bos('Bir iş seç', 'Soldan bir iş seç.', 'isler')}</section>`;
    return {
      baslik: 'İşler', yol: r.id ? H`<a href="#/isler${sorgu}">İşler</a> / <span class="kimlik">${r.id}</span>` : null,
      govde: H`<div class="bolunmus${r.id ? ' secili' : ''}">${sol}${sag}</div>`, tam: true,
    };
  }

  function isAyrinti(id, i) {
    if (!i) return d('/isler.json').veri ? bos('İş bulunamadı', id + ' bu çalışma alanında yok.', 'uyari') : iskelet();
    const t = i.ilerleme?.toplam || 0, b = i.ilerleme?.biten || 0;
    const tk = d(`/teknik.json?is=${enc(id)}`), td = d(`/api/todo?is=${enc(id)}`);
    const kartlar = tk.veri?.kartlar || [];
    const kovalar = H`<div class="kovalar">${KOVA.filter(([k]) => (i.kovalar?.[k] || []).length).map(([k, ad, renk]) => {
      const l = i.kovalar[k];
      const oge = e => e.tur === 'kart'
        ? H`<a class="k" href="#/kart/${enc(e.kart)}${ek('', i)}"><span class="yatay"><span class="kimlik">${e.kart}</span>${e.basamak ? H`<span class="etiket">${e.basamak}</span>` : ''}<span class="soluk kucuk-y" style="margin-left:auto">${B.paraP(e)}</span></span><span>${kisalt(e.metin, 120)}</span></a>`
        : H`<div class="k"><span>${kisalt(e.metin, 160)}</span>${e.bolum ? H`<span class="soluk kucuk-y">${e.bolum}</span>` : ''}</div>`;
      return H`<div class="kova"><h3><span class="nokta" style="--renk:${renk}"></span>${ad}<span class="soluk">${l.length}</span></h3>
        ${l.slice(0, 6).map(oge)}${l.length > 6 ? H`<details class="ac"><summary>${l.length - 6} daha</summary><div class="yigin sik" style="margin-top:6px">${l.slice(6).map(oge)}</div></details>` : ''}</div>`;
    })}</div>`;
    const kartTablo = tk.hata && !tk.veri ? hataKutu(tk.hata, `/teknik.json?is=${enc(id)}`) : !tk.veri ? iskelet(3, 32) : kartlar.length ? H`<div class="tablo-kap"><table class="tablo">
      <thead><tr><th>Kart</th><th>Başlık</th><th class="gizle-dar">Sınıf</th><th>Basamak</th><th>Durum</th><th class="gizle-dar">Denetim</th><th class="sayi gizle-dar">Süre</th><th class="sayi">${B.birim()}</th></tr></thead>
      <tbody>${kartlar.map(k => H`<tr class="tik" data-git="#/kart/${enc(k.id)}${ek('', i)}"><td><span class="kimlik">${k.id}</span></td><td class="kirp" title="${k.baslik}">${k.baslik}</td>
        <td class="gizle-dar soluk">${k.sinif || '–'}</td><td><span class="etiket">${k.basamak || '–'}</span></td><td>${rozet(k.durum)}</td>
        <td class="gizle-dar">${k.denetim ? rozet(k.denetim) : H`<span class="soluk">–</span>`}</td><td class="sayi gizle-dar">${B.sure(k.sure)}</td><td class="sayi">${B.paraP(k)}</td></tr>`)}</tbody></table></div>`
      : H`<p class="soluk" style="padding:0 var(--a4) var(--a3)">Bu işte kart yok.</p>`;
    const acikM = td.veri?.acik_maddeler || [], bitenM = td.veri?.biten_maddeler || [];
    const todo = td.veri ? (acikM.length + bitenM.length ? H`<ul class="todo">${acikM.map(m => H`<li><span class="kutu"></span><span>${m}</span></li>`)}</ul>
      ${bitenM.length ? H`<details class="ac" style="margin-top:8px"><summary>${bitenM.length} biten madde</summary><ul class="todo" style="margin-top:6px">${bitenM.map(m => H`<li class="bitti"><span class="kutu"></span><span>${m}</span></li>`)}</ul></details>` : ''}`
      : H`<p class="soluk">Todo yok.</p>`) : td.hata ? hataKutu(td.hata) : iskelet(3, 18);
    return H`<div class="yigin">
      <div class="yigin sik"><div class="yatay"><span class="kimlik">${i.id}</span>${alanRozeti(i)}${rozet(i.durum)}${(i.kovalar?.simdi || []).length ? rozet('suruyor') : ''}</div>
        <h1>${i.ad}</h1>
        ${i.klasor ? H`<div class="yatay soluk kucuk-y"><code title="${i.klasor}">${yolKisa(i.klasor)}</code><button class="dugme hayalet kucuk" data-eylem="kopyala" data-metin="${i.klasor}">Yolu kopyala</button></div>` : ''}
        ${i.durum === 'acik' && t - b <= 0 ? H`<div class="yatay"><button class="dugme kucuk" data-eylem="is-kapat" data-is="${i.id}" data-alan="${i.alan?.id || ''}" title="Açık todo maddesi yok; kapanış kapıları (çalışma özeti, ADR) denetlenir">İşi kapat</button></div>` : ''}</div>
      <div class="karolar">${karo('İlerleme', t ? B.yuzde(b / t) : '–', t ? H`${b} / ${t} madde` : 'madde yok')}
        ${karo('Harcama', B.paraP(i), pencereAd(B.pencere()) + ' · ' + B.birim())}
        ${karo('Kart', B.sayi(kartlar.length || Object.values(i.kovalar || {}).flat().filter(e => e.tur === 'kart').length), 'oluşturma sırasıyla aşağıda')}
        ${karo('Son etkinlik', B.goreli(i.son), B.tarih(i.son))}</div>
      ${t ? ilerleme(b / t) : ''}
      ${kovalar}
      <section class="kart"><div class="kart-bas"><h2>Kartlar</h2><span class="soluk kucuk-y">satıra tıkla: koşu izi</span></div><div class="kart-ic" style="padding:0 0 4px">${kartTablo}</div></section>
      <section class="kart"><div class="kart-bas"><h2>Yapılacaklar</h2><span class="soluk kucuk-y">todo.md</span></div><div class="kart-ic">${todo}</div></section>
    </div>`;
  }

  // ================================================================ 7. Görünüm: Koşular
  function gKosular(r) {
    const yuk = bekle('/analitik.json');
    const an = d('/analitik.json').veri, p = B.pencere();
    const bs = r.q.get('b') || '', du = r.q.get('d') || '', s = r.q.get('s') || 'yeni', q = r.q.get('q') || '';
    // pencere: kartın oluşturma günü seçili pencerede (sunucu 'penceresi' listesini verir); maliyet de pencerede kalan harcama
    let l = (an?.akis?.kartlar || []).filter(k => (k.penceresi || []).includes(p));
    const basamaklar = [...new Set(l.map(k => k.basamak).filter(Boolean))].sort();
    const durumlar = [...new Set(l.map(k => k.durum).filter(Boolean))].sort();
    l = l.filter(k => (!bs || k.basamak === bs) && (!du || k.durum === du) && (!q || eslesir(k.id + ' ' + k.baslik + ' ' + (k.alan?.ad || ''), q)));
    const sirala = { yeni: (a, b) => String(b.olusturma).localeCompare(String(a.olusturma)), sure: (a, b) => (b.toplam_dk || 0) - (a.toplam_dk || 0), kuyruk: (a, b) => (b.kuyruk_dk || 0) - (a.kuyruk_dk || 0) };
    l.sort(sirala[s] || sirala.yeni);
    const mx = Math.max(1, ...l.map(k => k.toplam_dk || 0));
    // toplam süre üç aşamadan uzunsa fark turlar arası beklemedir (ana ajanın yeniden çağırması, kullanıcı)
    const ara = k => Math.max(0, (k.toplam_dk || 0) - (k.kuyruk_dk || 0) - (k.is_dk || 0) - (k.denetim_toplam_dk || 0));
    const oz = an?.pencere?.[p]?.akis_ozet || {};
    const DARBOGAZ = { is: 'işçi çalışması', kuyruk: 'kuyruk', denetim: 'denetim' };
    const cip = (k, v, ad) => H`<button class="cip" data-eylem="sorgu" data-k="${k}" data-v="${v}" aria-pressed="${(r.q.get(k) || '') === v}">${ad}</button>`;
    const govde = yuk || H`
      <div class="karolar">${karo('Kart', B.sayi(oz.kart), 'süre verisi olan')}${karo('Medyan toplam süre', B.sure((oz.toplam_medyan || 0) * 60), 'ortalama ' + B.sure((oz.toplam_ort || 0) * 60))}
        ${karo('Medyan kuyruk', B.sure((oz.kuyruk_medyan || 0) * 60), `${oz.kuyruk_uzun ?? 0} kart ${oz.uzun_esik_dk ?? 30} dk üstü`)}
        ${karo('Darboğaz', DARBOGAZ[oz.darbogaz] || oz.darbogaz || '–', 'ortalamada en uzun aşama')}</div>
      <section class="kart">
        <div class="suzgec">${cip('b', '', 'Tüm basamaklar')}${basamaklar.map(b => cip('b', b, b))}<span class="soluk">|</span>${cip('d', '', 'Tüm durumlar')}${durumlar.map(x => cip('d', x, (DURUM[x] || [x])[0]))}
          <input class="arama" id="kosuAra" type="search" placeholder="Kart ara…  /" value="${q}" data-sorgu="q" aria-label="Kart ara"></div>
        <div class="suzgec" style="border-bottom:0;padding-bottom:0"><span class="soluk kucuk-y">Sırala:</span>${cip('s', 'yeni', 'En yeni')}${cip('s', 'sure', 'En uzun')}${cip('s', 'kuyruk', 'En uzun kuyruk')}
          <span class="lejant" style="margin-left:auto"><span><i style="--renk:var(--seri-5)"></i>Kuyruk</span><span><i style="--renk:var(--seri-1)"></i>İş</span><span><i style="--renk:var(--seri-3)"></i>Denetim</span><span><i style="--renk:var(--cizgi-guclu)"></i>Turlar arası</span></span></div>
        <div class="tablo-kap"><table class="tablo"><thead><tr><th>Kart</th><th>Başlık</th><th>Basamak</th><th>Durum</th><th>Süre dağılımı</th><th class="sayi">Toplam</th><th class="sayi gizle-dar">${B.birim()}</th><th class="gizle-dar gizle-orta">Oluşturma</th></tr></thead>
        <tbody>${l.slice(0, 300).map(k => {
          const w = x => ((x || 0) / mx * 120).toFixed(1);
          return H`<tr class="tik" data-gez data-git="#/kart/${enc(k.id)}${ek('', k)}"><td><span class="kimlik">${k.id}</span>${alanRozeti(k)}</td><td class="kirp" title="${k.baslik}">${k.baslik}</td><td><span class="etiket">${k.basamak || '–'}</span></td><td>${rozet(k.durum)}</td>
            <td><span class="mini-serit" title="Kuyruk ${B.sure(k.kuyruk_dk * 60)} · İş ${B.sure(k.is_dk * 60)} · Denetim ${B.sure(k.denetim_toplam_dk * 60)} · Turlar arası ${B.sure(ara(k) * 60)}"><i style="width:${w(k.kuyruk_dk)}px;background:var(--seri-5)"></i><i style="width:${w(k.is_dk)}px;background:var(--seri-1)"></i><i style="width:${w(k.denetim_toplam_dk)}px;background:var(--seri-3)"></i><i style="width:${w(ara(k))}px;background:var(--cizgi-guclu)"></i></span></td>
            <td class="sayi">${B.sure((k.toplam_dk || 0) * 60)}</td><td class="sayi gizle-dar">${B.paraP(k)}</td><td class="gizle-dar gizle-orta soluk">${B.tarih(k.olusturma)}</td></tr>`;
        })}</tbody></table></div>
        ${l.length ? '' : bos(q || bs || du ? 'Eşleşen kart yok' : 'Bu pencerede kart yok', q || bs || du ? 'Süzgeçleri gevşet.' : pencereAd(p) + ' içinde oluşturulan kart yok; üstten pencereyi genişlet.', 'ara')}
      </section>`;
    return { baslik: 'Koşular', sag: H`<span class="soluk kucuk-y">${l.length} kart · ${pencereAd(p)}</span>`, govde: H`<div class="icerik yigin">${govde}</div>` };
  }

  // ================================================================ 8. Görünüm: Kart koşu izi
  const birimDeger = o => (B.olcu() === 'token' ? o.token : o.usd) || 0;   // seçili birimin ham sayısı (çubuk genişliği, sıralama)
  const kSatirlari = l => (l || []).flatMap(s => String(s).split(/\s(?=K\d+:)/)).map(s => s.trim()).filter(Boolean);
  const kriterler = l => (l || []).flatMap(x => { if (typeof x === 'string' && x.trim().startsWith('[')) { try { return JSON.parse(x); } catch (e) { /* düz metin */ } } return [x]; });

  function gKart(r) {
    const yol = `/teknik.json?kart=${enc(r.id)}`;
    const yuk = bekle(yol);
    const t = d(yol).veri || {};
    const kAlan = rotaAlani(r);
    const kObj = tumMu() && kAlan ? { alan: { id: kAlan, ad: alanAd(kAlan) } } : null;
    const bilgi = kartBilgi(r.id, kAlan);
    const ms = t.maliyet_sure || {}, sr = ms.sureler || {};
    const dg = t.dogrulama || {};
    const denetimler = dg.denetimler || [], testler = dg.test_kosulari || [], onk = dg.onkontrol_kosulari || [];
    const durum = bilgi.durum || (denetimler.length && denetimler[denetimler.length - 1].karar === 'onay' ? 'teslim' : null);
    const isId = t.neden?.is;
    const topSure = (sr.kuyruk_sn || 0) + (sr.is_sn || 0) + (sr.denetim_sn || 0);
    const yuzde = x => topSure ? Math.max(0.5, (x || 0) / topSure * 100) : 0;
    const retS = denetimler.filter(x => x.karar === 'ret').length;
    const isciler = (ms.maliyet || []).filter(m => /isci|general/.test(m.ajan));
    const denetciler = (ms.maliyet || []).filter(m => /denetci/.test(m.ajan));
    const dosyalar = t.degisen?.dosyalar || [];
    const fmx = Math.max(1, ...dosyalar.map(f => (f.ekle || 0) + (f.sil || 0)));
    const adim = (renk, s, baslik, ek, govde) => H`<li><div class="dugum" style="--renk:${renk}">${simge(s)}</div><div class="adim"><div class="ust"><b>${baslik}</b>${ek || ''}</div>${govde || ''}</div></li>`;
    const modelSat = l => l.map(m => H`<span class="soluk kucuk-y">${m.ajan.replace('orkestra:', '')} · ${String(m.model).replace('claude-', '')} · ${B.para(m.usd, m.token)}</span>`);
    const iz = H`<ol class="iz">
      ${adim('var(--notr)', 'saat', 'Kuyruk', H`<span class="soluk kucuk-y">${B.sure(sr.kuyruk_sn)}</span>`, H`<span class="soluk kucuk-y">${bilgi.olusturma ? 'Oluşturma ' + B.tarih(bilgi.olusturma) : ''}</span>`)}
      ${adim('var(--seri-1)', 'oynat', 'İşçi çalıştı', H`<span class="etiket">${t.ne?.basamak || bilgi.basamak || '–'}</span><span class="soluk kucuk-y">${B.sure(sr.is_sn)}</span>`, H`<div class="yigin sik">${modelSat(isciler)}</div>`)}
      ${onk.length ? adim(onk.every(x => x.gecti) ? 'var(--iyi)' : 'var(--kotu)', 'kalkan', 'Ön kontrol', H`${onk.map(x => rozet(x.gecti ? 'iyi' : 'kotu', x.gecti ? 'Geçti' : 'Kaldı'))}`,
        H`${onk.filter(x => (x.ihlal_turleri || []).length).map(x => H`<span class="soluk kucuk-y">İhlal: ${x.ihlal_turleri.join(', ')}</span>`)}`) : ''}
      ${testler.length ? adim(testler[testler.length - 1].gecti ? 'var(--iyi)' : 'var(--kotu)', 'test', 'Test koşuları', H`<span class="soluk kucuk-y">${testler.length} koşu · ${testler.filter(x => x.gecti).length} geçti</span>`,
        H`<div class="yatay">${testler.map(x => H`<span class="rozet ${x.gecti ? 'r-iyi' : 'r-kotu'}" title="${B.tarih(x.zaman)} · çıkış ${x.cikis_kodu}">${x.asama || 'test'}</span>`)}</div>`) : ''}
      ${denetimler.map((x, i) => adim(x.karar === 'onay' ? 'var(--iyi)' : 'var(--kotu)', x.karar === 'onay' ? 'tamam' : 'carpi', `Denetim ${i + 1}`,
        H`${rozet(x.karar)}${x.neden ? H`<span class="etiket">${x.neden}</span>` : ''}`,
        kSatirlari(x.k_satirlari).length ? H`<details class="ac"><summary>${kSatirlari(x.k_satirlari).length} kriter satırı</summary><div class="yigin sik" style="margin-top:6px">${kSatirlari(x.k_satirlari).map(k => H`<div class="k-satir">${k}</div>`)}</div></details>` : ''))}
      ${denetciler.length ? H`<li><div class="dugum" style="--renk:var(--seri-3)">${simge('goz')}</div><div class="adim"><div class="ust"><b>Denetçi maliyeti</b><span class="soluk kucuk-y">${B.sure(sr.denetim_sn)}</span></div><div class="yigin sik">${modelSat(denetciler)}</div></div></li>` : ''}
      ${durum === 'teslim' ? adim('var(--iyi)', 'tamam', 'Teslim edildi', '', '') : durum ? adim('var(--uyari)', 'saat', (DURUM[durum] || [durum])[0], '', '') : ''}
    </ol>`;
    const ders = t.ogrenilen?.ret_dersleri || [], risk = t.ogrenilen?.riskler || [];
    const govde = yuk || H`<div class="yigin">
      <div class="yigin sik"><div class="yatay"><span class="kimlik">${r.id}</span>${alanRozeti(kObj)}${t.ne?.sinif && t.ne.sinif !== '-' ? H`<span class="etiket">${t.ne.sinif}</span>` : ''}${durum ? rozet(durum) : ''}${isId ? H`<a class="baglanti kucuk-y" href="#/is/${enc(isId)}${ek('', kObj)}">${isId} işine git →</a>` : ''}</div>
        <h1>${t.ne?.baslik || bilgi.baslik || r.id}</h1></div>
      <div class="karolar">${karo('Toplam süre', B.sure(topSure), 'kuyruk + iş + denetim')}${karo('Maliyet', B.para(ms.toplam_usd, ms.toplam_token), `${(ms.maliyet || []).length} ajan koşusu`)}
        ${karo('Denetim', `${denetimler.length}`, retS ? `${retS} ret` : 'ret yok')}${karo('Değişen dosya', B.sayi(dosyalar.length), dosyalar.length ? `+${dosyalar.reduce((a, f) => a + (f.ekle || 0), 0)} −${dosyalar.reduce((a, f) => a + (f.sil || 0), 0)} satır` : '–')}</div>
      ${topSure ? H`<div class="serit" role="img" aria-label="Süre dağılımı"><div class="s-kuyruk" style="width:${yuzde(sr.kuyruk_sn)}%">Kuyruk ${B.sure(sr.kuyruk_sn)}</div><div class="s-is" style="width:${yuzde(sr.is_sn)}%">İş ${B.sure(sr.is_sn)}</div><div class="s-denetim" style="width:${yuzde(sr.denetim_sn)}%">Denetim ${B.sure(sr.denetim_sn)}</div></div>` : ''}
      <div class="izgara iki" style="align-items:start">
        <section class="kart"><div class="kart-bas"><h2>Koşu izi</h2></div><div class="kart-ic">${iz}</div></section>
        <div class="yigin">
          <section class="kart"><div class="kart-bas"><h2>Kabul kriterleri</h2></div><div class="kart-ic">${kriterler(t.ne?.kabul_kriterleri).length ? H`<ul class="todo">${kriterler(t.ne.kabul_kriterleri).map(k => H`<li><span class="kutu" style="${durum === 'teslim' ? 'background:var(--iyi);border-color:var(--iyi)' : ''}"></span><span>${k}</span></li>`)}</ul>` : H`<p class="soluk">Kriter kaydı yok.</p>`}</div></section>
          <section class="kart"><div class="kart-bas"><h2>Maliyet</h2><span class="bosluk"></span><b class="sayi">${B.para(ms.toplam_usd, ms.toplam_token)}</b></div><div class="kart-ic">${(ms.maliyet || []).length ? (ms.maliyet || []).map(m => H`<div class="cubuk-l"><span title="${m.model}">${m.ajan.replace('orkestra:', '')}</span><span class="yol"><i style="width:${(birimDeger(m) / (birimDeger({ usd: ms.toplam_usd, token: ms.toplam_token }) || 1) * 100).toFixed(1)}%;--renk:${/denetci/.test(m.ajan) ? 'var(--seri-3)' : 'var(--seri-1)'}"></i></span><span class="d">${B.para(m.usd, m.token)}</span></div>`) : H`<p class="soluk">Maliyet kaydı yok.</p>`}</div></section>
          <section class="kart"><div class="kart-bas"><h2>Değişen dosyalar</h2><span class="soluk kucuk-y">${t.degisen?.kaynak || ''}</span></div><div class="kart-ic">${dosyalar.length ? dosyalar.map(f => H`<div class="dosya-s"><code title="${f.dosya}">${yolKisa(f.dosya)}</code><span class="sayi kucuk-y"><span style="color:var(--iyi)">+${f.ekle ?? 0}</span> <span style="color:var(--kotu)">−${f.sil ?? 0}</span></span><span class="fark" style="width:${(((f.ekle || 0) + (f.sil || 0)) / fmx * 80).toFixed(0)}px"><i class="e" style="flex:${f.ekle || 0}"></i><i class="s" style="flex:${f.sil || 0}"></i></span></div>`) : (t.ne?.ciktilar || []).length ? H`<div class="yigin sik">${t.ne.ciktilar.map(c => H`<code class="kucuk-y" title="${c}">${yolKisa(c)}</code>`)}</div><p class="soluk kucuk-y" style="margin-top:6px">Git farkı yok; planlanan çıktılar gösteriliyor.</p>` : H`<p class="soluk">Dosya kaydı yok.</p>`}</div></section>
          ${ders.length || risk.length ? H`<section class="kart"><div class="kart-bas"><h2>Öğrenilen</h2></div><div class="kart-ic yigin sik">${ders.map(x => H`<div class="k-satir"><b>${x.neden}</b> (denetim ${x.sira}): ${kisalt(x.talimat, 400)}</div>`)}${risk.map(x => H`<div class="k-satir">${typeof x === 'string' ? x : JSON.stringify(x)}</div>`)}</div></section>` : ''}
          ${t.nasil?.teknik ? H`<section class="kart"><div class="kart-bas"><h2>Teknik not</h2></div><div class="kart-ic" style="white-space:pre-wrap;font-size:13px">${typeof t.nasil.teknik === 'string' ? t.nasil.teknik : JSON.stringify(t.nasil.teknik, null, 2)}</div></section>` : ''}
        </div></div>
      ${(t.eksik || []).length ? H`<p class="soluk kucuk-y">Kayıtta eksik bloklar: ${t.eksik.join(', ')}.</p>` : ''}
    </div>`;
    return {
      baslik: r.id, yol: H`${isId ? H`<a href="#/is/${enc(isId)}">${isId}</a> / ` : H`<a href="#/kosular">Koşular</a> / `}<span class="kimlik">${r.id}</span>`,
      sag: H`${bilgi.oturum ? H`<button class="dugme ana-d kucuk" data-eylem="sohbet-ac" data-oturum="${bilgi.oturum}" data-ad="${bilgi.baslik || r.id}">Sohbeti aç</button> ` : ''}<a class="dugme hayalet kucuk" href="/teknik?alan=${enc(kAlan || gercekAlan())}&is=${enc(isId || '')}&kart=${enc(r.id)}">Klasik teknik görünüm</a>`,
      govde: H`<div class="icerik">${govde}</div>`,
    };
  }

  // ================================================================ 9. Görünüm: Maliyet
  const MODEL_RENK = ['var(--seri-1)', 'var(--seri-2)', 'var(--seri-3)', 'var(--seri-4)', 'var(--seri-5)'];
  const modelDegerleri = g => (B.olcu() === 'token' ? g.model_token : g.model) || {};
  // model → renk: dilim toplamına göre sıralı, grafik ve çubuklarda aynı
  function modelRenkleri(dilim) {
    const top = {};
    dilim.forEach(g => Object.entries(modelDegerleri(g)).forEach(([m, v]) => { top[m] = (top[m] || 0) + v; }));
    const sirali = Object.entries(top).sort((a, b) => b[1] - a[1]);
    return Object.fromEntries(sirali.map(([m], j) => [m, MODEL_RENK[j % MODEL_RENK.length]]));
  }
  // dilim: Bugün için 24 saatlik, diğer pencereler için günlük kayıtlar; değerler seçili birimdedir
  function dilimGrafik(dilim, renk, saatlik, pAd) {
    if (!dilim.length) return bos('Harcama kaydı yok', '', 'maliyet');
    const modeller = Object.keys(renk).filter(m => dilim.some(g => modelDegerleri(g)[m]));
    const W = 720, Hh = 200, sol = 48, alt = 22, ust = 8;
    const mx = Math.max(...dilim.map(birimDeger)) || 1;
    const us = Math.pow(10, Math.floor(Math.log10(mx)));
    const adimY = us * (mx / us > 5 ? 2 : 1);
    const tavan = Math.ceil(mx / adimY) * adimY;
    const bw = (W - sol) / dilim.length, cg = Math.min(36, bw * 0.7);
    const y = v => ust + (Hh - ust - alt) * (1 - v / tavan);
    let s = '';
    for (let v = 0; v <= tavan + 1e-9; v += adimY) s += `<line class="eksen" x1="${sol}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><text x="${sol - 6}" y="${y(v) + 4}" text-anchor="end">${esc(B.para(v, v))}</text>`;
    dilim.forEach((g, i) => {
      const x = sol + i * bw + (bw - cg) / 2;
      let taban = 0;
      const etiket = saatlik ? g.donem + ':00' : g.donem;
      const ipucu = `${etiket}: ${B.para(g.usd, g.token)}\n` + modeller.map(m => `${m}: ${B.para(modelDegerleri(g)[m] || 0, modelDegerleri(g)[m] || 0)}`).join('\n');
      s += `<g class="ipucu-alan"><title>${esc(ipucu)}</title>`;
      modeller.forEach(m => {
        const v = modelDegerleri(g)[m] || 0;
        if (v <= 0) return;
        s += `<rect class="c" x="${x.toFixed(1)}" y="${y(taban + v).toFixed(1)}" width="${cg.toFixed(1)}" height="${(y(taban) - y(taban + v)).toFixed(1)}" rx="2" fill="${renk[m]}"/>`;
        taban += v;
      });
      s += `</g>`;
      const goster = saatlik ? i % 3 === 0 : dilim.length <= 16 || i % Math.ceil(dilim.length / 12) === 0;
      if (goster) s += `<text x="${(x + cg / 2).toFixed(1)}" y="${Hh - 6}" text-anchor="middle">${esc(saatlik ? g.donem : String(g.donem).slice(5).replace('-', '.'))}</text>`;
    });
    return H`<svg class="grafik" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${pAd}: ${saatlik ? 'saatlik' : 'günlük'} harcama, modele göre, ${B.birim()}">${ham(s)}</svg>
      <div class="lejant">${modeller.map(m => H`<span><i style="--renk:${renk[m]}"></i>${m}</span>`)}</div>`;
  }
  function gosterge(ad, e, f, ek = {}) {
    if (!e || e.durum === 'veri-yok' || e.deger == null) return H`<div class="gosterge"><div class="ust"><span class="ad">${ad}</span><span class="d soluk">–</span></div><div class="ray-g"></div><div class="alt"><span>veri yok</span><span>hedef ${e?.tur === 'alt' ? '≥' : '≤'} ${f(e?.hedef)}</span></div></div>`;
    const kayan = ek.kayan && ek.kayan.payda ? H`<div class="alt"><span>son ${B.sayi(ek.kayan.n)} karar ${f(ek.kayan.deger)}</span><span>${B.sayi(ek.kayan.pay)} / ${B.sayi(ek.kayan.payda)} ret</span></div>` : '';
    const mutlak = ek.usd ? H`<span>${B.usdSabit(e.pay)} / ${B.usdSabit(e.payda)}</span>` : '';
    if (e.durum === 'yetersiz-ornek') return H`<div class="gosterge"><div class="ust"><span class="ad">${ad}</span>${rozet(e.durum)}<span class="d soluk">${f(e.deger)}</span></div><div class="ray-g"></div>
      <div class="alt"><span>${B.sayi(e.ornek)} örnek · en az ${B.sayi(ek.asgari)} gerekir</span><span>hedef ${e.tur === 'alt' ? '≥' : '≤'} ${f(e.hedef)}</span></div>${kayan}</div>`;
    const ust = Math.max(e.hedef * 2, e.deger * 1.1) || 1;
    const p = v => Math.max(0, Math.min(100, v / ust * 100));
    const bolge = e.tur === 'ust' ? `left:0;width:${p(e.hedef)}%` : `left:${p(e.hedef)}%;right:0`;
    const renk = e.durum === 'iyi' ? 'var(--iyi)' : e.durum === 'uyari' ? 'var(--uyari)' : 'var(--kotu)';
    return H`<div class="gosterge"><div class="ust"><span class="ad">${ad}</span>${rozet(e.durum)}<span class="d">${f(e.deger)}</span></div>
      <div class="ray-g" role="img" aria-label="${ad}: ${f(e.deger)}, hedef ${f(e.hedef)}"><div class="bolge" style="${bolge}"></div><div class="hedef" style="left:${p(e.hedef)}%"></div><div class="isaret" style="left:${p(e.deger)}%;--renk:${renk}"></div></div>
      <div class="alt"><span>${B.sayi(e.ornek)} örnek</span>${mutlak}<span>hedef ${e.tur === 'ust' ? '≤' : '≥'} ${f(e.hedef)}</span></div>${kayan}</div>`;
  }
  // Önbellek kaçakları (I-144): önceki bağlamın okunmayıp yeniden yazıldığı çağrılar; yalnız gösterir. Pencereden bağımsız, son 7 gün.
  const KACAK_AD = { katman_5dk: '5 dakikalık katman', model: 'Model değişimi', bosluk: '60 dakika ve üstü duraksama', sikistirma: 'Bağlam sıkıştırma', diger: 'Diğer' };
  function onbellekKarti(ob) {
    if (!ob) return '';
    const sat = Object.entries(ob.siniflar || {}).filter(([, v]) => v.olay > 0);
    const olay = (l, ad) => l.length ? H`<details class="ac"><summary>${ad}: en pahalı ${B.sayi(l.length)} olay</summary><div class="tablo-kap"><table class="tablo"><thead><tr><th>Zaman</th><th class="sayi">Boşluk dk</th><th class="sayi">Önceki bağlam</th><th class="sayi">Yazma</th><th>Model</th></tr></thead>
      <tbody>${l.map(e => H`<tr><td>${B.goreli(e.zaman)}</td><td class="sayi">${B.sayi(e.bosluk_dk)}</td><td class="sayi">${B.sayi(Math.round(e.onceki_baglam / 1000))} bin</td><td class="sayi">${B.usdSabit(e.usd)}</td><td>${e.model_once === e.model ? e.model : e.model_once + ' → ' + e.model}</td></tr>`)}</tbody></table></div></details>` : '';
    return H`<section class="kart"><div class="kart-bas"><h2>Önbellek kaçakları</h2><span class="soluk kucuk-y">son ${B.sayi(ob.gun)} gün · pencereden bağımsız · ${B.sayi(ob.olay_sayisi)} olay, ${B.usdSabit(ob.usd)} yazma maliyeti</span></div>
      <div class="kart-ic yigin">${sat.length ? H`<div class="tablo-kap"><table class="tablo"><thead><tr><th>Sınıf</th><th class="sayi">Olay</th><th class="sayi">Yazma maliyeti</th></tr></thead>
        <tbody>${sat.map(([k, v]) => H`<tr><td>${KACAK_AD[k] || k}</td><td class="sayi">${B.sayi(v.olay)}</td><td class="sayi">${B.usdSabit(v.usd)}</td></tr>`)}</tbody></table></div>` : H`<p class="soluk">Son ${B.sayi(ob.gun)} günde kaçak yok.</p>`}
        ${olay(ob.model_olaylari || [], KACAK_AD.model)}${olay(ob.bosluk_olaylari || [], KACAK_AD.bosluk)}
        <p class="soluk kucuk-y">Kaçak: önceki bağlamın yarısından azı okunup 40 bin tokenden fazlası yazılan çağrı. Aynı sayılar: <code>orkestra onbellek kacak --gun 7</code>.</p></div></section>`;
  }
  // Sayfadaki her değer üstteki pencere ve birim seçimini izler; yalnız "ay sonu tahmini" pencereden bağımsızdır ve öyle etiketlenir.
  function gMaliyet() {
    const yuk = bekle('/analitik.json', '/ozet.json');
    const an = d('/analitik.json').veri || {}, oz = d('/ozet.json').veri || {};
    const p = B.pencere(), tok = B.olcu() === 'token', ad = pencereAd(p);
    const pw = oz.maliyet?.pencere?.[p] || {}, ap = an.pencere?.[p] || {}, hp = an.hedef_panosu || {}, olc = hp.olculer || {}, israf = hp.israf?.[p];
    const tr = an.trend || {}, ay = tr.ay_sonu || {}, gun = tr.gunluk || [];
    const dilim = { bugun: tr.saatlik || [], son_3_gun: gun.slice(-3), son_7_gun: gun.slice(-7), bu_ay: gun.slice(-(ay.gecen_gun || gun.length)), tum_zaman: gun }[p] || [];
    const modelRenk = modelRenkleri(dilim);
    const modelL = Object.entries((tok ? pw.model_token : pw.model) || {}).sort((a, b) => b[1] - a[1]);
    const surec = Object.entries((tok ? pw.surec_token : pw.surec) || {}).sort((a, b) => b[1] - a[1]);
    const pahali = (tok ? ap.en_pahali_token : ap.en_pahali) || [];
    const mx = l => Math.max(1, ...l.map(x => x[1]));
    const onc = pw.onceki, fark = onc && birimDeger(onc) ? birimDeger(pw) / birimDeger(onc) - 1 : null;
    const bu = ap.birim || {};
    const bos0 = `${ad} içinde harcama yok.`;
    const tm = tumMu();
    const eksikAy = (ay.tahmin_eksik_alanlar || []).join(', ');
    const hedefler = tm ? H`<p class="birlesik-not">Hedefler, oranlar ve basamak verimi toplanamaz; tek bir çalışma alanı seçince görünür. Harcama, model, süreç ve en pahalı kartlar tüm orkestralı alanlar için toplanmıştır.</p>`
      : H`<section><div class="bolum-bas"><h2>Hedefler</h2><span class="aciklama">işaret = değer, kesik çizgi = hedef, yeşil bölge = kabul edilen aralık</span><span class="bosluk"></span><span class="soluk kucuk-y">${ad}</span></div>
        <div class="karolar" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">${Object.entries(OLCU_AD).map(([k, [adi, f]]) => gosterge(adi, olc[k]?.[p], f, { asgari: hp.asgari_ornek?.[k], usd: k === 'ana_ajan_payi', kayan: k === 'ret_orani' ? hp.ret_son_kararlar : null }))}</div></section>`;
    const govde = yuk || H`
      <div class="karolar">${karo('Harcama · ' + ad, B.para(pw.usd, pw.token), fark == null ? 'önceki dönem verisi yok' : `${fark >= 0 ? '↑' : '↓'} ${B.yuzde(Math.abs(fark))} önceki döneme göre`)}
        ${karo('Günlük ortalama', pw.gun ? B.para(pw.usd / pw.gun, pw.token / pw.gun) : '–', pw.gun ? `${B.sayi(pw.gun)} günlük veri` : '')}
        ${karo('Ay sonu tahmini', ay.tahmin_yeterli ? B.para(ay.tahmin_ort, ay.token?.tahmin_ort) : '–', ay.tahmin_yeterli ? (eksikAy ? `yalnız veri yeten alanlar; eksik: ${eksikAy}` : 'pencereden bağımsız') : `${ay.veri_gun ?? '–'} günlük veri`)}
        ${karo('Kart başı (medyan)', tm ? '–' : B.para(bu.kart_medyan, bu.kart_medyan_token), tm ? `${B.sayi(bu.teslim_kart)} teslim · oran toplanamaz` : `ortalama ${B.para(bu.kart_basi, bu.kart_basi_token)} · ${B.sayi(bu.teslim_kart)} teslim`)}
        ${karo('Önlenebilir israf', tm ? '–' : B.para(israf?.onlenebilir_usd, israf?.onlenebilir_token), tm ? 'alan başına görünür' : `${ad} · ret kaynaklı`)}</div>
      ${hedefler}
      <section class="kart"><div class="kart-bas"><h2>${p === 'bugun' ? 'Saatlik' : 'Günlük'} harcama</h2><span class="soluk kucuk-y">${ad} · modele göre, ${B.birim()}</span></div><div class="kart-ic">${dilimGrafik(dilim, modelRenk, p === 'bugun', ad)}</div></section>
      <div class="izgara iki">
        <section class="kart"><div class="kart-bas"><h2>Model</h2><span class="soluk kucuk-y">${ad}</span></div><div class="kart-ic">${modelL.length ? modelL.map(([m, v], j) => H`<div class="cubuk-l"><span>${m}</span><span class="yol"><i style="width:${(v / mx(modelL) * 100).toFixed(1)}%;--renk:${modelRenk[m] || MODEL_RENK[j % MODEL_RENK.length]}"></i></span><span class="d">${B.para(v, v)}</span></div>`) : H`<p class="soluk">${bos0}</p>`}</div></section>
        <section class="kart"><div class="kart-bas"><h2>Süreç</h2><span class="soluk kucuk-y">${ad}</span></div><div class="kart-ic">${surec.length ? surec.map(([m, v]) => H`<div class="cubuk-l"><span>${m}</span><span class="yol"><i style="width:${(v / mx(surec) * 100).toFixed(1)}%"></i></span><span class="d">${B.para(v, v)}</span></div>`) : H`<p class="soluk">${bos0}</p>`}</div></section>
      </div>
      ${onbellekKarti(an.onbellek)}
      <div class="izgara iki" style="align-items:start">
        <section class="kart"><div class="kart-bas"><h2>En pahalı kartlar</h2><span class="soluk kucuk-y">${ad} · tıkla: koşu izi</span></div><div class="kart-ic">${pahali.length ? pahali.map(([id, v, alanId]) => H`<a class="cubuk-l" href="#/kart/${enc(id)}${ek('', alanId ? { alan: { id: alanId } } : null)}" data-gez><span class="kimlik">${id}</span>${tm && alanId ? H`<span class="etiket alan-rozet">${alanAd(alanId)}</span>` : ''}<span class="yol"><i style="width:${(v / mx(pahali) * 100).toFixed(1)}%;--renk:var(--seri-2)"></i></span><span class="d">${B.para(v, v)}</span></a>`) : H`<p class="soluk">${bos0}</p>`}</div></section>
        ${tm ? '' : H`<section class="kart"><div class="kart-bas"><h2>Basamak verimi</h2><span class="soluk kucuk-y">${ad} içinde oluşan kartlar</span></div><div class="tablo-kap"><table class="tablo"><thead><tr><th>Basamak</th><th class="sayi">Kart</th><th class="sayi">İlk geçiş</th><th class="sayi">Ret</th><th class="sayi">Kart başı</th></tr></thead>
          <tbody>${(ap.basamak || []).map(s => H`<tr><td><span class="etiket">${s.basamak}</span></td><td class="sayi">${B.sayi(s.kart)}</td><td class="sayi">${B.yuzde(s.ilk_gecis_orani)}</td><td class="sayi" style="${s.ret_orani > 0.15 ? 'color:var(--kotu)' : ''}">${B.yuzde(s.ret_orani)}</td><td class="sayi">${B.para(s.kart_basi_usd, s.kart_basi_token)}</td></tr>`)}</tbody></table></div></section>`}
      </div>`;
    return { baslik: 'Maliyet', sag: H`<a class="dugme hayalet kucuk" href="/maliyet?alan=${enc(gercekAlan())}">Ayrıntılı analiz</a>`, govde: H`<div class="icerik yigin">${govde}</div>` };
  }

  // ================================================================ 10. Görünüm: Kurallar
  function gKurallar(r) {
    const yuk = bekle('/kurallar.json');
    const kv = d('/kurallar.json').veri || {};
    const q = r.q.get('q') || '', kt = r.q.get('k') || '';
    const etkin = (kv.etkin || []).filter(k => (!kt || k.katman === kt) && (!q || eslesir(k.id + ' ' + k.metin + ' ' + (k.neden || '') + ' ' + (k.alan?.ad || ''), q)));
    const KATMAN = { plugin: 'Eklenti', proje: 'Proje' };
    const kural = k => H`<article class="kart" data-gez><div class="kart-ic yigin sik">
      <div class="yatay"><span class="kimlik">${k.id}</span><span class="etiket">${KATMAN[k.katman] || k.katman || '–'}</span>${k.ortak ? H`<span class="etiket" title="Eklenti kuralı tüm çalışma alanlarında geçerli">ortak</span>` : alanRozeti(k)}<span class="soluk kucuk-y" style="margin-left:auto">${B.goreli(k.guncelleme || k.olusturma)}</span></div>
      <b>${ilkCumle(k.metin)}</b>
      <details class="ac"><summary>Tam metin ve neden</summary><div class="yigin sik" style="margin-top:8px"><p class="ikincil">${k.metin}</p>${k.neden ? H`<p class="soluk kucuk-y"><b>Neden:</b> ${k.neden}</p>` : ''}</div></details>
    </div></article>`;
    const say = { '': (kv.etkin || []).length, plugin: (kv.etkin || []).filter(k => k.katman === 'plugin').length, proje: (kv.etkin || []).filter(k => k.katman === 'proje').length };
    const govde = yuk || H`
      ${(kv.oneriler || []).length ? H`<section class="gelen-grup"><h2>Önerilen kurallar <span class="say">${kv.oneriler.length}</span></h2>${kv.oneriler.map(kural)}<p class="soluk kucuk-y">Öneriler Gelen kutusunda onaylanır.</p></section>` : ''}
      <div class="yatay">${[['', 'Tümü'], ['plugin', 'Eklenti'], ['proje', 'Proje']].map(([k, ad]) => H`<button class="cip" data-eylem="sorgu" data-k="k" data-v="${k}" aria-pressed="${kt === k}">${ad}<span class="say">${say[k]}</span></button>`)}
        <input class="arama" id="kuralAra" type="search" placeholder="Kural ara…  /" value="${q}" data-sorgu="q" aria-label="Kural ara"></div>
      <div class="yigin sik">${etkin.length ? etkin.map(kural) : bos('Eşleşen kural yok', '', 'ara')}</div>
      ${(kv.gecmis || []).length ? H`<details class="ac"><summary>${kv.gecmis.length} kaldırılan ya da devre dışı kural</summary><div class="yigin sik" style="margin-top:8px">${kv.gecmis.map(k => H`<div class="k-satir"><span class="kimlik">${k.id}</span> ${rozet(k.durum === 'kaldirildi' ? 'iptal' : k.durum, k.durum)} ${ilkCumle(k.metin)}</div>`)}</div></details>` : ''}`;
    return { baslik: 'Kurallar', sag: tumMu() ? '' : H`<a class="dugme kucuk" href="/onaylar?alan=${enc(V.alan)}#kurallar">Kural ekle ya da düzenle</a>`, govde: H`<div class="icerik yigin" style="max-width:920px">${govde}</div>` };
  }

  // ================================================================ 10a. Görünüm: Ayarlar (makine düzeyi, çalışma alanından bağımsız)
  function gAyarlar() {
    const yuk = bekle(AYAR_YOL);
    const b = d(AYAR_YOL).veri?.bildirim;
    const ortam = b?.kaynak === 'ortam';
    const neden = !b ? '' : !b.destek ? 'Bildirim yalnız Windows’ta çalışır.' : ortam ? 'ORKESTRA_BILDIRIM ortam değişkeni belirliyor; ayarı değiştirmek için önce onu kaldır.' : '';
    const govde = yuk || (b ? H`
      <section class="kart"><div class="kart-ic yatay ayar-satir">
        <div class="yigin"><b id="ayarBildirimAd">Bildirim</b>
          <span class="soluk kucuk-y" id="ayarBildirimAcik">İş bitince, yanıtın ya da onayın gerekince Windows bildirimi gönderir. Veri dışarı gitmez.</span>
          ${neden ? H`<span class="soluk kucuk-y">${neden}</span>` : ''}</div>
        <button type="button" class="anahtar" role="switch" data-eylem="ayar-bildirim" aria-checked="${b.acik}" aria-labelledby="ayarBildirimAd" aria-describedby="ayarBildirimAcik" ${neden ? 'disabled' : ''}><span class="anahtar-durum">${b.acik ? 'Açık' : 'Kapalı'}</span></button>
      </div></section>` : bos('Ayarlar okunamadı', '', 'uyari'));
    return { baslik: 'Ayarlar', sag: H`<span class="soluk kucuk-y">bu bilgisayar için geçerli</span>`, govde: H`<div class="icerik yigin" style="max-width:820px">${govde}</div>` };
  }
  async function ayarBildirim(b) {
    const hedef = b.getAttribute('aria-checked') !== 'true';
    b.disabled = true;
    try { await gonder(AYAR_YOL, { bildirim: hedef }); bildir(hedef ? 'Bildirim açıldı.' : 'Bildirim kapatıldı.'); }
    catch (x) { bildir('Ayar kaydedilemedi: ' + x.message, { hata: true, sure: 8000 }); }
    await getir(AYAR_YOL, { taze: true });
    planla();
  }

  // ================================================================ 10c. Görünüm: Araçlar (MCP ve skill aç/kapat; ADR-0098)
  // MCP: kullanıcı düzeyi kayıt (claude mcp add/remove). Skill: seçili çalışma alanının yerel ayarı; eklenti skill'i yalnız çağrıya kapanır.
  const ARAC_KAYNAK = { eklenti: 'Eklenti', kullanici: 'Kullanıcı', proje: 'Proje' };
  function gAraclar(r) {
    const t = r.q.get('t') === 'skill' ? 'skill' : 'mcp', q = r.q.get('q') || '';
    const yuk = bekle(t === 'skill' && !tumMu() ? ARAC_SKILL : ARAC_MCP);
    const mcp = d(ARAC_MCP).veri?.mcp || [], skill = d(ARAC_SKILL).veri?.skill || [];
    const satir = (tur, o) => {
      const mcpMi = tur === 'mcp', ac = o.durum === 'acik';
      const eksik = mcpMi && o.eksik_gerek.length;
      const neden = eksik && !ac ? `Önce kurulmalı: ${o.eksik_gerek.join(', ')}` : '';
      const ad = mcpMi ? 'MCP' : 'Skill';
      return H`<article class="kart" data-gez><div class="kart-ic yatay ayar-satir">
        <div class="yigin sik"><div class="yatay"><b id="ar-${tur}-${o.ad}">${o.ad}</b>
          ${mcpMi ? '' : H`<span class="etiket">${ARAC_KAYNAK[o.kaynak] || o.kaynak}</span>`}
          ${mcpMi && o.yuksek_yetki ? H`<span class="rozet r-uyari" title="Dosya sistemi, kabuk ya da masaüstü denetimi verir">Yüksek yetki</span>` : ''}
          ${eksik ? H`<span class="rozet r-uyari">Ön koşul eksik: ${o.eksik_gerek.join(', ')}</span>` : ''}
          ${mcpMi && String(o.kimlik).startsWith('yok') ? H`<span class="rozet r-notr" title="Anahtar değeri bu sayfadan girilmez: orkestra kimlik ekle">Anahtar eksik</span>` : ''}
          ${!mcpMi && o.mekanizma === 'deny' ? H`<span class="etiket" title="Kapatınca çağrı engellenir; skill listede görünmeye devam eder">çağrıya kapanır</span>` : ''}</div>
          <span class="soluk kucuk-y">${o.aciklama || ''}</span>
          ${neden ? H`<span class="soluk kucuk-y">${neden}</span>` : ''}</div>
        <button type="button" class="anahtar" role="switch" data-eylem="arac-degistir" data-tur="${tur}" data-ad="${o.ad}" data-acik="${ac ? 'true' : 'false'}" aria-checked="${ac ? 'true' : 'false'}" aria-labelledby="ar-${tur}-${o.ad}" ${neden ? 'disabled' : ''}><span class="anahtar-durum">${ac ? 'Açık' : 'Kapalı'}</span></button>
      </div></article>`;
    };
    const sira = depo.al('arac-sira') === 'alfa' ? 'alfa' : 'durum';   // varsayılan: açıktan kapalıya
    const trSira = (a, b) => a.ad.localeCompare(b.ad, 'tr');
    const liste = (t === 'mcp' ? mcp : skill).filter(o => !q || eslesir(o.ad + ' ' + (o.aciklama || ''), q))
      .sort((a, b) => sira === 'alfa' ? trSira(a, b) : ((b.durum === 'acik') - (a.durum === 'acik')) || trSira(a, b));
    const sayi = a => a.filter(o => o.durum === 'acik').length;
    const sekme = [['mcp', 'MCP', mcp], ['skill', 'Skill', skill]].map(([k, ad, a]) =>
      H`<button class="cip" data-eylem="sorgu" data-k="t" data-v="${k}" aria-pressed="${t === k ? 'true' : 'false'}">${ad}<span class="say">${a.length ? sayi(a) + '/' + a.length : ''}</span></button>`);
    const tumNot = t === 'skill' && tumMu() ? bos('Skill için bir çalışma alanı seç', 'Skill ayarı seçili çalışma alanına yazılır; üstteki alan seçiciden birini seç.', 'uyari') : null;
    const govde = tumNot || yuk || H`
      <div class="yatay">${sekme}<input class="arama" id="aracAra" type="search" placeholder="${t === 'mcp' ? 'MCP' : 'Skill'} ara…  /" value="${q}" data-sorgu="q" aria-label="Ara">
        ${[['durum', 'Açıktan kapalıya'], ['alfa', 'A–Z']].map(([k, ad]) => H`<button class="cip" data-eylem="arac-sirala" data-v="${k}" aria-pressed="${sira === k ? 'true' : 'false'}">${ad}</button>`)}</div>
      <p class="soluk kucuk-y">${t === 'mcp' ? 'Açık = kullanıcı kapsamında kayıtlı; yeni oturumda başlar. Kapatmak kaydı siler, ayar kayıt dosyasında kalır.' : 'Değişiklik seçili çalışma alanının yerel ayarına (.claude/settings.local.json) yazılır; yeni oturumda geçerli olur.'}</p>
      <div class="yigin sik" aria-live="polite">${liste.length ? liste.map(o => satir(t, o)) : bos('Eşleşen ' + (t === 'mcp' ? 'MCP' : 'skill') + ' yok', '', 'ara')}</div>`;
    return { baslik: 'Araçlar', sag: H`<span class="soluk kucuk-y">${t === 'mcp' ? 'bu bilgisayar için geçerli' : (tumMu() ? '' : alanAd(V.alan))}</span>`, govde: H`<div class="icerik yigin" style="max-width:920px">${govde}</div>` };
  }
  async function aracDegistir(b) {
    const tur = b.dataset.tur, ad = b.dataset.ad, hedef = b.dataset.acik !== 'true';
    const yol = tur === 'mcp' ? ARAC_MCP : ARAC_SKILL;
    b.disabled = true;
    try {
      const govde = { ad, durum: hedef ? 'acik' : 'kapali' };
      const s = tur === 'mcp' ? await gonder(ARAC_MCP, govde) : await gonder(ARAC_SKILL, govde);
      bildir(`${ad} ${s.durum === 'acik' ? 'açıldı' : 'kapatıldı'}.`);
    } catch (x) {
      const m = x.veri && x.veri.durum ? 'komut uygulanamadı, durum değişmedi' : x.message;
      bildir(`${ad} değiştirilemedi: ${m}`, { hata: true, sure: 8000 });
    }
    await getir(yol, { taze: true });
    planla();
  }

  // ================================================================ 10b. Görünüm: Yapılacaklar (kullanıcının kendi listesi)
  // Taslak ve bekleyen tamamlamalar yeniden çizimde kaybolmasın diye görünümün dışında tutulur.
  const YAP = { taslak: '', bekleyen: new Set(), alan: '' };   // alan: birleşik kipte yeni maddenin gideceği çalışma alanı
  const YAP_SINIR = 2000;
  const yapZaman = z => B.goreli(String(z || '').replace(' ', 'T'));

  function gYapilacaklar(r) {
    const yuk = bekle(YAP_YOL);
    const maddeler = d(YAP_YOL).veri?.maddeler || [];
    const q = r.q.get('q') || '';
    const g = q ? maddeler.filter(m => eslesir(m.metin, q)) : maddeler;
    const satir = m => H`<li class="${YAP.bekleyen.has(altAlan(m)) ? 'bitti' : ''}">
      <div class="yap-dugme">
        <button class="dugme kucuk hayalet" data-eylem="yap-kopya" data-id="${m.id}" data-alan="${m.alan?.id || ''}" aria-label="Kopyala: ${m.metin}">Kopyala</button>
        <button class="dugme kucuk" data-eylem="yap-tamam" data-id="${m.id}" data-alan="${m.alan?.id || ''}" ${YAP.bekleyen.has(altAlan(m)) ? 'disabled' : ''} aria-label="Tamamla: ${m.metin}">${simge('tamam')}Tamamla</button></div>
      <div class="yap-metin"><span>${alanRozeti(m)}${m.metin}</span><small class="soluk" title="${m.zaman || ''}">${yapZaman(m.zaman)}</small></div></li>`;
    const govde = yuk || H`
      <div class="karolar">${karo('Benim yapılacaklarım', maddeler.length, maddeler.length ? 'açık madde' : 'açık madde yok')}</div>
      <section class="kart"><div class="kart-ic yigin sik">
        <textarea class="yap-yeni" id="yapYeni" rows="2" maxlength="${YAP_SINIR}" placeholder="Yeni madde yaz, Enter ile ekle (Shift+Enter: yeni satır)" aria-label="Yeni yapılacak madde" data-yap="taslak">${YAP.taslak}</textarea>
        <div class="yatay">${tumMu() ? H`<select class="alan-sec" id="yapAlan" aria-label="Maddenin çalışma alanı" style="width:auto">${orkAlanlar().map(a => H`<option value="${a.id}" ${a.id === yapHedef() ? 'selected' : ''}>${a.ad}</option>`)}</select>` : ''}<span class="soluk kucuk-y" id="yapSayac">${YAP.taslak.length} / ${YAP_SINIR}</span><button class="dugme ana-d kucuk" style="margin-left:auto" data-eylem="yap-ekle">Ekle</button></div>
      </div></section>
      ${maddeler.length >= 8 ? H`<input class="arama" id="yapAra" type="search" placeholder="Madde ara…" value="${q}" data-sorgu="q" aria-label="Madde ara">` : ''}
      <section class="kart"><div class="kart-ic">${g.length ? H`<ul class="todo yap-liste">${g.map(satir)}</ul>` : bos(q ? 'Aramaya uyan madde yok' : 'Henüz madde yok', q ? '' : 'Yukarıya yaz, Enter ile ekle.', q ? 'ara' : 'tamam')}</div></section>`;
    return { baslik: 'Yapılacaklar', sag: H`<span class="soluk kucuk-y">yalnız sen düzenlersin</span>`, govde: H`<div class="icerik yigin" style="max-width:820px">${govde}</div>` };
  }

  const yapHedef = () => (orkAlanlar().some(a => a.id === YAP.alan) ? YAP.alan : gercekAlan());
  async function yapYaz(govde, alan) {
    try { await gonder(YAP_YOL, govde, alan); await getir(YAP_YOL, { taze: true }); return true; }
    catch (e) { bildir('Kaydedilemedi: ' + e.message, { hata: true, sure: 8000 }); return false; }
  }
  async function yapEkle() {
    const metin = YAP.taslak.trim();
    if (!metin) return;
    if (await yapYaz({ eylem: 'ekle', metin }, tumMu() ? yapHedef() : undefined)) { YAP.taslak = ''; planla(); }
    document.getElementById('yapYeni')?.focus();
  }
  const yapBul = (id, alan) => (d(YAP_YOL).veri?.maddeler || []).find(x => x.id === id && (!tumMu() || (x.alan?.id || '') === (alan || '')));
  async function yapTamam(id, alan) {
    const m = yapBul(id, alan);
    if (!m) return;
    const an = tumMu() ? m.alan?.id : undefined, ak = altAlan(m);
    YAP.bekleyen.add(ak); planla();
    const ok = await yapYaz({ eylem: 'sil', id }, an);
    YAP.bekleyen.delete(ak); planla();
    if (ok) bildir('Tamamlandı: ' + kisalt(m.metin, 60), { sure: 10000, geriAl: () => yapYaz({ eylem: 'ekle', metin: m.metin }, an).then(planla) });
  }
  async function yapKopya(id, alan) {
    const m = yapBul(id, alan);
    try { await navigator.clipboard.writeText(m ? m.metin : ''); bildir('Kopyalandı.'); }
    catch (x) { bildir('Kopyalanamadı.', { hata: true }); }
  }

  // ================================================================ 11. Kabuk ve çizim
  const SAYFALAR = [['gelen', 'Gelen kutusu', '#/gelen', 'gelen', 'g'], ['isler', 'İşler', '#/isler', 'isler', 'i'], ['kosular', 'Koşular', '#/kosular', 'kosular', 'k'],
    ['maliyet', 'Maliyet', '#/maliyet', 'maliyet', 'm'], ['kurallar', 'Kurallar', '#/kurallar', 'kurallar', 'r'], ['yapilacaklar', 'Yapılacaklar', '#/yapilacaklar', 'yapilacaklar', 'y'], ['araclar', 'Araçlar', '#/araclar', 'araclar', 'c'], ['ayarlar', 'Ayarlar', '#/ayarlar', 'ayarlar', 'a']];
  const GORUNUM = { gelen: gGelen, isler: gIsler, kosular: gKosular, kart: gKart, maliyet: gMaliyet, kurallar: gKurallar, yapilacaklar: gYapilacaklar, araclar: gAraclar, ayarlar: gAyarlar };

  function rayCiz() {
    const r = rota(), aktif = r.ad === 'kart' ? 'kosular' : r.ad;
    const gs = gelenSayisi(), acik = (d('/isler.json').veri?.isler || []).filter(i => i.durum === 'acik').length;
    const say = { gelen: gs ? H`<span class="say dikkat">${gs}</span>` : '', isler: acik ? H`<span class="say">${acik}</span>` : '' };
    const orkAlan = V.alanlar.filter(a => a.orkestra);
    const tema = document.documentElement.dataset.tema || 'sistem';
    document.getElementById('ray').innerHTML = H`
      <div class="ray-ust"><img src="/logo.png" alt=""><b>Orkestra</b></div>
      <select class="alan-sec" id="alanSec" aria-label="Çalışma alanı">${orkAlan.length > 1 ? H`<option value="${TUM}" ${tumMu() ? 'selected' : ''}>Tüm çalışma alanları</option>` : ''}${orkAlan.map(a => H`<option value="${a.id}" ${a.id === V.alan ? 'selected' : ''}>${a.ad}</option>`)}</select>
      <button class="ara-dugme" data-eylem="palet">${simge('ara')}<span>Ara ya da komut</span><kbd>Ctrl</kbd><kbd>K</kbd></button>
      <div class="gezinti">${SAYFALAR.map(([k, ad, h, s]) => H`<a href="${h}" ${aktif === k ? 'aria-current="page"' : ''}>${simge(s)}<span>${ad}</span>${say[k] || ''}</a>`)}</div>
      <div class="ray-alt">
        <span class="satir canli" id="canli"><i></i><span id="canliMetin">bağlanıyor</span></span>
        <span class="satir"><button class="dugme hayalet kucuk" data-eylem="tema" title="Tema: ${tema}">Tema: ${{ sistem: 'sistem', acik: 'açık', koyu: 'koyu' }[tema]}</button></span>
      </div>`.__h;
    canliYaz();
  }

  let cizPlan = 0;
  function planla() { if (!cizPlan) cizPlan = requestAnimationFrame(() => { cizPlan = 0; gorunumCiz(); }); }

  function gorunumCiz() {
    const r = rota();
    const g = (GORUNUM[r.ad] || gGelen)(r);
    // odak, imleç ve kaydırma korunur (yeniden çizim yazmayı bölmesin)
    const ae = document.activeElement, odakId = ae && ae.id, imlec = odakId && 'selectionStart' in ae ? [ae.selectionStart, ae.selectionEnd] : null;
    const kaydir = [...document.querySelectorAll('[data-kaydir]')].map(e => [e.id, e.scrollTop]);
    document.getElementById('bas').innerHTML = H`${g.yol ? H`<span class="yol">${g.yol}</span>` : H`<h1>${g.baslik}</h1>`}<span class="bosluk"></span>${g.sag || ''}${kontroller(r)}`.__h;
    const ana = document.getElementById('ana');
    // birleşik kipte okunamayan alan sessizce eksik kalmaz: hangi alanın neden atlandığı sayfanın başında yazılır
    const atlanan = tumMu() ? [...new Map(gerekler(r).flatMap(y => d(y).veri?.atlanan || []).map(a => [a.alan?.id, a])).values()] : [];
    const uyari = atlanan.length ? H`<p class="birlesik-not" role="status">Bu alanlar toplamda yok: ${atlanan.map(a => `${a.alan?.ad || '?'} (${a.hata})`).join('; ')}</p>`.__h : '';
    ana.innerHTML = uyari + g.govde.__h;
    ana.className = g.tam ? '' : '';
    document.title = 'Orkestra · ' + g.baslik;
    if (odakId) { const e = document.getElementById(odakId); if (e) { e.focus(); if (imlec) try { e.setSelectionRange(...imlec); } catch (x) { /* arama türü */ } } }
    kaydir.forEach(([id, t]) => { const e = id && document.getElementById(id); if (e) e.scrollTop = t; });
    rayCiz();
  }

  // ================================================================ 12. Canlı akış
  let kaynaklar = [], yedekZam = null;
  // birleşik kipte sunucu '*' akışı vermez; her orkestralı alanın akışı ayrı açılır, biri açıksa "canlı" sayılır
  function canliBagla() {
    kaynaklar.forEach(k => k.close());
    kaynaklar = [];
    clearInterval(yedekZam);
    yedekZam = setInterval(() => tazele(true), 30000);   // akış kopsa da veri bayatlamaz
    if (!window.EventSource || !V.alan) return;
    const acik = new Set();
    const durum = () => { V.canli = acik.size > 0; canliYaz(); };
    (tumMu() ? orkAlanlar().map(a => a.id) : [V.alan]).forEach(id => {
      const k = new EventSource('/akis?alan=' + enc(id));
      k.addEventListener('degisti', () => tazele(true));
      k.onopen = () => { acik.add(id); durum(); };
      k.onerror = () => { acik.delete(id); durum(); };
      kaynaklar.push(k);
    });
  }
  function canliYaz() {
    const e = document.getElementById('canli'), m = document.getElementById('canliMetin');
    if (!e || !m) return;
    const yas = V.sonBasari ? (Date.now() - V.sonBasari) / 1000 : null;
    const bayat = yas != null && yas > 90;
    e.className = 'satir canli' + (V.canli && !bayat ? ' acik' : bayat ? ' bayat' : '');
    m.textContent = (V.canli ? 'Canlı' : 'Yeniden bağlanıyor') + (yas != null ? ' · ' + (yas < 10 ? 'şimdi güncellendi' : B.goreli(new Date(V.sonBasari).toISOString())) : '');
  }
  setInterval(canliYaz, 5000);

  // ================================================================ 13. Etkileşim
  function bildir(metin, { geriAl, hata, sure = 5000 } = {}) {
    const kap = document.getElementById('bildirimler');
    const e = document.createElement('div');
    e.className = 'bildirim' + (hata ? ' hata' : '');
    e.innerHTML = H`<span>${metin}</span>${geriAl ? H`<button class="dugme kucuk">Geri al</button>` : ''}`.__h;
    kap.appendChild(e);
    const kapat = () => e.remove();
    if (geriAl) e.querySelector('button').addEventListener('click', () => { geriAl(); kapat(); });
    setTimeout(kapat, sure);
  }

  function kararVer(id, sonuc, secim, alan) {
    const an = alan || undefined, ak = (alan || '') + '|' + id;   // birleşik kipte karar kaydın kendi alanına yazılır
    if (ertelenen.has(ak)) return;
    const z = setTimeout(async () => {
      try {
        await gonder('/onay', { islem: 'karar', id, sonuc, secim: secim || null, not: '' }, an);
        ertelenen.delete(ak);
        getir('/onaylar.json', { taze: true });
      } catch (e) {
        ertelenen.delete(ak);
        bildir(`${id} kaydedilemedi: ${e.message}`, { hata: true, sure: 8000 });
        planla();
      }
    }, 5000);
    ertelenen.set(ak, { z, id, alan: an, sonuc, secim: secim || null });
    planla();
    bildir(`${id} ${sonuc === 'onay' ? 'onaylandı' + (secim ? ` (${secim})` : '') : 'reddedildi'}`, {
      geriAl: () => { clearTimeout(z); ertelenen.delete(ak); planla(); },
    });
  }

  // Geri al süresi dolmadan sayfa yenilenir ya da kapanırsa zamanlayıcı ölür ve karar hiç kaydedilmezdi (kart yenilemede
  // "bekliyor" olarak geri gelirdi). Sayfa terk edilirken bekleyen kararlar hemen gönderilir; keepalive isteği sayfa
  // kapanınca da tamamlanır.
  function ertelenenleriGonder() {
    ertelenen.forEach((e, ak) => {
      clearTimeout(e.z);
      ertelenen.delete(ak);
      try {
        fetch(urlAl('/onay', e.alan), { method: 'POST', keepalive: true, headers: { 'X-Orkestra': '1', 'Content-Type': 'application/json' },
          body: JSON.stringify({ islem: 'karar', id: e.id, sonuc: e.sonuc, secim: e.secim, not: '' }) }).catch(() => {});
      } catch (x) { /* sayfa zaten kapanıyor */ }
    });
  }
  window.addEventListener('pagehide', ertelenenleriGonder);

  document.addEventListener('click', async e => {
    const tr = e.target.closest('tr[data-git]');
    if (tr && !e.target.closest('a,button')) { git(tr.dataset.git); return; }
    const oge = e.target.closest('article[data-oturum]');   // kart öğesinin gövdesi: bağlantı ve düğmeler kendi işini yapar
    if (oge && !e.target.closest('a,button')) { sohbetAc(oge.dataset.oturum, oge.dataset.ad); return; }
    const b = e.target.closest('[data-eylem]');
    if (!b) return;
    const ey = b.dataset.eylem;
    if (ey === 'sorgu') sorguKoy(b.dataset.k, b.dataset.v);
    else if (ey === 'ayar-bildirim') ayarBildirim(b);
    else if (ey === 'arac-degistir') aracDegistir(b);
    else if (ey === 'arac-sirala') { depo.koy('arac-sira', b.dataset.v); planla(); }
    else if (ey === 'karar') kararVer(b.dataset.id, b.dataset.sonuc, b.dataset.secim, b.dataset.alan);
    else if (ey === 'uygula') {
      b.disabled = true;
      try { await gonder('/onay', { islem: 'simdi-uygula' }, b.dataset.alan || undefined); bildir('Uygulama arka planda başladı (pencere açılmaz); bitince kart kalkar.'); getir('/onaylar.json', { taze: true }); }
      catch (x) { bildir('Başlatılamadı: ' + x.message, { hata: true }); b.disabled = false; }
    } else if (ey === 'perspektif') {
      b.disabled = true;
      try { await gonder('/perspektif-calistir', {}, b.dataset.alan || undefined); bildir("Yeni sohbet açıldı; istem hazır, Enter'a bas."); getir('/onaylar.json', { taze: true }); }
      catch (x) { bildir('Perspektif başlatılamadı: ' + x.message, { hata: true }); b.disabled = false; }
    } else if (ey === 'perspektif-yoksay') {
      b.disabled = true;
      try { await gonder('/perspektif-yoksay', {}, b.dataset.alan || undefined); bildir('Yoksayıldı; bir sonraki tetiklemeye kadar sorulmaz.'); getir('/onaylar.json', { taze: true }); }
      catch (x) { bildir('Yoksayılamadı: ' + x.message, { hata: true }); b.disabled = false; }
    } else if (ey === 'guncelle') {
      b.disabled = true;
      try { await gonder('/api/guncelle'); bildir('Güncelleme başladı.'); }
      catch (x) { bildir('Güncelleme başlatılamadı: ' + x.message, { hata: true, sure: 8000 }); }
      await getir(GUNC_YOL, { taze: true });   // başarıda 'calisiyor' kartı gelir ve yoklama başlar; başka sekmede çalışıyorsa o da görünür
      b.disabled = false;
    } else if (ey === 'guncelle-ertele') {
      b.disabled = true;
      try { await gonder('/api/guncelle-ertele'); bildir('Yeni bir sürüm çıkınca yeniden hatırlatılır.'); }
      catch (x) { bildir('Ertelenemedi: ' + x.message, { hata: true }); }
      await getir(GUNC_YOL, { taze: true });
      b.disabled = false;
    } else if (ey === 'yenile') { V.onbellek.delete(anahtar(b.dataset.yol)); tazele(true); }
    else if (ey === 'kopyala') { try { await navigator.clipboard.writeText(b.dataset.metin); bildir('Yol kopyalandı.'); } catch (x) { bildir('Kopyalanamadı.', { hata: true }); } }
    else if (ey === 'is-kapat') isKapatSor(b, b.dataset.is, b.dataset.alan || undefined);
    else if (ey === 'yap-ekle') yapEkle();
    else if (ey === 'yap-tamam') yapTamam(b.dataset.id, b.dataset.alan);
    else if (ey === 'yap-kopya') yapKopya(b.dataset.id, b.dataset.alan);
    else if (ey === 'sohbet-ac') sohbetAc(b.dataset.oturum, b.dataset.ad);
    else if (ey === 'palet') paletAc();
    else if (ey === 'tema') temaDegis();
    else if (ey === 'olcu') olcuKoy(b.dataset.v);
    else if (ey === 'pencere') pencereKoy(b.dataset.v);
  });
  document.addEventListener('input', e => {
    const t = e.target;
    if (t.dataset && t.dataset.sorgu) sorguKoy(t.dataset.sorgu, t.value);
    else if (t.dataset && t.dataset.yap === 'taslak') {   // yazılan metin yeniden çizimde kaybolmaz; sayaç yerinde güncellenir
      YAP.taslak = t.value;
      const s = document.getElementById('yapSayac'); if (s) s.textContent = t.value.length + ' / ' + YAP_SINIR;
    }
  });
  // alan seçimi: TUM ya da gerçek bir alan. Gerçek alan 'orkestra.alan'da, 'tüm' tercihi 'orkestra.tumAlan'da saklanır;
  // böylece birleşik kipten çıkınca son gerçek alan kaybolmaz.
  function alanSec(deger) {
    if (deger === TUM) depo.koy('orkestra.tumAlan', '1');
    else { depo.koy('orkestra.tumAlan', '0'); depo.koy('orkestra.alan', deger); }
    V.alan = deger; V.onbellek.clear();
    canliBagla(); git('#/gelen'); gorunumCiz(); tazele(true);
  }
  document.addEventListener('change', e => {
    if (e.target.id === 'alanSec') alanSec(e.target.value);
    else if (e.target.id === 'yapAlan') { YAP.alan = e.target.value; }
  });
  function temaDegis() {
    const sira = { sistem: 'acik', acik: 'koyu', koyu: 'sistem' };
    const yeni = sira[document.documentElement.dataset.tema || 'sistem'];
    if (yeni === 'sistem') delete document.documentElement.dataset.tema; else document.documentElement.dataset.tema = yeni;
    depo.koy('orkestra.tema', yeni);
    rayCiz();
  }

  let gBekliyor = 0;
  document.addEventListener('keydown', e => {
    if (e.target.id === 'yapYeni' && e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); yapEkle(); return; }
    const yaziyor = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); paletAc(); return; }
    if (document.querySelector('dialog[open]')) return;
    if (yaziyor) { if (e.key === 'Escape') e.target.blur(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const r = rota();
    if (gBekliyor && Date.now() - gBekliyor < 1200) {
      gBekliyor = 0;
      const s = SAYFALAR.find(x => x[4] === e.key);
      if (s) { e.preventDefault(); git(s[2]); }
      return;
    }
    if (e.key === 'g') { gBekliyor = Date.now(); return; }
    if ((e.key === 'p' || e.key === 'u') && kontrolVar()) { e.preventDefault(); if (e.key === 'u') olcuKoy(); else if (r.ad !== 'kart') pencereSonraki(); return; }
    if (/^[1-7]$/.test(e.key)) { git(SAYFALAR[+e.key - 1][2]); return; }
    if (e.key === '/') { const a = document.querySelector('#ana .arama'); if (a) { e.preventDefault(); a.focus(); a.select(); } else { e.preventDefault(); paletAc(); } return; }
    if (e.key === 'Escape') {
      if (r.ad === 'isler' && r.id) git('#/isler' + ek(r.q));
      else if (r.ad === 'kart') history.length > 1 ? history.back() : git('#/kosular');
      return;
    }
  });

  // ================================================================ 14. Komut paleti ve yardım
  function paletOgeleri() {
    const l = [];
    SAYFALAR.forEach(([k, ad, h], i) => l.push({ grup: 'Sayfalar', ad, ek: String(i + 1), git: h }));
    const alanEk = o => tumMu() && o.alan?.ad ? ' · ' + o.alan.ad : '';
    (d('/isler.json').veri?.isler || []).forEach(i => l.push({ grup: 'İşler', ad: i.ad, kimlik: i.id, ek: (i.durum === 'acik' ? 'açık' : 'kapandı') + alanEk(i), git: '#/is/' + enc(i.id) + ek('', i) }));
    const kartlar = new Map();
    (d('/analitik.json').veri?.akis?.kartlar || []).forEach(k => kartlar.set(altAlan(k), k));
    (d('/ozet.json').veri?.kartlar || []).forEach(k => kartlar.set(altAlan(k), { ...kartlar.get(altAlan(k)), ...k }));
    [...kartlar.values()].reverse().forEach(k => l.push({ grup: 'Kartlar', ad: k.baslik, kimlik: k.id, ek: (k.basamak || '') + alanEk(k), git: '#/kart/' + enc(k.id) + ek('', k) }));
    l.push({ grup: 'Komutlar', ad: 'Temayı değiştir', calis: temaDegis });
    l.push({ grup: 'Komutlar', ad: 'Ölçü birimini değiştir (USD / token)', ek: 'u', calis: () => olcuKoy() });
    PENCERE.forEach(([k, ad]) => l.push({ grup: 'Komutlar', ad: 'Zaman penceresi: ' + ad, ek: B.pencere() === k ? 'seçili' : 'p', calis: () => pencereKoy(k) }));
    l.push({ grup: 'Komutlar', ad: 'Veriyi şimdi yenile', calis: () => tazele(true) });
    [['Klasik: Dashboard', '/isler'], ['Klasik: Maliyet ve verim', '/maliyet'], ['Klasik: Onaylar, etki ve kurallar', '/onaylar'], ['Klasik: Son olaylar', '/simdi'], ['Klasik: Teknik detay', '/teknik']]
      .forEach(([ad, y]) => l.push({ grup: 'Klasik görünüm', ad, href: y + '?alan=' + enc(gercekAlan()) }));
    return l;
  }
  // İşi kapat: CLI `orkestra is kapat` ile aynı kapılar (POST /api/is-kapat). Kapı engeli yanıttaki `kapi` alanından okunur.
  function isKapatSor(dugme, isId, alan) {
    if (document.getElementById('isKapatOnay')) return;
    const dl = document.createElement('dialog');
    dl.className = 'onay'; dl.id = 'isKapatOnay';
    dl.setAttribute('aria-labelledby', 'isKapatBaslik');
    dl.innerHTML = H`<form method="dialog">
      <h2 id="isKapatBaslik">${isId} kapatılsın mı?</h2>
      <p class="soluk">Açık todo maddesi yok. Kapatırken çalışma özeti ve ADR kaydı denetlenir; kapanan iş "Kapanan" altına geçer.</p>
      <div id="isKapatGerekce" hidden>
        <label for="isKapatNeden" class="soluk kucuk-y">Özetsiz kapatma gerekçesi (zorunlu)</label>
        <textarea id="isKapatNeden" rows="2" maxlength="500" placeholder="Örn. iş hiç yapılmadı, yinelenen kayıt"></textarea>
      </div>
      <p class="hata-satir" id="isKapatHata" role="alert"></p>
      <div class="eylemler"><button type="button" class="dugme kucuk" id="isKapatVazgec">Vazgeç</button>
        <button type="button" class="dugme ana-d kucuk" id="isKapatEvet">Evet, kapat</button></div></form>`.__h;
    document.body.appendChild(dl);
    const evet = dl.querySelector('#isKapatEvet'), hata = dl.querySelector('#isKapatHata');
    const neden = dl.querySelector('#isKapatNeden'), gerekce = dl.querySelector('#isKapatGerekce');
    const kapat = () => { dl.close(); dl.remove(); if (dugme.isConnected) dugme.focus(); };
    let ozetsizKip = false;
    dl.querySelector('#isKapatVazgec').addEventListener('click', kapat);
    dl.addEventListener('cancel', e => { e.preventDefault(); kapat(); });
    evet.addEventListener('click', async () => {
      const govde = { is: isId };
      if (ozetsizKip) {
        const n = neden.value.trim();
        if (!n) { hata.textContent = 'Gerekçe yazın.'; neden.focus(); return; }
        govde.ozetsiz = n;
      }
      evet.disabled = true; evet.textContent = 'Kapatılıyor…'; hata.textContent = '';
      try {
        await gonder('/api/is-kapat', govde, alan);
        kapat();
        bildir(`${isId} kapatıldı.`);
        ['/isler.json', '/ozet.json'].forEach(y => getir(y, { taze: true }));
      } catch (err) {
        evet.disabled = false;
        evet.textContent = ozetsizKip ? 'Özetsiz kapat' : 'Evet, kapat';
        hata.textContent = 'Kapatılamadı: ' + err.message;
        // Kapı engeli (özet/ADR/teslim): gerekçe alanı açılır; iş gerçekten yapılmadıysa özetsiz kapatılabilir.
        if (err.veri?.kapi) { ozetsizKip = true; gerekce.hidden = false; evet.textContent = 'Özetsiz kapat'; neden.focus(); }
      }
    });
    dl.showModal();
    evet.focus();
  }
  function paletAc() {
    if (document.getElementById('palet')) return;
    getir('/analitik.json');
    const dl = document.createElement('dialog');
    dl.className = 'palet'; dl.id = 'palet';
    dl.innerHTML = H`<input type="text" placeholder="İş, kart, sayfa ya da komut ara…" aria-label="Komut paleti" autocomplete="off"><ul role="listbox"></ul>
      <div class="ipucu-alt"><span><kbd>↑</kbd><kbd>↓</kbd> seç</span><span><kbd>Enter</kbd> aç</span><span><kbd>Esc</kbd> kapat</span></div>`.__h;
    document.body.appendChild(dl);
    const inp = dl.querySelector('input'), ul = dl.querySelector('ul');
    let secili = 0, sonuc = [];
    const calis = o => {
      dl.close();
      if (o.git) git(o.git); else if (o.href) location.href = o.href; else if (o.calis) o.calis();
    };
    const doldur = () => {
      const q = inp.value.trim();
      const tum = paletOgeleri();
      sonuc = (q ? tum.filter(o => eslesir((o.kimlik || '') + ' ' + o.ad + ' ' + o.grup, q)) : tum.filter(o => o.grup !== 'Kartlar').slice(0, 30)).slice(0, 60);
      secili = Math.min(secili, Math.max(0, sonuc.length - 1));
      let son = '';
      ul.innerHTML = sonuc.length ? sonuc.map((o, i) => {
        const g = o.grup !== son ? H`<li class="grup" role="presentation">${o.grup}</li>`.__h : '';
        son = o.grup;
        return g + H`<li role="option" data-i="${i}" aria-selected="${i === secili}">${o.kimlik ? H`<span class="kimlik">${o.kimlik}</span>` : ''}<span>${kisalt(o.ad, 90)}</span><span class="tur">${o.ek || ''}</span></li>`.__h;
      }).join('') : '<li class="grup">Sonuç yok</li>';
      ul.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
    };
    inp.addEventListener('input', () => { secili = 0; doldur(); });
    inp.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); secili = Math.min(sonuc.length - 1, secili + 1); doldur(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); secili = Math.max(0, secili - 1); doldur(); }
      else if (e.key === 'Enter') { e.preventDefault(); if (sonuc[secili]) calis(sonuc[secili]); }
    });
    ul.addEventListener('click', e => { const li = e.target.closest('li[data-i]'); if (li) calis(sonuc[+li.dataset.i]); });
    dl.addEventListener('close', () => dl.remove());
    dl.addEventListener('click', e => { if (e.target === dl) dl.close(); });
    doldur();
    dl.showModal();
    inp.focus();
  }
  // ================================================================ 15. Başlangıç
  window.addEventListener('hashchange', () => { derinBaglanti(); gorunumCiz(); gerekler(rota()).forEach(y => getir(y)); document.getElementById('ana').focus({ preventScroll: true }); window.scrollTo(0, 0); });
  async function basla() {
    rayCiz();
    try {
      V.alanlar = await fetch('/alanlar.json').then(r => r.json());
    } catch (e) { V.alanlar = []; }
    const ork = V.alanlar.filter(a => a.orkestra);
    const adresAlan = new URLSearchParams(location.search).get('alan');
    const istenen = adresAlan || depo.al('orkestra.alan');
    V.alan = (ork.find(a => a.id === istenen) || ork[0] || {}).id || '';
    // birleşik kip: adreste ?alan=* ya da (adreste başka alan yokken) önceki seçim; tek orkestralı alanda anlamsızdır
    if (ork.length > 1 && (adresAlan === TUM || (!adresAlan && depo.al('orkestra.tumAlan') === '1'))) V.alan = TUM;
    if (!V.alan) {
      document.getElementById('ana').innerHTML = bos('Orkestralı çalışma alanı yok', 'Bir projede orkestra kurulunca burada görünür.', 'uyari').__h;
      rayCiz();
      return;
    }
    if (!tumMu()) depo.koy('orkestra.alan', V.alan);
    derinBaglanti();
    gorunumCiz();
    tazele();
    canliBagla();
  }
  basla();
})();
