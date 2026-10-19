// One settings destination at a time. No account, business or reminder writes on page open.
const COPY = {
  title: ["Settings", "সেটিংস", "设置"], intro: ["Make the app work for you.", "অ্যাপটি আপনার সুবিধামতো সাজান।", "让应用更适合您。"],
  back: ["All settings", "সব সেটিংস", "全部设置"], appearance: ["Appearance & language", "রং ও ভাষা", "外观与语言"],
  appearanceHint: ["Choose a comfortable look and language.", "আপনার সুবিধার রং ও ভাষা বাছুন।", "选择舒适的外观和语言。"],
  business: ["Your business", "আপনার ব্যবসা", "您的生意"], businessHint: ["Business details, starting money and setup.", "ব্যবসার তথ্য, শুরুর টাকা ও সেটআপ।", "商家资料、期初资金与设置。"],
  reminders: ["Reminders", "রিমাইন্ডার", "提醒"], remindersHint: ["Choose how to hear about important dates.", "জরুরি তারিখ কীভাবে মনে করিয়ে দেব তা বাছুন।", "选择如何接收重要日期提醒。"],
  privacy: ["Privacy & data", "গোপনীয়তা ও তথ্য", "隐私与数据"], privacyHint: ["Understand, download or manage your records.", "আপনার তথ্য সম্পর্কে জানুন ও কপি নামান।", "了解、下载或管理您的记录。"],
  owner: ["Business owner", "ব্যবসার মালিক", "店主"], accountant: ["Bookkeeper", "হিসাবরক্ষক", "记账员"], viewer: ["Read-only access", "শুধু দেখার অনুমতি", "只读权限"],
  help: ["Get help", "সাহায্য নিন", "获取帮助"], tour: ["Take a quick tour", "অ্যাপটি চিনে নিন", "快速导览"], logout: ["Log out", "লগ আউট", "退出登录"],
  theme: ["Light or dark", "লাইট বা ডার্ক", "浅色或深色"], themeHint: ["Pick what is easiest on your eyes.", "চোখের জন্য আরামদায়ক রং বাছুন।", "选择看起来更舒适的外观。"],
  light: ["Light", "লাইট", "浅色"], dark: ["Dark", "ডার্ক", "深色"], system: ["Same as device", "ডিভাইসের মতো", "跟随设备"],
  languages: ["More languages", "আরও ভাষা", "更多语言"], languagesHint: ["Show বাংলা and 中文 as language choices.", "ভাষার তালিকায় বাংলা ও চীনা দেখান।", "显示孟加拉语和中文选项。"], language: ["Language", "ভাষা", "语言"],
  device: ["Appearance and language are saved on this device.", "রং ও ভাষার পছন্দ এই ডিভাইসে থাকে।", "外观与语言偏好保存在此设备上。"],
  extra: ["More appearance options", "রং ও দেখার আরও পছন্দ", "更多外观选项"], style: ["Style", "স্টাইল", "风格"],
  styleHint: ["Change the accent colour.", "মূল রং বদলান।", "更换主题配色。"], general: ["Warm", "উষ্ণ", "暖色"], sky: ["Blue", "নীল", "蓝色"], classic: ["Green", "সবুজ", "绿色"],
  mode: ["App view", "অ্যাপের ধরন", "应用视图"], modeHint: ["Simple keeps everyday tasks easy to find.", "সহজ ভিউতে প্রতিদিনের কাজ সহজে খুঁজে পাবেন।", "简洁视图让日常任务更容易找到。"], simple: ["Simple (recommended)", "সহজ (পরামর্শকৃত)", "简洁（推荐）"], advanced: ["Advanced", "বিস্তারিত", "详细"],
  numbers: ["Number format", "সংখ্যার ধরন", "数字格式"], numbersHint: ["How amounts appear for your business.", "ব্যবসার টাকার পরিমাণ যেভাবে দেখাবে।", "选择商家金额的显示格式。"],
  setup: ["Business setup", "ব্যবসার সেটআপ", "商家设置"],
  buffer: ["Low-money warning", "টাকা কমার সতর্কতা", "资金不足提醒"], bufferHint: ["Warn me if expected money falls below this amount.", "সম্ভাব্য টাকা এই পরিমাণের নিচে নামলে জানাবেন।", "预计资金低于此金额时提醒我。"], amount: ["Amount (৳)", "পরিমাণ (৳)", "金额（৳）"],
  save: ["Save changes", "পরিবর্তন সেভ করুন", "保存更改"], saving: ["Saving…", "সেভ হচ্ছে…", "正在保存…"], saved: ["Changes saved.", "পরিবর্তন সেভ হয়েছে।", "更改已保存。"], failed: ["Couldn't save. Check your connection and try again.", "সেভ হয়নি। সংযোগ দেখে আবার চেষ্টা করুন।", "无法保存。请检查网络后重试。"],
  ownerOnly: ["Only the business owner can change this.", "শুধু ব্যবসার মালিক এটি বদলাতে পারেন।", "只有店主可以更改此项。"],
  inApp: ["Your saved reminders are available in the app. The owner manages SMS preferences.", "সেভ করা রিমাইন্ডার অ্যাপে পাবেন। এসএমএসের পছন্দ মালিক ঠিক করেন।", "已保存的提醒可在应用中查看。短信偏好由店主管理。"],
  appReminders: ["In-app reminders", "অ্যাপের রিমাইন্ডার", "应用内提醒"], available: ["Saved reminders appear when you return to the app.", "অ্যাপে ফিরলে সেভ করা রিমাইন্ডার পাবেন।", "返回应用即可查看已保存的提醒。"], sms: ["SMS reminders (optional)", "এসএমএস রিমাইন্ডার (ইচ্ছামতো)", "短信提醒（可选）"],
  info: ["You control your information", "আপনার তথ্যের নিয়ন্ত্রণ আপনার হাতে", "您的信息由您掌控"],
  infoHint: ["The app uses the records you add. It does not connect to your bank automatically.", "আপনার যোগ করা হিসাবই অ্যাপ ব্যবহার করে। নিজে থেকে ব্যাংকে যুক্ত হয় না।", "应用使用您添加的记录，不会自动连接银行。"],
  usage: ["How your information is used", "আপনার তথ্য যেভাবে ব্যবহার হয়", "信息如何被使用"],
  local: ["Your AI questions are handled by the server's local model.", "আপনার প্রশ্ন সার্ভারের স্থানীয় এআই মডেল দেখে।", "您的问题由服务器的本地模型处理。"],
  cloud: ["Your AI questions are sent to the configured cloud model.", "আপনার প্রশ্ন নির্ধারিত ক্লাউড এআই মডেলে পাঠানো হয়।", "您的问题会发送至已配置的云端模型。"],
  masking: ["Phone and account numbers are masked in text sent to cloud models.", "ক্লাউড মডেলে পাঠানো লেখায় ফোন ও হিসাব নম্বর আড়াল করা হয়।", "发送至云端模型的文字会隐藏电话和账户号码。"],
  noMasking: ["Text masking for cloud models is turned off on this server.", "এই সার্ভারে ক্লাউডে পাঠানো লেখার নম্বর আড়াল করা বন্ধ আছে।", "此服务器未启用云端文字脱敏。"],
  sharing: ["Customer messages stay as drafts. Sending an owner SMS needs consent, verification and provider setup.", "ক্রেতার বার্তা খসড়া থাকে। মালিককে এসএমএস দিতে সম্মতি, যাচাই ও সেবা সেটআপ লাগে।", "客户消息保留为草稿。店主短信须经同意、号码验证并配置服务。"],
  history: ["Recent account activity", "অ্যাকাউন্টের সাম্প্রতিক কাজ", "最近账户活动"], empty: ["No recent activity.", "সাম্প্রতিক কোনো কাজ নেই।", "暂无最近活动。"],
  export: ["Download my records", "আমার হিসাবের কপি নামান", "下载我的记录"], exportHint: ["Keep a copy of your business records and saved tasks.", "ব্যবসার হিসাব ও সেভ করা কাজের একটি কপি রাখুন।", "保留商家记录与已保存任务的副本。"], exportType: ["Downloads a JSON data file.", "তথ্যের একটি জেসন ফাইল নামবে।", "下载为 JSON 数据文件。"],
  downloading: ["Preparing your download…", "কপি প্রস্তুত হচ্ছে…", "正在准备下载…"], downloaded: ["Your download is ready.", "আপনার কপি প্রস্তুত।", "下载已准备好。"],
  downloadFailed: ["Couldn't download. Check your connection and try again.", "কপি নামেনি। সংযোগ দেখে আবার চেষ্টা করুন।", "无法下载。请检查网络后重试。"], loadFailed: ["Couldn't load. Check your connection and try again.", "তথ্য আনা যায়নি। সংযোগ দেখে আবার চেষ্টা করুন।", "无法加载。请检查网络后重试。"],
  danger: ["Delete business data", "ব্যবসার তথ্য মুছুন", "删除商家数据"], dangerHint: ["This permanently removes your records and closes this business's accounts. A masked activity log is kept.", "এতে হিসাব স্থায়ীভাবে মুছে যায় ও ব্যবসার অ্যাকাউন্ট বন্ধ হয়। নম্বর আড়াল করা কাজের ইতিহাস রাখা হয়।", "这将永久删除记录并关闭该商家的账户。脱敏活动日志会保留。"],
  password: ["Your password", "আপনার পাসওয়ার্ড", "您的密码"], confirm: ["Type DELETE MY DATA to confirm", "নিশ্চিত করতে DELETE MY DATA লিখুন", "输入 DELETE MY DATA 以确认"], cancel: ["Cancel", "বাতিল", "取消"],
  deleting: ["Deleting…", "মুছে ফেলা হচ্ছে…", "正在删除…"], deleteFailed: ["Deletion was not confirmed. Check your password and connection.", "মুছে ফেলা নিশ্চিত হয়নি। পাসওয়ার্ড ও সংযোগ দেখুন।", "未能确认删除。请检查密码和网络。"],
};
const opened = new Set();

export async function renderSettings(host, ctx) {
  const { h, icon, api, S, setPref } = ctx;
  const lang = { bn: 1, zh: 2 }[S.ui] || 0, c = key => COPY[key][lang];
  const section = new URLSearchParams(location.hash.split('?')[1] || '').get('section');
  const root = h('div', { class: 'settings-page' }); host.replaceChildren(root);
  queueMicrotask(() => { if (root.isConnected) root.querySelector('h1')?.focus(); });
  const button = (text, onclick, attrs = {}) => h('button', { type: 'button', class: 'btn', onclick, ...attrs }, text);
  const note = text => h('p', { class: 'settings-note' }, text);
  const details = (key, title, ...children) => h('details', { class: 'settings-disclosure', open: opened.has(`${S.user.id}:${key}`), ontoggle: e => {
    const id = `${S.user.id}:${key}`; if (e.currentTarget.open) opened.add(id); else opened.delete(id);
  } }, h('summary', {}, title), h('div', { class: 'settings-disclosure-body' }, children));
  const select = (label, value, options, change, attrs = {}) => h('select', { 'aria-label': label, onchange: e => change(e.target.value, e.target), ...attrs },
    options.map(([v, text]) => h('option', { value: v, selected: value === v }, text)));
  const field = (title, hint, control) => h('label', { class: 'settings-field' }, h('span', { class: 'settings-field-copy' }, h('span', { class: 'settings-label' }, title), hint ? h('span', { class: 'settings-note' }, hint) : null), control);
  const heading = (title, hint) => h('div', { class: 'settings-heading' }, h('h1', { tabindex: -1 }, title), hint ? note(hint) : null);
  const routes = [['appearance', 'sun'], ['business', 'book'], ['reminders', 'bell'], ['privacy', 'check']];
  if (!routes.some(([id]) => id === section)) {
    root.append(heading(c('title'), c('intro')),
      h('nav', { class: 'settings-list', 'aria-label': c('title') }, routes.map(([id, glyph]) => h('a', {
        class: 'settings-link', href: `#settings?section=${id}${id === 'reminders' ? '&tab=notifications' : ''}`,
      }, h('span', { class: 'settings-link-icon' }, icon(glyph)), h('span', { class: 'settings-link-copy' }, h('span', { class: 'settings-label' }, c(id)), h('span', { class: 'settings-note' }, c(`${id}Hint`))), h('span', { class: 'settings-chevron', 'aria-hidden': 'true' }, '›')))),
      h('div', { class: 'settings-account' }, h('span', { class: 'settings-account-avatar', 'aria-hidden': 'true' }, (S.user.full_name || S.user.username).trim().slice(0, 1)),
        h('div', {}, h('strong', {}, S.user.full_name || S.user.username), note(`${S.user.business_name || ''} · ${c(S.user.role)}`)), button(c('logout'), ctx.onLogout, { class: 'btn ghost' })),
      h('div', { class: 'settings-help' }, h('a', { href: '#chat?tab=help' }, c('help')), button(c('tour'), ctx.onTour, { class: 'text-link' })));
    return;
  }
  root.append(h('a', { class: 'settings-back', href: '#settings' }, h('span', { 'aria-hidden': 'true' }, '←'), c('back')));
  root.append(heading(c(section), c(`${section}Hint`)));

  if (section === 'appearance') {
    const theme = select(c('theme'), S.theme, [['light', c('light')], ['dark', c('dark')], ['system', c('system')]], v => setPref('theme', v), { 'data-theme-select': '' });
    root.append(h('section', { class: 'settings-surface' }, field(c('theme'), c('themeHint'), theme)));
    if ((S.health.languages || ['en']).length > 1) {
      root.append(h('section', { class: 'settings-surface' }, field(c('languages'), c('languagesHint'), h('input', { type: 'checkbox', role: 'switch', 'aria-label': c('languages'), checked: ctx.moreLanguages(), onchange: e => {
        ctx.setMoreLanguages(e.target.checked); setPref('ui', e.target.checked ? S.ui : 'en');
      } })), ctx.moreLanguages() ? field(c('language'), '', select(c('language'), S.ui, ctx.langs(), v => setPref('ui', v))) : null));
    }
    const status = h('p', { class: 'settings-note', role: 'status' });
    root.append(note(c('device')), details('appearance', c('extra'),
      field(c('style'), c('styleHint'), select(c('style'), S.look, [['general', c('general')], ['sky', c('sky')], ['classic', c('classic')]], v => setPref('look', v))),
      field(c('mode'), c('modeHint'), select(c('mode'), S.mode, [['simple', c('simple')], ['advanced', c('advanced')]], v => setPref('mode', v))),
      field(c('numbers'), c('numbersHint'), select(c('numbers'), S.style, [['lakh', '1,00,000'], ['intl', '100,000']], async (value, input) => {
        input.disabled = true; status.textContent = c('saving');
        try { const saved = await api('/api/settings', { method: 'PATCH', body: { number_style: value } }); S.style = saved.number_style; status.textContent = c('saved'); }
        catch { input.value = S.style; status.textContent = c('failed'); }
        finally { input.disabled = false; }
      }, { disabled: S.user.max_tier < 1 })), S.user.max_tier < 1 ? note(c('viewer')) : null, status));
    return;
  }
  if (section === 'business') { root.append(ctx.businessCard(), details('setup', c('setup'), ctx.homeLayoutCard())); return; }
  if (section === 'reminders') {
    root.append(h('section', { class: 'settings-surface settings-padding' }, h('h2', {}, c('appReminders')), note(c(S.user.role === 'owner' ? 'available' : 'inApp'))));
    if (S.user.role === 'owner') {
      const panel = h('div'), sms = details('sms', c('sms'), panel);
      let loaded = false;
      const load = async () => { if (!sms.open || loaded) return; loaded = true; await ctx.reminderPanel(panel); };
      sms.addEventListener('toggle', load); root.append(sms); await load();
    }
    const st = await api('/api/settings'), status = h('p', { class: 'settings-note', role: 'status' });
    const amount = h('input', { id: 'settings-buffer', type: 'number', min: 0, max: 1e9, step: 1, value: st.low_balance_threshold, disabled: S.user.max_tier < 1 });
    const save = h('button', { type: 'submit', class: 'btn primary', disabled: S.user.max_tier < 1 }, c('save'));
    root.append(details('buffer', c('buffer'), h('form', { onsubmit: async e => {
      e.preventDefault(); save.disabled = true; status.textContent = c('saving');
      try { await api('/api/settings', { method: 'PATCH', body: { low_balance_threshold: Number(amount.value) } }); status.textContent = c('saved'); }
      catch { status.textContent = c('failed'); } finally { save.disabled = S.user.max_tier < 1; }
    } }, note(c('bufferHint')), h('label', { class: 'field', for: 'settings-buffer' }, c('amount'), amount), save, status)));
    return;
  }
  const profile = (S.models?.profiles || []).find(p => p.name === S.profile), local = S.models?.local_only_mode || profile?.external === false;
  const usage = details('usage', c('usage'), note(c(local ? 'local' : 'cloud')), note(c(S.models?.mask_pii ? 'masking' : 'noMasking')), note(c('sharing')));
  const activity = details('activity', c('history'), note('…'));
  activity.addEventListener('toggle', async () => {
    if (!activity.open || activity.dataset.loaded) return;
    activity.dataset.loaded = 'true';
    try {
      const recent = await api('/api/privacy/recent'), body = activity.lastElementChild;
      body.replaceChildren(recent.length ? h('ul', { class: 'settings-activity' }, recent.map(e => h('li', {}, h('time', {}, e.ts.replace('T', ' ')), h('span', {}, e.actor), h('span', {}, e.action.replace(/_/g, ' '))))) : note(c('empty')));
    } catch { activity.lastElementChild.replaceChildren(note(c('loadFailed'))); delete activity.dataset.loaded; }
  });
  root.append(h('section', { class: 'settings-surface settings-padding' }, h('h2', {}, c('info')), note(c('infoHint')), usage, activity));
  if (S.user.role !== 'owner') { root.append(note(c('ownerOnly'))); return; }
  const status = h('p', { class: 'settings-note', role: 'status' });
  root.append(h('section', { class: 'settings-surface settings-padding' }, h('h2', {}, c('export')), note(c('exportHint')),
    button(c('export'), async e => {
      e.currentTarget.disabled = true; status.textContent = c('downloading');
      try { await ctx.onExport(); status.textContent = c('downloaded'); } catch { status.textContent = c('downloadFailed'); }
      finally { if (e.target.isConnected) e.target.closest('button').disabled = false; }
    }), note(c('exportType')), status));
  root.append(details('delete', c('danger'), note(c('dangerHint')), button(c('danger'), () => {
    const password = h('input', { id: 'settings-delete-password', type: 'password', autocomplete: 'current-password', required: true });
    const phrase = h('input', { id: 'settings-delete-confirm', autocomplete: 'off', required: true, pattern: 'DELETE MY DATA' });
    const message = h('p', { role: 'status', class: 'settings-note' });
    const submit = h('button', { type: 'submit', class: 'btn danger' }, c('danger'));
    const form = h('form', { class: 'settings-delete-form', onsubmit: async e => {
      e.preventDefault(); if (!form.reportValidity()) return; submit.disabled = true; message.textContent = c('deleting');
      try { await api('/api/privacy/delete', { body: { password: password.value, confirm: phrase.value } }); password.value = ''; dialog.remove(); ctx.onDeleted(); }
      catch { message.textContent = c('deleteFailed'); submit.disabled = false; }
    } }, note(c('dangerHint')), h('label', { class: 'field', for: password.id }, c('password'), password), h('label', { class: 'field', for: phrase.id }, c('confirm'), phrase),
      h('div', { class: 'row' }, button(c('cancel'), () => dialog.remove()), submit), message);
    const dialog = ctx.modal(c('danger'), form);
    password.focus();
  }, { class: 'btn danger' })));
}
