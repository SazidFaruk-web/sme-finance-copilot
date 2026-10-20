// The closed price tab counts sharp moves the owner has not opened yet. Opening the drawer is the
// acknowledgement, so the number must clear and stay cleared until the published prices change.
import test from 'node:test';
import assert from 'node:assert/strict';

const node = (tag, attrs = {}) => {
  const classes = new Set(String(attrs.class || '').split(' ').filter(Boolean));
  const el = {
    tag, attrs, kids: [], id: attrs.id,
    classList: { toggle: (x, on) => (on ? classes.add(x) : classes.delete(x)), contains: x => classes.has(x) },
    appendChild(k) { el.kids.push(k); return k; },
    replaceChildren(...k) { el.kids = k.flat(Infinity).filter(x => x != null && x !== false); },
    setAttribute(k, v) { el.attrs[k] = v; },
    remove() {}, focus() {},
    querySelector(sel) { return find(el, sel); },
  };
  return el;
};
const find = (el, sel) => {
  for (const k of el.kids || []) {
    if (typeof k !== 'object' || k === null) continue;
    if (sel[0] === '#' ? k.id === sel.slice(1) : k.classList?.contains(sel.slice(1))) return k;
    const hit = find(k, sel);
    if (hit) return hit;
  }
  return null;
};
const h = (tag, attrs, ...kids) => { const el = node(tag, attrs || {}); el.replaceChildren(...kids); return el; };

function store() {
  const map = new Map();
  return { getItem: k => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)), map };
}

const item = (id, change) => ({
  id, label: { en: id }, unit: { en: 'kg' }, price: 100, observed: '2026-09', previous_month: '2026-08',
  change_1m_pct: change, change_1m_abs: change, change_12m_pct: change, history: [['2026-08', 98], ['2026-09', 100]],
  area: { level: 'district', name: 'Dhaka', markets: 3 }, forecast: null,
});
const prices = (month, items) => ({
  latest_observation: month, items, big_move_pct: 10, note: null,
  big_moves: items.filter(x => Math.abs(x.change_1m_pct) >= 10).length,
  engine: { kind: 'stat', name: 'stat' }, source: { url: 'https://example.org' }, watch: { source: 'rules', items: [] },
});

// The drawer reads document/localStorage as globals, so install the fakes before importing it.
const body = node('div');
globalThis.document = { body, createElementNS: () => node('svg'), addEventListener() {}, removeEventListener() {}, activeElement: null };
const { createMarketDrawer } = await import('../../frontend/market.js');

async function mounted(data, storage) {
  globalThis.localStorage = storage;
  body.kids = [];
  const drawer = createMarketDrawer({ h, S: { ui: 'en' }, api: async url => (url === '/api/market/prices' ? data : { items: [] }) });
  drawer.mount();
  await new Promise(r => setTimeout(r, 0));  // the background price load
  return { drawer, badge: () => find(body.kids[0], '.market-badge')?.kids.join('') ?? null };
}

test('opening the drawer clears the sharp-move count on the closed tab', async () => {
  const data = prices('2026-09', [item('flour', 12), item('sugar', -15), item('rice', 1)]);
  const { drawer, badge } = await mounted(data, store());
  assert.equal(badge(), '2');            // two items moved 10% or more, the tab says so
  drawer.redraw();
  assert.equal(badge(), '2');            // a redraw alone is not an acknowledgement
  find(body.kids[0], '.market-tab').attrs.onclick();
  assert.equal(badge(), null);           // open: the panel itself lists the moves
  find(body.kids[0], '.market-close').attrs.onclick();
  assert.equal(badge(), null);           // closed again, and the number is gone for good
});

test('the count stays cleared on the next visit but returns when the prices change', async () => {
  const storage = store();
  const data = prices('2026-09', [item('flour', 12), item('sugar', -15), item('rice', 1)]);
  const first = await mounted(data, storage);
  find(body.kids[0], '.market-tab').attrs.onclick();
  find(body.kids[0], '.market-close').attrs.onclick();
  assert.equal(first.badge(), null);

  assert.equal((await mounted(data, storage)).badge(), null);  // same prices, already seen
  assert.equal((await mounted(prices('2026-10', [item('flour', 12), item('sugar', -15), item('rice', 1)]), storage)).badge(), '2');  // new month
  assert.equal((await mounted(prices('2026-09', [item('flour', 12), item('onion', -22), item('rice', 1)]), storage)).badge(), '2');  // a different item moved
});

test('a blocked store still clears the count for the rest of the session', async () => {
  const blocked = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  const { badge } = await mounted(prices('2026-09', [item('flour', 12), item('sugar', -15)]), blocked);
  assert.equal(badge(), '2');
  find(body.kids[0], '.market-tab').attrs.onclick();
  find(body.kids[0], '.market-close').attrs.onclick();
  assert.equal(badge(), null);
});
