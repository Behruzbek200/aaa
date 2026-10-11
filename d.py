# -*- coding: utf-8 -*-
"""QR Master — HTML sahifa"""
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="uz" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>QR Master</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script src="//libtl.com/sdk.js" data-zone="11990967" data-sdk="show_11990967"></script>
<style>
:root{--bg:#fff;--fg:#0f172a;--muted:#64748b;--card:#f1f5f9;--primary:#6366f1;
--primary-2:#8b5cf6;--border:#e2e8f0;--success:#22c55e;--danger:#ef4444;--radius:16px}
[data-theme="dark"]{--bg:#0f172a;--fg:#f1f5f9;--muted:#94a3b8;--card:#1e293b;--border:#334155}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--fg);padding-bottom:80px;min-height:100dvh}
.header{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;
background:var(--bg);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:19px}
.logo-mark{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--primary),var(--primary-2));
display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900}
.avatar{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#06b6d4,var(--primary));
display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:14px}
.main{padding:0 16px}
.hero{margin:16px 0;padding:22px;border-radius:var(--radius);background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff}
.hero h2{font-size:20px;margin-bottom:6px}.hero p{font-size:13px;opacity:.9}
.section-title{font-size:15px;font-weight:700;margin:22px 0 12px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.type-card{background:var(--card);border:none;border-radius:14px;padding:14px 8px;
display:flex;flex-direction:column;align-items:center;gap:6px;cursor:pointer;color:var(--fg);font-family:inherit;transition:transform .15s}
.type-card:active{transform:scale(.94)}
.type-icon{font-size:24px}.type-label{font-size:11px;text-align:center;font-weight:600}
.nav{position:fixed;bottom:0;left:0;right:0;display:flex;background:var(--bg);
border-top:1px solid var(--border);padding:8px 0 calc(8px + env(safe-area-inset-bottom))}
.nav-btn{flex:1;background:none;border:none;color:var(--muted);display:flex;
flex-direction:column;align-items:center;gap:2px;padding:6px;font-size:10px;font-weight:600;cursor:pointer;font-family:inherit}
.nav-btn.active{color:var(--primary)}.nav-btn .ico{font-size:20px}
.page{display:none;animation:fade .25s}.page.active{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.field{margin-bottom:14px}.field label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px;font-weight:600}
.input,.select,.textarea{width:100%;padding:14px 16px;background:var(--card);
border:1.5px solid transparent;border-radius:14px;font-size:15px;color:var(--fg);outline:none;font-family:inherit}
.input:focus,.textarea:focus,.select:focus{border-color:var(--primary)}
.textarea{resize:vertical;min-height:80px}
.btn{width:100%;padding:16px;border:none;border-radius:14px;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit;transition:transform .15s}
.btn:active{transform:scale(.97)}
.btn-primary{background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff}
.btn-ghost{background:var(--card);color:var(--fg)}
.btn-warn{background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff}
.qr-result{margin-top:20px;padding:20px;border-radius:var(--radius);background:var(--card);text-align:center}
.qr-result img,.qr-result canvas{border-radius:12px;max-width:100%;height:auto}
.qr-actions{display:flex;gap:8px;margin-top:14px}
.qr-actions .btn{padding:12px;font-size:13px}
.toast-wrap{position:fixed;top:80px;left:50%;transform:translateX(-50%);z-index:1000;
display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{padding:12px 20px;border-radius:12px;color:#fff;font-size:14px;font-weight:600;max-width:85vw;text-align:center}
.toast.success{background:var(--success)}.toast.error{background:var(--danger)}.toast.info{background:var(--primary)}
.empty{text-align:center;padding:40px 20px;color:var(--muted);font-size:14px}
.empty .ico{font-size:44px;display:block;margin-bottom:10px;opacity:.5}
.hist-item{display:flex;align-items:center;gap:12px;padding:14px;background:var(--card);border-radius:14px;margin-bottom:8px}
.hist-info{flex:1;min-width:0}
.hist-info h4{font-size:14px;font-weight:700;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hist-info p{font-size:12px;color:var(--muted)}
.icon-btn{width:34px;height:34px;border-radius:10px;border:none;background:var(--bg);
color:var(--fg);cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center}
.profile-card{padding:20px;border-radius:var(--radius);background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;text-align:center;margin-bottom:16px}
.profile-card .av{width:70px;height:70px;border-radius:50%;background:rgba(255,255,255,.2);
margin:0 auto 10px;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800}
.profile-card h3{font-size:17px;margin-bottom:4px}
.profile-card p{font-size:13px;opacity:.85}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:16px}
.stat{background:rgba(255,255,255,.15);padding:10px;border-radius:12px}
.stat b{display:block;font-size:18px;font-weight:800}
.stat span{font-size:10px;opacity:.85}
.loading{position:fixed;inset:0;background:rgba(15,23,42,.55);display:none;align-items:center;justify-content:center;z-index:2000}
.loading.on{display:flex}
.spin{width:42px;height:42px;border:3px solid rgba(255,255,255,.25);border-top-color:#fff;border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.ref-link{background:var(--card);padding:12px;border-radius:10px;font-family:monospace;font-size:11px;
word-break:break-all;margin:10px 0;border:1px solid var(--border)}
.logo-upload{display:flex;align-items:center;gap:10px;padding:14px;background:var(--card);
border-radius:14px;border:2px dashed var(--border);cursor:pointer;margin-bottom:10px}
.logo-upload img{width:50px;height:50px;object-fit:contain;border-radius:8px}
</style>
</head>
<body>

<div class="header">
  <div class="logo"><div class="logo-mark">QR</div><span>QR Master</span></div>
  <div class="avatar" id="avatar">U</div>
</div>

<div class="main">
  <!-- HOME -->
  <div class="page active" id="page-home">
    <div class="hero"><h2>🎯 QR Master</h2><p>Har qanday QR kod yaratish</p></div>
    <div class="section-title">QR turlari</div>
    <div class="grid" id="typeGrid"></div>
    <div class="section-title">So'nggi QR kodlar</div>
    <div id="recentList"></div>
  </div>

  <!-- CREATE -->
  <div class="page" id="page-create">
    <div class="section-title" id="createTitle">QR kod</div>
    <div id="dynamicFields"></div>
    <div class="section-title">🎨 Dizayn</div>
    <div class="field"><label>QR rangi</label>
      <input type="color" id="fillColor" value="#0f172a" style="width:100%;height:50px;border:none;border-radius:12px"></div>
    <div class="field"><label>Fon rangi</label>
      <input type="color" id="backColor" value="#ffffff" style="width:100%;height:50px;border:none;border-radius:12px"></div>
    <div class="field"><label>📷 Logo (ixtiyoriy)</label>
      <div class="logo-upload" id="logoBox" onclick="document.getElementById('logoFile').click()">
        <img id="logoPreview" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='50' height='50'%3E%3Ctext x='50%25' y='55%25' text-anchor='middle' font-size='24' fill='%2364748b'%3E%2B%3C/text%3E%3C/svg%3E">
        <div style="flex:1">
          <div style="font-weight:700;font-size:14px">Logo yuklash</div>
          <div style="font-size:11px;color:var(--muted)">PNG, JPG - 500 KB gacha</div>
        </div>
      </div>
      <input type="file" id="logoFile" accept="image/*" hidden>
      <button class="btn btn-ghost" id="clearLogo" style="display:none;padding:8px;font-size:12px">🗑 Logoni o'chirish</button>
    </div>
    <div class="field"><label>O'lcham</label>
      <select class="select" id="qrSize">
        <option value="256">256×256</option>
        <option value="512" selected>512×512</option>
        <option value="1024">1024×1024</option></select></div>
    <button class="btn btn-primary" id="genBtn">✨ Yaratish</button>
    <button class="btn btn-ghost" id="backBtn" style="margin-top:8px">← Orqaga</button>
    <div class="qr-result" id="qrResult" style="display:none">
      <div id="qrContainer"></div>
      <div class="qr-actions">
        <button class="btn btn-primary" id="dlBtn">⬇️ Yuklab olish</button>
        <button class="btn btn-ghost" id="saveHistBtn">💾 Saqlash</button>
      </div>
    </div>
  </div>

  <!-- ADS -->
  <div class="page" id="page-ads">
    <div class="section-title">🎬 Reklama / Unlock</div>
    <div class="hero"><h2>🔓 Qo'shimcha QR limit</h2>
      <p>Reklama ko'ring yoki do'stlarni taklif qiling</p></div>
    <div class="hist-item">
      <div class="hist-info">
        <h4>Bepul limit</h4>
        <p id="freeCount">5 ta</p>
      </div>
    </div>
    <div class="hist-item">
      <div class="hist-info">
        <h4>Unlock qilingan</h4>
        <p id="unlockCount">0 ta</p>
      </div>
    </div>
    <button class="btn btn-warn" id="watchAdBtn" style="margin-top:14px">
      ▶️ Reklama ko'rish (+3 QR)
    </button>
    <button class="btn btn-primary" id="inviteBtn" style="margin-top:8px">
      👥 Do'st taklif qilish (+10 QR)
    </button>
    <div class="section-title" style="margin-top:20px">Ko'rilgan reklamalar</div>
    <div class="hist-item">
      <div class="hist-info">
        <h4>Jami reklama</h4>
        <p id="adsTotal">0</p>
      </div>
    </div>
  </div>

  <!-- HISTORY -->
  <div class="page" id="page-history">
    <div class="section-title">🕐 Tarix</div>
    <div id="historyList"></div>
  </div>

  <!-- REF -->
  <div class="page" id="page-ref">
    <div class="section-title">👥 Referal tizimi</div>
    <div class="hero"><h2>🎁 +10 QR har referal</h2>
      <p>Do'stni taklif qiling va bonus oling</p></div>
    <div class="field"><label>Sizning havolangiz:</label>
      <div class="ref-link" id="refLink">—</div></div>
    <button class="btn btn-primary" id="copyRef">📋 Nusxalash</button>
    <button class="btn btn-ghost" id="shareRef" style="margin-top:8px">📤 Ulashish</button>
    <div class="section-title" style="margin-top:20px">Referallaringiz (<span id="refCount">0</span>)</div>
    <div id="refList"></div>
  </div>

  <!-- PROFILE -->
  <div class="page" id="page-profile">
    <div class="profile-card">
      <div class="av" id="profileAv">U</div>
      <h3 id="profileName">Foydalanuvchi</h3>
      <p id="profileUsername">@username</p>
      <div class="stats">
        <div class="stat"><b id="statQR">0</b><span>QR</span></div>
        <div class="stat"><b id="statAds">0</b><span>Reklama</span></div>
        <div class="stat"><b id="statUnlock">0</b><span>Unlock</span></div>
        <div class="stat"><b id="statRef">0</b><span>Referal</span></div>
      </div>
    </div>
    <button class="btn btn-ghost" id="themeBtn">🌗 Mavzuni almashtirish</button>
  </div>
</div>

<nav class="nav">
  <button class="nav-btn active" data-page="home"><span class="ico">🏠</span>Asosiy</button>
  <button class="nav-btn" data-page="ads"><span class="ico">🎬</span>Reklama</button>
  <button class="nav-btn" data-page="ref"><span class="ico">👥</span>Referal</button>
  <button class="nav-btn" data-page="history"><span class="ico">🕐</span>Tarix</button>
  <button class="nav-btn" data-page="profile"><span class="ico">👤</span>Profil</button>
</nav>

<div class="toast-wrap" id="toastWrap"></div>
<div class="loading" id="loading"><div class="spin"></div></div>

<script>
const MONETAG_ZONE = "11990967";

const AdManager = {
  async show() {
    const fn = window['show_' + MONETAG_ZONE];
    if (typeof fn !== 'function') { console.warn('SDK yo\'q'); return false; }
    try { await fn('pop'); return true; }
    catch (e) { console.warn(e); return false; }
  }
};

const App = {
  currentType: 'universal', currentData: null, initData: '', me: null,
  logoData: null,

  async init() {
    const tg = window.Telegram?.WebApp;
    if (tg) { tg.ready(); tg.expand();
      document.documentElement.setAttribute('data-theme', tg.colorScheme === 'dark' ? 'dark' : 'light');
    }
    this.initData = tg?.initData || '';
    this.renderTypes(); this.bindNav(); this.bindForm(); this.bindProfile(); this.bindRef(); this.bindAds();
    this.loadProfile();

    if (this.initData) {
      try {
        this.me = await this.api('/api/auth/me', 'POST');
        this.updateStats();
        await this.loadHistory();
        await this.loadRefs();
      } catch (e) {
        this.toast('Xato: ' + e.message, 'error');
        console.warn(e);
      }
    } else {
      this.toast('Telegram orqali oching!', 'error');
    }
  },

  async api(path, method = 'GET', body = null) {
    const opts = { method, headers: {
      'X-Telegram-Init-Data': this.initData, 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    if (!r.ok) { const e = await r.json().catch(() => ({ detail: 'Xatolik' }));
      throw new Error(e.detail || 'Xatolik'); }
    return r.json();
  },

  updateStats() {
    if (!this.me) return;
    document.getElementById('statQR').textContent = this.me.qr_count || 0;
    document.getElementById('statAds').textContent = this.me.ad_count || 0;
    document.getElementById('statUnlock').textContent = this.me.unlock_count || 0;
    document.getElementById('statRef').textContent = this.me.referrals || 0;
    document.getElementById('freeCount').textContent = (this.me.free_qr || 5) + ' ta';
    document.getElementById('unlockCount').textContent = (this.me.unlock_count || 0) + ' ta';
    document.getElementById('adsTotal').textContent = this.me.ad_count || 0;
  },

  loadProfile() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user || {};
    const f = (u.first_name || 'F').charAt(0).toUpperCase();
    document.getElementById('avatar').textContent = f;
    document.getElementById('profileAv').textContent = f;
    document.getElementById('profileName').textContent =
      ((u.first_name || '') + ' ' + (u.last_name || '')).trim() || 'Foydalanuvchi';
    document.getElementById('profileUsername').textContent = u.username ? '@' + u.username : 'Telegram';
  },

  types: [
    {id:'universal',icon:'✨',label:'Universal',fields:[{k:'text',l:'Matn / URL',t:'textarea',p:'Istalgan matn'}]},
    {id:'url',icon:'🔗',label:'URL',fields:[{k:'url',l:'Havola',t:'url',p:'https://example.com'}]},
    {id:'text',icon:'📝',label:'Matn',fields:[{k:'text',l:'Matn',t:'textarea'}]},
    {id:'wifi',icon:'📶',label:'Wi-Fi',fields:[
      {k:'ssid',l:'Tarmoq',t:'text'},{k:'pass',l:'Parol',t:'text'},
      {k:'sec',l:'Xavfsizlik',t:'select',opts:['WPA','WEP','nopass']}]},
    {id:'vcard',icon:'👤',label:'Kontakt',fields:[
      {k:'first',l:'Ism',t:'text'},{k:'last',l:'Familiya',t:'text'},
      {k:'phone',l:'Telefon',t:'tel'},{k:'email',l:'Email',t:'email'}]},
    {id:'phone',icon:'📞',label:'Telefon',fields:[{k:'phone',l:'Raqam',t:'tel',p:'+998901234567'}]},
    {id:'sms',icon:'💬',label:'SMS',fields:[{k:'phone',l:'Telefon',t:'tel'},{k:'msg',l:'Xabar',t:'textarea'}]},
    {id:'email',icon:'✉️',label:'Email',fields:[
      {k:'to',l:'Kimga',t:'email'},{k:'subject',l:'Mavzu',t:'text'},{k:'body',l:'Xabar',t:'textarea'}]},
    {id:'tg',icon:'✈️',label:'Telegram',fields:[{k:'username',l:'Username',t:'text',p:'durov'}]},
    {id:'instagram',icon:'📸',label:'Instagram',fields:[{k:'username',l:'Username',t:'text'}]},
    {id:'youtube',icon:'▶️',label:'YouTube',fields:[{k:'url',l:'URL',t:'url'}]},
    {id:'tiktok',icon:'🎵',label:'TikTok',fields:[{k:'username',l:'Username',t:'text'}]},
    {id:'geo',icon:'📍',label:'Geo',fields:[
      {k:'lat',l:'Kenglik',t:'text',p:'41.311081'},{k:'lng',l:'Uzunlik',t:'text',p:'69.240562'}]},
    {id:'event',icon:'📅',label:'Tadbir',fields:[
      {k:'title',l:'Nomi',t:'text'},{k:'start',l:'Boshlanish',t:'text',p:'2025-12-31 18:00'}]},
    {id:'video',icon:'🎬',label:'Video',fields:[{k:'url',l:'Video URL (YouTube/MP4)',t:'url'}]},
    {id:'audio',icon:'🎧',label:'Audio',fields:[{k:'url',l:'Audio URL',t:'url'}]},
    {id:'pdf',icon:'📄',label:'PDF',fields:[{k:'url',l:'PDF URL',t:'url'}]},
    {id:'image',icon:'🖼️',label:'Rasm',fields:[{k:'url',l:'Rasm URL',t:'url'}]},
    {id:'app',icon:'📱',label:'Ilova',fields:[
      {k:'name',l:'Ilova nomi',t:'text'},{k:'url',l:'Yuklab olish URL',t:'url'}]},
    {id:'custom',icon:'⚙️',label:'Maxsus',fields:[{k:'raw',l:'Format',t:'textarea'}]},
  ],

  renderTypes() {
    document.getElementById('typeGrid').innerHTML = this.types.map(t =>
      `<button class="type-card" data-type="${t.id}">
        <span class="type-icon">${t.icon}</span>
        <span class="type-label">${t.label}</span></button>`).join('');
    document.querySelectorAll('.type-card').forEach(b => {
      b.onclick = () => this.openCreate(b.dataset.type); });
  },

  openCreate(id) {
    const t = this.types.find(x => x.id === id); if (!t) return;
    this.currentType = id;
    document.getElementById('createTitle').textContent = `${t.icon} ${t.label}`;
    document.getElementById('dynamicFields').innerHTML = t.fields.map(f => {
      let el;
      if (f.t === 'textarea') el = `<textarea class="textarea" id="f_${f.k}" placeholder="${f.p||''}"></textarea>`;
      else if (f.t === 'select') el = `<select class="select" id="f_${f.k}">${f.opts.map(o=>`<option>${o}</option>`).join('')}</select>`;
      else el = `<input class="input" type="${f.t}" id="f_${f.k}" placeholder="${f.p||''}">`;
      return `<div class="field"><label>${f.l}</label>${el}</div>`;
    }).join('');
    document.getElementById('qrResult').style.display = 'none';
    this.goPage('create');
  },

  buildPayload() {
    const v = id => (document.getElementById('f_' + id)?.value || '').trim();
    const enc = encodeURIComponent;
    const m = {
      universal: () => v('text'), text: () => v('text'), url: () => v('url'),
      wifi: () => `WIFI:T:${v('sec')||'WPA'};S:${v('ssid')};P:${v('pass')};;`,
      vcard: () => ['BEGIN:VCARD','VERSION:3.0',`N:${v('last')};${v('first')};;;`,
        `FN:${v('first')} ${v('last')}`.trim(),
        v('phone')?`TEL:${v('phone')}`:'', v('email')?`EMAIL:${v('email')}`:'',
        'END:VCARD'].filter(Boolean).join('\n'),
      phone: () => `tel:${v('phone')}`,
      sms: () => `SMSTO:${v('phone')}:${v('msg')}`,
      email: () => `mailto:${v('to')}?subject=${enc(v('subject'))}&body=${enc(v('body'))}`,
      tg: () => `https://t.me/${v('username').replace('@','')}`,
      instagram: () => `https://instagram.com/${v('username').replace('@','')}`,
      youtube: () => v('url'),
      tiktok: () => `https://tiktok.com/@${v('username').replace('@','')}`,
      geo: () => `geo:${v('lat')},${v('lng')}`,
      event: () => ['BEGIN:VEVENT',`SUMMARY:${v('title')}`,
        `DTSTART:${v('start').replace(/[-: ]/g,'')}`,'END:VEVENT'].join('\n'),
      video: () => v('url'), audio: () => v('url'),
      pdf: () => v('url'), image: () => v('url'),
      app: () => `APP:${v('name')}|URL:${v('url')}`,
      custom: () => v('raw'),
    };
    return (m[this.currentType] || (() => ''))();
  },

  async generate() {
    const data = this.buildPayload();
    if (!data) return this.toast("Ma'lumot kiriting", 'error');
    if (typeof QRCode === 'undefined') return this.toast("QR kutubxona yo'q", 'error');

    const size = parseInt(document.getElementById('qrSize').value);
    const fill = document.getElementById('fillColor').value;
    const back = document.getElementById('backColor').value;

    try {
      this.showLoading(true);
      const c = document.getElementById('qrContainer');
      c.innerHTML = '';
      const qrDiv = document.createElement('div');
      c.appendChild(qrDiv);

      new QRCode(qrDiv, {
        text: data, width: size, height: size,
        colorDark: fill, colorLight: back,
        correctLevel: QRCode.CorrectLevel.H
      });

      // Logo qo'yish
      if (this.logoData) {
        setTimeout(() => {
          const canvas = qrDiv.querySelector('canvas');
          if (!canvas) return;
          const ctx = canvas.getContext('2d');
          const img = new Image();
          img.onload = () => {
            const s = canvas.width;
            const logoSize = s * 0.22;
            const pad = s * 0.015;
            const x = (s - logoSize) / 2;
            const y = (s - logoSize) / 2;
            // Oq fon
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(x - pad, y - pad, logoSize + pad*2, logoSize + pad*2);
            ctx.drawImage(img, x, y, logoSize, logoSize);
          };
          img.src = this.logoData;
        }, 100);
      }

      this.currentData = data;
      document.getElementById('qrResult').style.display = 'block';
      document.getElementById('qrResult').scrollIntoView({ behavior: 'smooth' });
      this.toast('Yaratildi ✅', 'success');
    } catch (e) { this.toast('Xato: ' + e.message, 'error'); }
    finally { this.showLoading(false); }
  },

  download() {
    const canvas = document.querySelector('#qrContainer canvas');
    if (!canvas) return this.toast("QR yo'q", 'error');
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = `qrmaster-${Date.now()}.png`;
    a.click();
    this.toast('Yuklab olindi ✅', 'success');
  },

  async saveToHistory() {
    if (!this.currentData) return;
    try {
      this.showLoading(true);
      const res = await this.api('/api/qr/create', 'POST', {
        qr_type: this.currentType,
        name: this.types.find(t => t.id === this.currentType)?.label || 'QR',
        data: this.currentData
      });
      this.toast('✅ Saqlandi! Botda "📜 Mening QR larim" da ko\'ring', 'success');

      // Yangilash
      if (this.me) {
        this.me.qr_count = res.total_qr;
        this.updateStats();
      }
      await this.loadHistory();

      // Reklama kerakmi?
      if (res.show_ad) {
        this.showLoading(false);
        if (confirm('🎬 Bepul limit tugadi!\n\nReklama ko\'rib +3 QR unlock olasizmi?')) {
          this.showLoading(true);
          const watched = await AdManager.show();
          this.showLoading(false);
          if (watched) {
            const r = await this.api('/api/qr/ad_complete', 'POST', {});
            this.me.unlock_count = r.unlock;
            this.updateStats();
            this.toast('🎁 +3 QR unlock!', 'success');
          } else {
            this.toast("Reklama ko'rilmadi", 'error');
          }
        }
      }
    } catch (e) { this.toast(e.message, 'error'); }
    finally { this.showLoading(false); }
  },

  async loadHistory() {
    try {
      const list = await this.api('/api/qr/history');
      this.renderHistory(list); this.renderRecent(list);
    } catch (e) { console.warn(e); }
  },

  renderRecent(list) {
    const el = document.getElementById('recentList');
    const r = list.slice(0, 3);
    if (!r.length) { el.innerHTML = `<div class="empty"><span class="ico">🎯</span>Bo'sh</div>`; return; }
    el.innerHTML = r.map(h => `<div class="hist-item"><div class="hist-info">
      <h4>${h.name}</h4><p>${h.qr_type} · ${new Date(h.created_at).toLocaleString('uz')}</p>
    </div></div>`).join('');
  },

  renderHistory(list) {
    const el = document.getElementById('historyList');
    if (!list.length) { el.innerHTML = `<div class="empty"><span class="ico">🕐</span>Bo'sh</div>`; return; }
    el.innerHTML = list.map(h => `<div class="hist-item">
      <div class="hist-info">
        <h4>${h.name}</h4>
        <p>${h.qr_type} · ${new Date(h.created_at).toLocaleString('uz')}</p>
      </div>
      <button class="icon-btn" onclick="App.delQr(${h.id})">🗑</button>
    </div>`).join('');
  },

  async delQr(id) {
    if (!confirm("O'chirilsinmi?")) return;
    try {
      await this.api('/api/qr/' + id, 'DELETE');
      this.toast("O'chirildi", 'info');
      await this.loadHistory();
      if (this.me) { this.me.qr_count = Math.max(0, this.me.qr_count - 1); this.updateStats(); }
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async loadRefs() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (!u) return;
    const bot = this.me?.bot_username || 'SizningBotUsername';
    const link = `https://t.me/${bot}?start=ref_${u.id}`;
    document.getElementById('refLink').textContent = link;
    try {
      const data = await this.api('/api/ref/list');
      document.getElementById('refCount').textContent = data.total || 0;
      const el = document.getElementById('refList');
      if (!data.refs || !data.refs.length) {
        el.innerHTML = `<div class="empty"><span class="ico">👥</span>Referal yo'q</div>`;
      } else {
        el.innerHTML = data.refs.map(r => `<div class="hist-item">
          <div class="hist-info">
            <h4>${r.first_name || 'Foydalanuvchi'}</h4>
            <p>@${r.username || '—'} · ${(r.created_at||'').slice(0,10)}</p>
          </div>
        </div>`).join('');
      }
    } catch (e) { console.warn(e); }
  },

  bindRef() {
    document.getElementById('copyRef').onclick = async () => {
      const link = document.getElementById('refLink').textContent;
      try { await navigator.clipboard.writeText(link); this.toast('Nusxalandi 📋', 'success'); }
      catch { this.toast('Xato', 'error'); }
    };
    document.getElementById('shareRef').onclick = () => {
      const link = document.getElementById('refLink').textContent;
      window.open(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=QR Master`, '_blank');
    };
  },

  bindAds() {
    document.getElementById('watchAdBtn').onclick = async () => {
      this.showLoading(true);
      const ok = await AdManager.show();
      this.showLoading(false);
      if (ok) {
        try {
          const r = await this.api('/api/qr/ad_complete', 'POST', {});
          this.me.unlock_count = r.unlock;
          this.me.ad_count = (this.me.ad_count || 0) + 1;
          this.updateStats();
          this.toast('🎁 +3 QR unlock!', 'success');
        } catch (e) { this.toast(e.message, 'error'); }
      } else {
        this.toast("Reklama ko'rilmadi. Qayta urinib ko'ring", 'error');
      }
    };
    document.getElementById('inviteBtn').onclick = () => this.goPage('ref');
  },

  bindProfile() {
    document.getElementById('themeBtn').onclick = () => {
      const cur = document.documentElement.getAttribute('data-theme');
      document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
    };
  },

  bindForm() {
    document.getElementById('genBtn').onclick = () => this.generate();
    document.getElementById('backBtn').onclick = () => this.goPage('home');
    document.getElementById('dlBtn').onclick = () => this.download();
    document.getElementById('saveHistBtn').onclick = () => this.saveToHistory();

    // Logo yuklash
    document.getElementById('logoFile').onchange = (e) => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 500 * 1024) return this.toast('Fayl 500 KB dan oshmasin', 'error');
      const reader = new FileReader();
      reader.onload = (ev) => {
        this.logoData = ev.target.result;
        document.getElementById('logoPreview').src = ev.target.result;
        document.getElementById('clearLogo').style.display = 'block';
      };
      reader.readAsDataURL(f);
    };
    document.getElementById('clearLogo').onclick = () => {
      this.logoData = null;
      document.getElementById('logoPreview').src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='50' height='50'%3E%3Ctext x='50%25' y='55%25' text-anchor='middle' font-size='24' fill='%2364748b'%3E%2B%3C/text%3E%3C/svg%3E";
      document.getElementById('clearLogo').style.display = 'none';
    };
  },

  bindNav() {
    document.querySelectorAll('.nav-btn').forEach(b => {
      b.onclick = () => this.goPage(b.dataset.page);
    });
  },

  goPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById('page-' + name)?.classList.add('active');
    document.querySelectorAll('.nav-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.page === name));
    window.scrollTo({ top: 0 });
  },

  toast(msg, type = 'info') {
    const w = document.getElementById('toastWrap');
    const el = document.createElement('div');
    el.className = 'toast ' + type; el.textContent = msg;
    w.appendChild(el); setTimeout(() => el.remove(), 3500);
  },

  showLoading(on) { document.getElementById('loading').classList.toggle('on', on); }
};

window.addEventListener('DOMContentLoaded', () => App.init());
</script>
</body>
</html>"""
