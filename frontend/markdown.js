// Small, DOM-only Markdown renderer for assistant replies. Raw HTML stays text.
// No innerHTML, external images, plugins or model-provided executable attributes.
const node = (tag, text) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  return el;
};
const safeLink = value => {
  const url = value.trim();
  if (/[\u0000-\u0020\u007f]/.test(url)) return null;
  if (/^(https?:\/\/|mailto:)/i.test(url) || /^#[\w/?=&%.-]*$/.test(url) || /^\/(?!\/)/.test(url)) return url;
  return null;
};

function inline(parent, text, depth = 0) {
  if (depth > 10) { parent.append(document.createTextNode(text)); return; }
  const pattern = /\\([\\`*_[\]{}()#+.!|>~-])|(`+)([\s\S]*?)\2|!\[([^\]]*)\]\([^\n]*?\)|\[([^\]]+)\]\(([^\s)]+)(?:\s+"[^"]*")?\)|<(https?:\/\/[^>\s]+)>|(\*\*|__)(?=\S)([\s\S]*?\S)\8|(\*|(?<![\p{L}\p{N}])_)(?=\S)([^\n]+?)\10|~~(?=\S)(.*?\S)~~/gu;
  let end = 0, m;
  while ((m = pattern.exec(text))) {
    if (m.index > end) parent.append(document.createTextNode(text.slice(end, m.index)));
    if (m[1]) parent.append(document.createTextNode(m[1]));
    else if (m[2]) parent.append(node('code', m[3].replace(/\n/g, ' ')));
    else if (m[4] !== undefined) parent.append(document.createTextNode(m[4])); // never fetch model images
    else if (m[5] || m[7]) {
      const label = m[5] || m[7], href = safeLink(m[6] || m[7]);
      if (href) {
        const a = node('a'); a.setAttribute('href', href);
        if (/^https?:/i.test(href)) { a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener noreferrer'); }
        inline(a, label, depth + 1); parent.append(a);
      } else inline(parent, label, depth + 1);
    } else {
      const el = node(m[8] ? 'strong' : m[10] ? 'em' : 'del');
      inline(el, m[9] || m[11] || m[12], depth + 1); parent.append(el);
    }
    end = pattern.lastIndex;
  }
  if (end < text.length) parent.append(document.createTextNode(text.slice(end)));
}

function cells(line) {
  const source = line.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '');
  const result = []; let cell = '', ticks = 0;
  for (let i = 0; i < source.length; i++) {
    if (source[i] === '\\' && i + 1 < source.length) { cell += source[i] + source[++i]; continue; }
    if (source[i] === '`') {
      let n = 1; while (source[i + n] === '`') n++;
      if (!ticks) ticks = n; else if (ticks === n) ticks = 0;
      cell += '`'.repeat(n); i += n - 1; continue;
    }
    if (source[i] === '|' && !ticks) { result.push(cell.trim()); cell = ''; }
    else cell += source[i];
  }
  result.push(cell.trim()); return result;
}
const divider = line => /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
const listRow = line => line.match(/^(\s*)([-+*]|\d+[.)])\s+(.+)$/);
const blockStart = line => /^(?:\s*#{1,6}\s|\s*```|\s*~~~|\s*>|\s*(?:[-+*]|\d+[.)])\s+)/.test(line);

function blocks(lines, parent, depth = 0) {
  if (depth > 12) { parent.append(node('p', lines.join('\n'))); return; }
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = line.match(/^\s*(`{3,}|~{3,})([^\s`]*)\s*$/);
    if (fence) {
      const content = []; i++;
      while (i < lines.length && !new RegExp('^\\s*' + fence[1][0] + '{' + fence[1].length + ',}\\s*$').test(lines[i])) content.push(lines[i++]);
      if (i < lines.length) i++;
      const pre = node('pre'), code = node('code', content.join('\n'));
      if (/^[\w+-]{1,30}$/.test(fence[2])) code.setAttribute('data-language', fence[2]);
      pre.append(code); parent.append(pre); continue;
    }
    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) { const h = node('h' + Math.min(6, heading[1].length + 2)); inline(h, heading[2]); parent.append(h); i++; continue; }
    if (/^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$/.test(line)) { parent.append(node('hr')); i++; continue; }
    if (/^\s*>/.test(line)) {
      const quoted = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quoted.push(lines[i++].replace(/^\s*>\s?/, ''));
      const quote = node('blockquote'); blocks(quoted, quote, depth + 1); parent.append(quote); continue;
    }
    if (i + 1 < lines.length && line.includes('|') && divider(lines[i + 1])) {
      const wrap = node('div'), table = node('table'), head = node('thead'), tr = node('tr'), body = node('tbody');
      wrap.className = 'markdown-table'; wrap.setAttribute('tabindex', '0'); wrap.setAttribute('role', 'region');
      const headers = cells(line); wrap.setAttribute('aria-label', headers.join(' / '));
      for (const label of headers) { const th = node('th'); th.setAttribute('scope', 'col'); inline(th, label); tr.append(th); }
      head.append(tr); i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        const row = node('tr'), values = cells(lines[i++]);
        for (let n = 0; n < headers.length; n++) { const td = node('td'); inline(td, values[n] || ''); row.append(td); }
        body.append(row);
      }
      table.append(head, body); wrap.append(table); parent.append(wrap); continue;
    }
    const first = listRow(line);
    if (first) {
      const indent = first[1].length, ordered = /^\d/.test(first[2]), list = node(ordered ? 'ol' : 'ul');
      if (ordered && parseInt(first[2], 10) !== 1) list.setAttribute('start', String(parseInt(first[2], 10)));
      while (i < lines.length) {
        const match = listRow(lines[i]);
        if (!match || match[1].length !== indent || /^\d/.test(match[2]) !== ordered) break;
        const li = node('li'); let content = match[3]; i++;
        const task = content.match(/^\[([ xX])\]\s+(.*)$/);
        if (task) { content = (task[1].toLowerCase() === 'x' ? '☑ ' : '☐ ') + task[2]; }
        inline(li, content);
        const nested = [];
        while (i < lines.length && lines[i].trim() && lines[i].match(/^\s*/)[0].length > indent) {
          const leading = lines[i].match(/^\s*/)[0].length;
          nested.push(lines[i].slice(Math.min(indent + 2, leading))); i++;
        }
        if (nested.length) blocks(nested, li, depth + 1);
        list.append(li);
        if (i < lines.length && !lines[i].trim() && listRow(lines[i + 1] || '')?.[1].length === indent) i++;
      }
      parent.append(list); continue;
    }
    if (i + 1 < lines.length && /^\s*(?:={3,}|-{3,})\s*$/.test(lines[i + 1])) {
      const h = node(/^\s*=/.test(lines[i + 1]) ? 'h3' : 'h4'); inline(h, line.trim()); parent.append(h); i += 2; continue;
    }
    const text = [line]; i++;
    while (i < lines.length && lines[i].trim() && !blockStart(lines[i]) && !(i + 1 < lines.length && divider(lines[i + 1]))) text.push(lines[i++]);
    const p = node('p');
    text.forEach((part, n) => { if (n) p.append(node('br')); inline(p, part.replace(/\s{2}$/, '')); });
    parent.append(p);
  }
}

export function renderMarkdown(text) {
  const root = node('div'); root.className = 'markdown';
  blocks(String(text ?? '').replace(/\r\n?/g, '\n').split('\n'), root);
  return root;
}
export function updateMarkdown(host, text) {
  host.classList.add('markdown');
  host.replaceChildren(...renderMarkdown(text).childNodes);
}
