/* Orkestra paneli: ortak çalışma zamanı (global window.O). Sözleşme: tasarim_sozlesmesi.md §2.
   O.B   biçimleyiciler (tek sayı dili, tr-TR)
   O.E   etiket sözlüğü (iç kimlik → kullanıcı dili; bilinmeyen değer olduğu gibi döner)
   O.kabuk({sayfa})        başlık: ad, sekmeler, çalışma alanı seçici, canlı göstergesi
   O.veri(yol, {ad, aralik, cizici, hata, gecerli, yoksay})   periyodik getirme; imza değişmedikçe çizmez
   O.canli(kaynak, tamam, mesaj)  canlı göstergesi; her kaynağın son denemesi ayrı tutulur
   O.ipucu, O.bildirim(metin), O.esc(s), O.depo.al/koy, O.temizMetin(s), O.yolGizle(s), O.hataMetni(e)

   Başlatma sırası (sayfalar buna güvenir):
     1. Sayfa O.kabuk({sayfa}) çağırır. Kabuk /alanlar.json'u okur, O.alan'ı çözer, sonra O.hazir sözünü çözer.
     2. O.veri(...) hemen çağrılabilir ama ilk getirmeyi O.hazir çözüldükten SONRA yapar; böylece
        yol fonksiyonu (ör. () => '/ozet.json?alan=' + O.alan) her zaman çözülmüş alanla çalışır.
        O.kabuk hiç çağrılmazsa O.veri başlamaz.
     3. Alan değişince 'orkestra:alan' olayı yayılır; alana bağlı O.veri'ler imzayı sıfırlayıp hemen yeniden getirir.
*/
(function () {
  'use strict';
  const O = window.O = window.O || {};
  const YER = 'tr-TR';

  // ------------------------------------------------------------ yardımcılar
  const bos = v => v == null || v === '' || (typeof v === 'number' && !isFinite(v));
  // Sayıyı tr-TR ile biçimler: binlik ayırıcı nokta, ondalık ayırıcı virgül. en az/en çok ondalık ayrı verilebilir.
  const yerel = (v, enCok, enAz = enCok) => Number(v).toLocaleString(YER, { minimumFractionDigits: enAz, maximumFractionDigits: enCok });
  const iki = n => String(n).padStart(2, '0');
  const tarihAl = s => {
    if (bos(s)) return null;
    const d = s instanceof Date ? s : new Date(typeof s === 'number' ? s : String(s));
    return isNaN(d) ? null : d;
  };
  const EKSI = '−'; // gerçek eksi işareti (−)

  O.esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  O.depo = {
    al(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    koy(k, v) { try { if (v == null || v === '') localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* gizli pencere */ } },
  };

  // Markdown soyar: tablo ayraçları (|---|) ve hücre çizgileri (| a | b | → a · b), ***, **, __, `, [a](b)→a;
  // başlık/alıntı imleri; boşlukları tek boşluğa indirir. Tek satıra inmiş tablolarda satır içi ayraç dizileri
  // (|---|---|, | :---: | ---: |, ---|---) da soyulur; boşlukla çevrili | dizileri tek " · " olur ("a||b" gibi kod dokunulmaz).
  const AYRAC_HUCRE = /^:?-{3,}:?$/;
  O.temizMetin = s => String(s ?? '')
    .replace(/^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$/gm, ' ')   // tablo ayraç satırı |---|---|
    .replace(/\|?(?:[ \t]*:?-{3,}:?[ \t]*\|)+(?:[ \t]*:?-{3,}:?(?![\w-]))?|\|[ \t]*:?-{3,}:?(?![\w|-])/g, ' | ')   // satır içi ayraç dizisi
    .replace(/^[ \t]*\|(.*)\|[ \t]*$/gm, (m, ic) => ic.split('|').map(h => h.trim()).filter(h => h && !AYRAC_HUCRE.test(h)).join(' · '))   // | a | b | → a · b
    .replace(/(^|\s)\|(?:\s+\|)*(?=\s|$)/g, ' · ')   // boşlukla çevrili | (ve "| | |" dizisi) → ·
    .replace(/\[([^\]]*)\]\(([^)]*)\)/g, '$1')
    .replace(/\*\*\*|\*\*|__|`/g, '')
    .replace(/(^|\s)[#>]+\s+/g, '$1')
    .replace(/\s+/g, ' ')
    .replace(/·(?: ·)+/g, '·')
    .replace(/([:;,]) · /g, '$1 ')
    .trim()
    .replace(/^· |^·$| ·$/g, '');

  // Tarayıcının ham ağ hata metinlerini kullanıcı diline çevirir (ham metin ipucunda ayrıca gösterilebilir).
  //   'Failed to fetch' / 'NetworkError …' / 'Load failed'  → 'sunucuya ulaşılamıyor'
  //   AbortError / TimeoutError                              → 'yanıt zaman aşımına uğradı'
  //   JSON ayrıştırma hatası (SyntaxError)                   → 'beklenmeyen yanıt (JSON değil)'
  //   sunucunun hata sözlüğü ('KeyError: …', 'OSError: …' gibi ham istisna)   → 'sunucu veriyi üretemedi'
  // Başka her metin olduğu gibi döner (ör. 'HTTP 500'). Ham metin çağıranda ipucu için ayrıca tutulur.
  O.hataMetni = e => {
    if (e == null || e === '') return 'bilinmeyen hata';
    const ad = (typeof e === 'object' && e.name) || '';
    const m = typeof e === 'object' ? String(e.message ?? '') : String(e);
    if (ad === 'TimeoutError' || ad === 'AbortError' || /^(?:AbortError|TimeoutError)\b|aborted/i.test(m)) return 'yanıt zaman aşımına uğradı';
    if (/Failed to fetch|NetworkError|Load failed|Network request failed|ERR_[A-Z_]+/i.test(m)) return 'sunucuya ulaşılamıyor';
    if (ad === 'SyntaxError' || /Unexpected token|not valid JSON|JSON\.parse/i.test(m)) return 'beklenmeyen yanıt (JSON değil)';
    if (/^[A-Za-z_.]*(?:Error|Exception)\b\s*:/.test(m.trim())) return 'sunucu veriyi üretemedi';
    return m || ad || 'bilinmeyen hata';
  };

  // Tam dosya yollarını son parçasına indirir (ekranda yol gösterilmez; tam yol gerekiyorsa ipucuna/title'a gider).
  O.yolGizle = s => String(s ?? '')
    .replace(/\b([A-Za-z]:[\\/](?:[^\\/\s"'<>|]+[\\/])*)([^\\/\s"'<>|]*)/g, (m, on, son) => {
      if (son) return '…\\' + son;
      const parcalar = on.split(/[\\/]/).filter(Boolean);   // ayraçla biten yol: son klasör adı korunur
      return parcalar.length > 1 ? '…\\' + parcalar[parcalar.length - 1] : m;
    })
    .replace(/(^|\s)\/(?:Users|home|mnt|tmp|var|opt)\/((?:[^/\s"'<>]+\/)*)([^/\s"'<>]*)/g, (m, on, yol, son) =>
      on + '…/' + (son || yol.split('/').filter(Boolean).pop() || ''));

  // ------------------------------------------------------------ O.B biçimleyiciler
  O.B = {
    // Para: |v| < 1000 → 2 ondalık ($5,65), ≥ 1000 → ondalıksız ($1.668); negatif −$.
    usd(v) {
      if (bos(v)) return '–';
      const n = Number(v);
      if (isNaN(n)) return '–';
      const a = Math.abs(n);
      const ondalik = Math.round(a * 100) / 100 < 1000 ? 2 : 0;
      const metin = yerel(a, ondalik);
      return (n < 0 && metin.replace(/[0,.]/g, '') !== '' ? EKSI : '') + '$' + metin;
    },
    // Token: ≥ 1e6 → "192 M" (10 M altı 1 ondalık: "2,1 M"); ≥ 1e3 → "567 K" (aynı kural); altı tam sayı.
    token(n) {
      if (bos(n)) return '–';
      const x = Number(n);
      if (isNaN(x)) return '–';
      const a = Math.abs(x), isaret = x < 0 ? EKSI : '';
      const kisalt = (bolen, harf) => {
        const v = a / bolen;
        const ondalik = Math.round(v * 10) / 10 < 10 ? 1 : 0;
        return isaret + yerel(v, ondalik, 0) + ' ' + harf;
      };
      if (a >= 1e6 || Math.round(a / 1e3) >= 1000) return kisalt(1e6, 'M');
      if (a >= 1e3) return kisalt(1e3, 'K');
      return isaret + yerel(Math.round(a), 0);
    },
    sayi(n, ondalik = 0) { return bos(n) || isNaN(Number(n)) ? '–' : yerel(n, ondalik, 0); },
    // Oran (0..1) → "%27"
    yuzde(x, ondalik = 0) { return bos(x) || isNaN(Number(x)) ? '–' : '%' + yerel(Number(x) * 100, ondalik, 0); },
    // Dakika → "45 dk" / "1,5 sa"
    dk(m) {
      if (bos(m) || isNaN(Number(m))) return '–';
      const v = Number(m);
      return Math.abs(v) < 60 ? yerel(Math.round(v), 0) + ' dk' : yerel(v / 60, 1, 0) + ' sa';
    },
    // "13.10 11:26"
    tarih(iso) { const d = tarihAl(iso); return d ? `${iki(d.getDate())}.${iki(d.getMonth() + 1)} ${iki(d.getHours())}:${iki(d.getMinutes())}` : '–'; },
    // "13.10"; "YYYY-MM-DD" saat dilimi kaymadan okunur
    gun(s) {
      if (bos(s)) return '–';
      const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s));
      if (m) return `${m[3]}.${m[2]}`;
      const d = tarihAl(s);
      return d ? `${iki(d.getDate())}.${iki(d.getMonth() + 1)}` : '–';
    },
    // "11:26"
    saat(iso) { const d = tarihAl(iso); return d ? `${iki(d.getHours())}:${iki(d.getMinutes())}` : '–'; },
    // "şimdi", "3 dk önce", "2 sa önce", "3 gün önce"
    once(iso) {
      const d = tarihAl(iso);
      if (!d) return '';
      const dk = Math.floor((Date.now() - d.getTime()) / 60000);
      if (dk < 1) return 'şimdi';
      if (dk < 60) return dk + ' dk önce';
      const sa = Math.floor(dk / 60);
      if (sa < 24) return sa + ' sa önce';
      return Math.floor(sa / 24) + ' gün önce';
    },
  };

  // ------------------------------------------------------------ O.E etiket sözlüğü
  const MODEL = {
    'opus-5-5': 'Opus 5.5', 'sonnet-5-5': 'Sonnet 5.5', 'haiku-5-5': 'Haiku 5.5',
    'fable-5-1': 'Fable 5.1', 'opus-4-8': 'Opus 4.8',
  };
  const SUREC = {
    orkestrasyon: 'Planlama ve koordinasyon', is: 'İşçi çalışması', denetim: 'Denetim', duzeltme: 'Düzeltme',
    arastirma: 'Araştırma', sentez: 'Sentez', perspektif: 'Perspektif (bakım)', ruya: 'Perspektif (bakım)',
    // gecmis-*: `orkestra maliyet gecmis` ile orkestra kaydı başlamadan önceki oturumlardan bir kez aktarılan kullanım
    'gecmis-ana': 'Orkestra öncesi · ana ajan', 'gecmis-alt': 'Orkestra öncesi · alt ajan',
    bilinmiyor: 'Etiketsiz', '-': 'Etiketsiz',
  };
  const AJAN = {
    'ana-ajan': 'Ana ajan', ana: 'Ana ajan',
    'orkestra:denetci': 'Denetçi', 'orkestra:arastirmaci': 'Araştırmacı', 'orkestra:triyaj': 'Triyaj',
    'orkestra:perspektif-ajani': 'Perspektif ajanı', 'orkestra:ruya-ajani': 'Perspektif ajanı', 'orkestra:skill-avcisi': 'Skill avcısı',
    'orkestra:hafiza-bakimcisi': 'Hafıza bakımcısı', 'orkestra:arsivci': 'Arşivci',
    'general-purpose': 'Genel alt ajan', Explore: 'Keşif ajanı', Plan: 'Plan ajanı', 'claude-code-guide': 'Claude Code rehberi',
  };
  const DURUM = {
    planlandi: ['Sırada', 'var(--neutral)'], isleniyor: ['Çalışıyor', 'var(--s1)'], denetimde: ['Denetimde', 'var(--warning)'],
    reddedildi: ['Reddedildi', 'var(--critical)'], onaylandi: ['Onaylandı · teslim bekliyor', 'var(--good)'],
    teslim: ['Teslim edildi', 'var(--neutral)'], beklemede: ['Beklemede', 'var(--neutral)'], iptal: ['İptal', 'var(--neutral)'],
  };
  const BEKLEYEN = {
    sen: ['Seni bekliyor', 'var(--warning)'], claude: ['Claude çalışıyor', 'var(--s1)'], bitti: ['Bitti', 'var(--good)'],
    beklemede: ['Beklemede', 'var(--neutral)'], kapandi: ['Kapandı', 'var(--neutral)'],
  };
  const KAYNAK = { motor: ["Claude'un hesabı", ''], defter: ['tahmini (orkestra defteri)', 'tahmini'], tahmin: ['kaba tahmin (transkript)', 'kaba'] };
  const ciftten = (tablo, k) => { const t = tablo[k]; return t ? { ad: t[0], renk: t[1] } : { ad: k == null ? '–' : String(k), renk: 'var(--neutral)' }; };

  O.E = {
    model(k) {
      if (bos(k)) return '–';
      const sade = String(k).replace(/^claude-/, '').replace(/\[[^\]]*\]$/, '').replace(/-\d{8}$/, '');
      if (MODEL[sade]) return MODEL[sade];
      const m = /^([a-z]+)-(\d+)(?:-(\d+))?$/i.exec(sade);   // genel kural: aile-X-Y → Aile X.Y
      if (m) return m[1].charAt(0).toLocaleUpperCase(YER) + m[1].slice(1) + ' ' + m[2] + (m[3] != null ? '.' + m[3] : '');
      return String(k);
    },
    surec(k) { return bos(k) ? 'Etiketsiz' : (SUREC[k] || String(k)); },
    ajan(k) {
      if (bos(k)) return '–';
      if (AJAN[k]) return AJAN[k];
      const m = /^(?:orkestra:)?isci-t(\d+)$/i.exec(String(k));
      return m ? 'İşçi T' + m[1] : String(k);
    },
    durum(k) { return ciftten(DURUM, k); },
    bekleyen(k) { return ciftten(BEKLEYEN, k); },
    // kisa=true → ekranda glif yerine kısa sözcük: "tahmini" / "kaba" ("motor" için boş)
    kaynak(k, kisa = false) { const t = KAYNAK[k]; return t ? t[kisa ? 1 : 0] : (k == null ? '' : String(k)); },
  };

  // ------------------------------------------------------------ ipucu
  // [data-ipucu] (HTML içerik, öznitelikte kaçışlı) öğelerinde fare, odak ve dokunmayla açılır; Esc kapatır.
  let ipucuEl = null, ipucuSahibi = null;
  const ipucuKutu = () => {
    if (!ipucuEl) {
      ipucuEl = document.getElementById('ipucu');
      if (!ipucuEl) { ipucuEl = document.createElement('div'); ipucuEl.id = 'ipucu'; document.body.appendChild(ipucuEl); }
      ipucuEl.setAttribute('role', 'tooltip');
    }
    return ipucuEl;
  };
  function konumla(x, y) {
    const k = ipucuKutu(), w = k.offsetWidth, h = k.offsetHeight;
    let sx = x + 14, sy = y + 14;
    if (sx + w > innerWidth - 8) sx = Math.max(8, x - w - 14);
    if (sy + h > innerHeight - 8) sy = Math.max(8, y - h - 14);
    k.style.left = sx + 'px'; k.style.top = sy + 'px';
  }
  O.ipucu = {
    goster(hedef, html, olay) {
      const k = ipucuKutu();
      k.innerHTML = html; k.style.display = 'block';
      ipucuSahibi = hedef || null;
      if (olay && olay.clientX != null && (olay.clientX || olay.clientY)) konumla(olay.clientX, olay.clientY);
      else if (hedef && hedef.getBoundingClientRect) { const r = hedef.getBoundingClientRect(); konumla(r.left, r.bottom - 6); }
    },
    gizle() { if (ipucuEl) ipucuEl.style.display = 'none'; ipucuSahibi = null; },
    get acik() { return !!ipucuSahibi; },
  };
  const ipucuHedef = e => (e.target && e.target.closest) ? e.target.closest('[data-ipucu]') : null;
  const eylemli = el => el.matches('a, button, select, input, summary, [role="button"]');
  document.addEventListener('mousemove', e => {
    if (e.sourceCapabilities && e.sourceCapabilities.firesTouchEvents) return;
    const el = ipucuHedef(e);
    if (el) O.ipucu.goster(el, el.dataset.ipucu, e);
    else if (ipucuSahibi && !ipucuSahibi.contains(document.activeElement)) O.ipucu.gizle();
  });
  document.addEventListener('mouseout', e => {
    const el = ipucuHedef(e);
    if (el && el === ipucuSahibi && !el.contains(e.relatedTarget)) O.ipucu.gizle();
  });
  document.addEventListener('focusin', e => {
    const el = ipucuHedef(e);
    if (el && e.target.matches(':focus-visible')) O.ipucu.goster(el, el.dataset.ipucu);
  });
  document.addEventListener('focusout', e => { if (ipucuHedef(e) === ipucuSahibi) O.ipucu.gizle(); });
  // Dokunma: eylemi olmayan öğede dokunmak ipucunu açar/kapatır; başka yere dokunmak kapatır.
  document.addEventListener('pointerup', e => {
    if (e.pointerType !== 'touch') return;
    const el = ipucuHedef(e);
    if (el && !eylemli(el)) {
      if (ipucuSahibi === el) O.ipucu.gizle(); else O.ipucu.goster(el, el.dataset.ipucu, e);
    } else if (!el) O.ipucu.gizle();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') O.ipucu.gizle(); });
  addEventListener('scroll', () => { if (ipucuSahibi) O.ipucu.gizle(); }, { passive: true });

  // ------------------------------------------------------------ bildirim (toast)
  let bildirimZaman = null;
  O.bildirim = metin => {
    let b = document.getElementById('bildirim');
    if (!b) { b = document.createElement('div'); b.id = 'bildirim'; document.body.appendChild(b); }
    b.setAttribute('role', 'status'); b.setAttribute('aria-live', 'polite');
    b.textContent = metin; b.classList.add('acik');
    clearTimeout(bildirimZaman);
    // canlı bölge erişilebilirlik ağacında hep kalır (display:none değil); kapanınca boşaltılır ve görsel olarak gizlenir
    bildirimZaman = setTimeout(() => { b.classList.remove('acik'); b.textContent = ''; }, 3500);
  };

  // ------------------------------------------------------------ canlı göstergesi
  // Her veri kaynağının (çalışma alanları, ozet, simdi, …) SON denemesi ayrı tutulur:
  //   hepsi başarılı → yeşil "canlı · 11:42"; bir kısmı hatalı → sarı "kısmi bağlantı"; hepsi hatalı → kırmızı "bağlantı yok".
  // Hatalı kaynakların adı ve hata metni göstergenin ipucunda (title) yazar.
  const kaynaklar = new Map();   // ad → {tamam, mesaj, zaman}
  const yeniden = new Map();     // ad → () => kaynağı hemen yeniden dene (O.veri ve çalışma alanları kaydeder)
  // Kaynak adındaki dosya adı/teknik ek ipucunda gösterilmez: 'Görev verisi (ozet.json)' → 'Görev verisi'.
  const kaynakAdiSade = ad => String(ad).replace(/\s*\([^)]*\)\s*$/, '').replace(/`/g, '');
  O.canli = (kaynak, tamam, mesaj) => {
    if (typeof kaynak === 'boolean') { mesaj = tamam; tamam = kaynak; kaynak = 'genel'; }   // eski çağrı biçimi
    const adi = String(kaynak);
    const onceki = kaynaklar.get(adi);
    kaynaklar.set(adi, { tamam: !!tamam, mesaj: mesaj ? String(mesaj) : '', zaman: new Date() });
    // Bir kaynak hatadan toparlandı: hatalı kalan DİĞER kaynaklar 15 sn'lik yoklamayı beklemeden hemen yeniden denenir
    // (aksi halde 'kısmi bağlantı' bayatlar). Başarısız deneme yeniden tetiklemez: döngü yok.
    if (tamam && onceki && !onceki.tamam) {
      setTimeout(() => {
        kaynaklar.forEach((d, ad2) => {
          const f = d.tamam || ad2 === adi ? null : yeniden.get(ad2);
          if (f) { try { f(); } catch (e) { console.error('O.canli yeniden deneme', ad2, e); } }
        });
      }, 0);
    }
    const c = document.getElementById('canli');
    if (!c) return;
    const hepsi = [...kaynaklar.entries()];
    const hatali = hepsi.filter(([, d]) => !d.tamam);
    const durum = !hatali.length ? 'acik' : hatali.length < hepsi.length ? 'kismi' : 'kopuk';
    c.classList.toggle('acik', durum === 'acik');
    c.classList.toggle('kismi', durum === 'kismi');
    c.classList.toggle('kopuk', durum === 'kopuk');
    const t = c.querySelector('span');
    if (t) t.textContent = durum === 'acik' ? 'canlı · ' + O.B.saat(new Date()) : durum === 'kismi' ? 'kısmi bağlantı' : 'bağlantı yok';
    // Ayrıntı fareyle, odakla ve dokunmayla açılır (O.ipucu); title kullanılmaz (klavyeyle erişilemez).
    const e = O.esc;
    c.dataset.ipucu = durum === 'acik'
      ? '<b>Bütün kaynaklar güncel</b><div class="meta">Son yenileme ' + e(new Date().toLocaleTimeString(YER)) + '</div>'
      : '<b>Alınamayan</b>' + hatali.map(([ad, d]) =>
          '<div>' + e(kaynakAdiSade(ad)) + (d.mesaj ? ' <span class="meta">(' + e(O.yolGizle(d.mesaj)) + ')</span>' : '') + '</div>').join('') +
        (durum === 'kopuk' ? '<div class="meta">Claude içinde <code>orkestra panel</code> ile sunucuyu yeniden başlat.</div>'
          : '<div class="meta">Hemen yeniden deneniyor.</div>');
    c.removeAttribute('title');
  };
  O.canliDurum = () => new Map(kaynaklar);

  // ------------------------------------------------------------ çalışma alanı ve kabuk
  const url = new URL(location.href);
  O.alan = url.searchParams.get('alan') || O.depo.al('orkestra.alan') || '';
  O.alanlar = [];
  O.alanBilgi = () => O.alanlar.find(a => a.id === O.alan) || null;
  const SEKMELER = [['simdi', 'Şimdi', '/'], ['maliyet', 'Maliyet', '/maliyet'], ['verim', 'Verim ve sağlık', '/verim']];
  const sorgu = () => (O.alan ? '?alan=' + encodeURIComponent(O.alan) : '');
  function sekmeBagla() {
    document.querySelectorAll('#kabuk [data-sekme]').forEach(a => { a.href = a.dataset.yol + sorgu(); });
    const m = document.querySelector('#kabuk .marka');
    if (m) m.href = '/' + sorgu();
  }
  function alanYaz(yeni, yay) {
    const degisti = yeni !== O.alan;
    O.alan = yeni || '';
    O.depo.koy('orkestra.alan', O.alan);
    const u = new URL(location.href);
    if (O.alan) u.searchParams.set('alan', O.alan); else u.searchParams.delete('alan');
    history.replaceState(null, '', u);
    sekmeBagla();
    const sec = document.getElementById('alanSec');
    if (sec) { const b = O.alanBilgi(); sec.title = b ? b.yol || '' : ''; }
    if (degisti && yay) window.dispatchEvent(new CustomEvent('orkestra:alan', { detail: { alan: O.alan, bilgi: O.alanBilgi() } }));
  }
  async function alanlariYukle() {
    const r = await fetch('/alanlar.json', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const liste = await r.json();
    if (!Array.isArray(liste)) return;
    O.alanlar = liste;
    const sec = document.getElementById('alanSec');
    if (sec) {
      const imza = liste.map(a => a.id + (a.orkestra ? '+' : '-') + a.ad).join('|');
      if (sec.dataset.imza !== imza) {
        sec.innerHTML = liste.map(a => `<option value="${O.esc(a.id)}">${O.esc(a.ad)}${a.orkestra ? '' : ' · yalnız maliyet'}</option>`).join('');
        sec.dataset.imza = imza;
      }
    }
    let hedef = O.alan;
    if (!liste.some(a => a.id === hedef)) hedef = ((liste.find(a => a.orkestra) || liste[0]) || {}).id || '';
    if (sec && document.activeElement !== sec) sec.value = hedef;
    alanYaz(hedef, true);
  }

  let hazirCoz;
  O.hazir = new Promise(c => { hazirCoz = c; });
  O.kabuk = ({ sayfa } = {}) => {
    let h = document.getElementById('kabuk');
    if (!h) { h = document.createElement('header'); h.id = 'kabuk'; document.body.prepend(h); }
    h.classList.add('kabuk');
    h.innerHTML = `<div class="kabuk-ic">
      <a class="marka" href="/">Orkestra</a>
      <nav class="sekmeler" aria-label="Sayfalar">${SEKMELER.map(([k, ad, yol]) =>
        `<a data-sekme="${k}" data-yol="${yol}" href="${yol}"${k === sayfa ? ' aria-current="page"' : ''}>${ad}</a>`).join('')}</nav>
      <span class="bosluk"></span>
      <label class="alan-sec"><span class="alan-etiket">Çalışma alanı</span> <select id="alanSec"></select></label>
      <span class="canli" id="canli" aria-live="off" tabindex="0"><i></i><span>bağlanıyor</span></span>
    </div>`;
    sekmeBagla();
    // Yapışkan başlığın gerçek yüksekliği --kabuk-yuk'e yazılır: html{scroll-padding-top} Shift+Tab ile odaklanan öğeyi altında bırakmaz.
    const yukOlc = () => document.documentElement.style.setProperty('--kabuk-yuk', Math.ceil(h.getBoundingClientRect().height) + 'px');
    yukOlc();
    if (typeof ResizeObserver === 'function') new ResizeObserver(yukOlc).observe(h); else addEventListener('resize', yukOlc);
    document.getElementById('alanSec').addEventListener('change', e => alanYaz(e.target.value, true));
    const alanHata = e => O.canli('Çalışma alanları', false, O.hataMetni(e));
    let alanYolda = false;   // tek uçuşlu: yoklama ile hızlı yeniden deneme çakışmaz
    const alanTazele = () => {
      if (alanYolda) return Promise.resolve();
      alanYolda = true;
      return alanlariYukle().then(() => O.canli('Çalışma alanları', true), alanHata).finally(() => { alanYolda = false; });
    };
    yeniden.set('Çalışma alanları', alanTazele);
    alanTazele().finally(() => hazirCoz(O.alan));
    setInterval(alanTazele, 15000);
    return O.hazir;
  };

  // ------------------------------------------------------------ periyodik veri
  // yol: dizge ya da fonksiyon (her getirmede yeniden hesaplanır, ör. () => '/ozet.json?alan=' + O.alan).
  // İmza = yanıtın JSON'u, `yoksay` anahtarları (varsayılan: üretim damgası) dışarıda. İmza aynıysa cizici çağrılmaz.
  //
  // İstek yaşam döngüsü (aynı anda en çok BİR istek yoldadır):
  //   - yenile() (periyodik yoklama, görünürlük dönüşü, sayfa çağrısı) yolda istek varken YENİSİNİ BAŞLATMAZ; yoldakinin
  //     sözünü döndürür. Böylece aralıktan uzun süren ama geçerli yanıt atılmaz, gelince çizilir.
  //   - Yoldaki istek yalnız zorla() ve sifirla() (alan değişimi) ile geçersizlenir: iptal edilir (AbortController) ve
  //     yanıtı yine de gelirse atılır. zorla() hemen yeni istek başlatır; sifirla()'dan sonra yenile() başlatır.
  //   - Zaman aşımı: istek `zamanAsimi` ms içinde (varsayılan en az 15 sn, aralığın 5 katı) bitmezse iptal edilir ve
  //     hata sayılır: 'yanıt zaman aşımına uğradı'.
  //
  // Son iyi veri ve bayatlık (sayfalar bunu bedavaya alır):
  //   kontrol.son           son BAŞARILI çizilen veri; hata anında SİLİNMEZ (yalnız alan değişince sıfırlanır)
  //   kontrol.durum         'bekliyor' (henüz deneme yok) | 'tamam' | 'hata' (son deneme başarısız)
  //   kontrol.sonBasari     son başarılı getirmenin zamanı (Date) ya da null
  //   kontrol.hata          son hatanın kullanıcı metni ('' başarıda); ağ hataları O.hataMetni ile Türkçeleşir
  //   kontrol.hamHata       aynı hatanın ham metni (ör. 'Failed to fetch'); yalnız ipucunda gösterilir
  //   kontrol.hataBaslangic bu hata dizisinin başladığı an; kontrol.ardisikHata ardışık başarısız deneme sayısı
  //   kontrol.bayat         son veri var ama son deneme başarısız (ekranda "son güncelleme hh:mm · yenilenemiyor")
  //   kontrol.uzunHata      hata ≥ 3 ardışık yoklama ya da ≥ 10 sn sürüyor (ya da hiç veri gelmedi) → kullanıcıya şerit gösterilir
  //   kontrol.yolda         şu an yolda istek var mı; kontrol.istekSayisi başlatılan istek sayısı (tanı/test)
  // Kısa kopukluk DOM'a dokunmaz: imza korunur, toparlanınca veri aynıysa cizici yeniden çağrılmaz (titreme yok).
  // Hata sayılanlar: ağ/HTTP hatası, zaman aşımı, JSON değil, yanıtta `hata` alanı, `gecerli(v)` false, cizici istisnası.
  // Geri çağrılar: cizici(v, kontrol) yeni veri; durum(kontrol) her durum/bayatlık değişiminde (çizim yapmadan
  //   işaret ve şerit güncellemek için); hata(mesaj, kontrol) her başarısız denemede.
  // cizici istisna atarsa imza yazılmaz; bir sonraki yoklamada yeniden denenir.
  const UZUN_HATA_DENEME = 3, UZUN_HATA_MS = 10000, ZAMAN_ASIMI_EN_AZ = 15000;
  O.veri = (yol, { ad, aralik = 3000, cizici = () => {}, durum = () => {}, hata = () => {}, gecerli = null, yoksay = ['uretim'], alanaBagli = true, zamanAsimi = 0 } = {}) => {
    let imza = null, zaman = null, durdu = false, basladi = false, sira = 0, oncekiOzet = '', ucus = null;
    const sinirMs = zamanAsimi > 0 ? zamanAsimi : Math.max(ZAMAN_ASIMI_EN_AZ, aralik * 5);
    const kaynakAdi = ad || (typeof yol === 'string' ? yol : 'veri');
    const atla = new Set(yoksay);
    const imzala = v => JSON.stringify(v, (k, d) => (atla.has(k) ? undefined : d));
    const kontrol = {
      ad: kaynakAdi, son: null, durum: 'bekliyor', sonBasari: null, hata: '', hamHata: '', hataBaslangic: null, ardisikHata: 0, istekSayisi: 0,
      get bayat() { return this.durum === 'hata' && this.son != null; },
      get uzunHata() {
        return this.durum === 'hata' && (this.son == null || this.ardisikHata >= UZUN_HATA_DENEME ||
          (this.hataBaslangic != null && Date.now() - this.hataBaslangic.getTime() >= UZUN_HATA_MS));
      },
      get yolda() { return ucus != null; },
    };
    const bildir = () => {
      const oz = [kontrol.durum, kontrol.bayat, kontrol.uzunHata, kontrol.hata, kontrol.son != null].join('|');
      if (oz === oncekiOzet) return;
      oncekiOzet = oz;
      try { durum(kontrol); } catch (e) { console.error('O.veri durum işleyicisi', kaynakAdi, e); }
    };
    // mesaj: kullanıcı metni; ham: ipucundaki özgün metin (verilmezse mesajın kendisi)
    const basarisiz = (mesaj, e, ham) => {
      if (e) console.error('O.veri', kaynakAdi, e);
      if (kontrol.durum !== 'hata') kontrol.hataBaslangic = new Date();
      kontrol.durum = 'hata'; kontrol.hata = String(mesaj || 'bilinmeyen hata'); kontrol.ardisikHata++;
      kontrol.hamHata = ham ? String(ham) : kontrol.hata;
      O.canli(kaynakAdi, false, kontrol.hata + (kontrol.hamHata !== kontrol.hata ? ' · ' + kontrol.hamHata : ''));
      try { hata(kontrol.hata, kontrol); } catch (e2) { console.error('O.veri hata işleyicisi', kaynakAdi, e2); }
      bildir();
    };
    // Tek getirme: fetch, zaman aşımı ve dış iptal yarışır. Yarış, sinyali yok sayan (ör. test için sahte) fetch'te de
    // isteği bitirir; gerçek tarayıcıda iptal ayrıca bağlantıyı keser.
    const getir = (adres, iptal) => {
      let saat = null;
      const sinir = new Promise((_, red) => {
        iptal.signal.addEventListener('abort', () => {
          const e = new Error('istek iptal edildi'); e.name = 'AbortError';
          red(iptal.signal.reason instanceof Error ? iptal.signal.reason : e);
        }, { once: true });
        saat = setTimeout(() => {
          const e = new Error('yanıt ' + Math.round(sinirMs / 1000) + ' sn içinde gelmedi'); e.name = 'TimeoutError';
          red(e);
          try { iptal.abort(e); } catch (x) { /* abort(neden) desteklenmiyor */ }
        }, sinirMs);
      });
      const istek = (async () => {
        const r = await fetch(adres, { cache: 'no-store', signal: iptal.signal });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })();
      return Promise.race([istek, sinir]).finally(() => clearTimeout(saat));
    };
    const calis = async (benim, iptal) => {
      kontrol.istekSayisi++;
      let v;
      try {
        v = await getir(typeof yol === 'function' ? yol() : yol, iptal);
      } catch (e) {
        if (benim !== sira) return;            // zorla/sifirla bu isteği geçersizledi: sessizce bırak
        return basarisiz(O.hataMetni(e), e, e && e.message ? e.message : String(e));
      }
      if (benim !== sira) return;              // geçersizlenmiş isteğin (ör. eski alan) yanıtı çizilmez
      if (v == null || typeof v !== 'object') return basarisiz('beklenmeyen yanıt');
      if (v.hata) return basarisiz(O.hataMetni(String(v.hata)), null, String(v.hata));   // ham istisna yalnız ipucunda
      if (gecerli && !gecerli(v)) return basarisiz('beklenmeyen yanıt biçimi');
      // başarı: durum önce güncellenir ki cizici bayatlık işaretlerini doğru okusun (çizim patlarsa geri alınır)
      const onceki = { durum: kontrol.durum, hata: kontrol.hata, hamHata: kontrol.hamHata, hataBaslangic: kontrol.hataBaslangic, ardisikHata: kontrol.ardisikHata, sonBasari: kontrol.sonBasari };
      kontrol.durum = 'tamam'; kontrol.hata = ''; kontrol.hamHata = ''; kontrol.hataBaslangic = null; kontrol.ardisikHata = 0; kontrol.sonBasari = new Date();
      const yeni = imzala(v);
      if (yeni !== imza) {
        try { cizici(v, kontrol); } catch (e) {
          Object.assign(kontrol, onceki); imza = null;
          return basarisiz('çizim hatası: ' + (e && e.message), e);
        }
        imza = yeni; kontrol.son = v;          // yalnız başarılı çizimden sonra
      }
      O.canli(kaynakAdi, true);
      bildir();
    };
    const baslat = () => {
      const u = { iptal: new AbortController(), soz: null };
      ucus = u;
      u.soz = calis(sira, u.iptal).finally(() => { if (ucus === u) ucus = null; });
      return u.soz;
    };
    // yoldaki isteği geçersizler: nesil (sira) artar, istek iptal edilir; yanıtı gelse de atılır
    const gecersizle = () => {
      sira++;
      const u = ucus;
      ucus = null;
      if (u) { try { u.iptal.abort(); } catch (e) { /* zaten bitti */ } }
    };
    // yolda istek varken yenisi başlatılmaz (yavaş ama geçerli yanıt atılmasın): yoldakinin sözü döner
    kontrol.yenile = () => (ucus ? ucus.soz : baslat());
    kontrol.zorla = () => { imza = null; gecersizle(); return baslat(); };
    kontrol.sifirla = () => {                  // alan değişti: eski alanın verisi artık "son iyi veri" değildir
      gecersizle();
      imza = null; kontrol.son = null; kontrol.durum = 'bekliyor'; kontrol.sonBasari = null;
      kontrol.hata = ''; kontrol.hamHata = ''; kontrol.hataBaslangic = null; kontrol.ardisikHata = 0; oncekiOzet = '';
    };
    kontrol.durdur = () => { durdu = true; clearInterval(zaman); yeniden.delete(kaynakAdi); };
    yeniden.set(kaynakAdi, () => { if (!durdu && basladi) kontrol.yenile(); });
    O.hazir.then(() => {
      if (durdu) return;
      basladi = true;
      kontrol.yenile();
      zaman = setInterval(() => { if (!document.hidden) kontrol.yenile(); }, aralik);
    });
    // ilk alan çözümü O.hazir'dan önce olay yayar; o zaman ilk getirmeyi O.hazir yapar (çift istek olmasın)
    if (alanaBagli) window.addEventListener('orkestra:alan', () => { if (basladi && !durdu) { kontrol.sifirla(); kontrol.yenile(); } });
    document.addEventListener('visibilitychange', () => { if (basladi && !document.hidden && !durdu) kontrol.yenile(); });
    return kontrol;
  };

  // Bölüm başlığı için bayatlık işareti: verilen kontrollerden biri bayatsa "son güncelleme hh:mm · yenilenemiyor".
  // Hata metni (kullanıcı metni + farklıysa ham metin) ipucunda. Bayat değilse boş dizge (yerlestir ile kullanılınca DOM'a dokunulmaz).
  O.bayatIsaret = (...kontroller) => {
    const bayat = kontroller.filter(k => k && k.bayat);
    if (!bayat.length) return '';
    const en = bayat.reduce((a, k) => (!a || (k.sonBasari && k.sonBasari < a.sonBasari) ? k : a), null);
    const ham = k => (k.hamHata && k.hamHata !== k.hata ? ` <span class="meta">(${O.esc(O.yolGizle(k.hamHata))})</span>` : '');
    const ip = '<b>Yenilenemiyor</b>' + bayat.map(k => `<div>${O.esc(k.ad)}: ${O.esc(O.yolGizle(k.hata))}${ham(k)}</div>`).join('') +
      '<div class="meta">Gösterilen bilgi son başarılı yenilemeden; birkaç saniyede bir yeniden deneniyor.</div>';
    return `<span class="bayat" tabindex="0" data-ipucu="${O.esc(ip)}">son güncelleme ${O.B.saat(en.sonBasari)} · yenilenemiyor</span>`;
  };

  // "3 dk önce" gibi göreli zamanlar DOM'u yeniden kurmadan tazelenir: <span data-once="<iso>">.
  setInterval(() => {
    document.querySelectorAll('[data-once]').forEach(el => { el.textContent = O.B.once(el.dataset.once); });
  }, 30000);
})();
