import test from 'node:test';
import assert from 'node:assert/strict';
import { renderMarkdown, updateMarkdown } from '../../frontend/markdown.js';

class Element {
  constructor(tag, value = '') { this.tag = tag; this.value = value; this.childNodes = []; this.attributes = {}; this.className = ''; this.classList = { add: name => { this.className += ' ' + name; } }; }
  append(...nodes) { this.childNodes.push(...nodes); }
  setAttribute(key, value) { this.attributes[key] = value; }
  replaceChildren(...nodes) { this.childNodes = nodes; }
  set textContent(text) { this.value = text; this.childNodes = []; }
  get textContent() { return this.value + this.childNodes.map(x => x.textContent).join(''); }
}
globalThis.document = { createElement: tag => new Element(tag), createTextNode: text => new Element('#text', text) };
const find = (root, tag) => [...(root.tag === tag ? [root] : []), ...root.childNodes.flatMap(x => find(x, tag))];

test('headings, bold, lists, nested lists and Bangla money render as semantic elements', () => {
  const root = renderMarkdown('## Your plan\n\n**Keep bills safe**\n\n1. Check ৳৫,০০০\n2. Compare quotes\n   - Delivery\n   - Storage\n\n> Keep a reserve.');
  assert.equal(find(root, 'h4')[0].textContent, 'Your plan');
  assert.equal(find(root, 'strong')[0].textContent, 'Keep bills safe');
  assert.equal(find(root, 'ol').length, 1); assert.equal(find(root, 'ul').length, 1);
  assert.equal(find(root, 'li').length, 4); assert.ok(root.textContent.includes('৳৫,০০০'));
  assert.equal(find(root, 'blockquote').length, 1);
});

test('tables retain header semantics, money, inline code pipes and escaped pipes', () => {
  const root = renderMarkdown('| Option | Cost |\n| --- | ---: |\n| **Small** | ৳500 |\n| `a|b` | 20 \\| 30 |');
  assert.equal(find(root, 'table').length, 1);
  assert.equal(find(root, 'th').length, 2); assert.equal(find(root, 'td').length, 4);
  assert.equal(find(root, 'th')[0].attributes.scope, 'col');
  assert.equal(find(root, 'code')[0].textContent, 'a|b');
  assert.equal(find(root, 'td')[3].textContent, '20 | 30');
});

test('raw HTML and unsafe URLs cannot execute and images never fetch', () => {
  const root = renderMarkdown('<img src=x onerror=alert(1)>\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1)) [data](data:text/html,abc) ![remote](https://tracking.test/image) [official](https://example.gov.bd/rules)');
  assert.equal(find(root, 'script').length, 0); assert.equal(find(root, 'img').length, 0);
  const links = find(root, 'a'); assert.equal(links.length, 1);
  assert.equal(links[0].attributes.href, 'https://example.gov.bd/rules');
  assert.equal(links[0].attributes.rel, 'noopener noreferrer');
  assert.ok(root.textContent.includes('<script>'));
});

test('streaming partial text is replaced cleanly by completed formatting', () => {
  const host = new Element('div'); updateMarkdown(host, '**Starting');
  assert.ok(host.textContent.includes('**Starting'));
  updateMarkdown(host, '**Starting point**\n\n- Ask for a quote.');
  assert.equal(find(host, 'strong')[0].textContent, 'Starting point');
  assert.equal(find(host, 'li').length, 1); assert.ok(!host.textContent.includes('**'));
});

test('fenced code preserves literal Markdown and HTML, even before closing fence arrives', () => {
  const root = renderMarkdown('```text\n**literal**\n<script>literal</script>');
  assert.equal(find(root, 'pre').length, 1);
  assert.equal(find(root, 'strong').length, 0); assert.equal(find(root, 'script').length, 0);
  assert.equal(find(root, 'code')[0].textContent, '**literal**\n<script>literal</script>');
});
