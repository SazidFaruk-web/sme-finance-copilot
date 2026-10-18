import test from 'node:test';
import assert from 'node:assert/strict';
import { ZH, zh, zhCopy } from '../../frontend/i18n-zh.js';
import { AUTH_COPY } from '../../frontend/auth-copy.js';

const HAN = /[一-鿿]/;

test('Chinese login and account creation cover every message, with no English left in the copy', () => {
  assert.deepEqual(Object.keys(AUTH_COPY.zh).sort(), Object.keys(AUTH_COPY.en).sort());
  for (const [key, message] of Object.entries(AUTH_COPY.zh)) {
    assert.match(message, HAN, `${key} is not translated`);
    assert.doesNotMatch(message, /[A-Za-z]{3,}/, `${key} still contains English: ${message}`);
  }
});

test('lookups keep surrounding whitespace and leave unknown or user text unchanged', () => {
  assert.equal(zh('Home'), '首页');
  assert.equal(zh('  Gross profit'), '  毛利');
  assert.equal(zh('Rina Traders'), 'Rina Traders');
  assert.equal(zh(''), '');
  assert.equal(zh(42), 42);
});

test('templated sentences translate and keep their values', () => {
  assert.equal(zh('12 days late'), '逾期 12 天');
  assert.equal(zh('Partial payment saved · ৳1,200 still due'), '已保存部分付款 · 仍欠 ৳1,200');
  assert.equal(zh('October 2026 (to date)'), '2026年10月（截至目前）');
  assert.equal(zh('Profit & loss · October 2026 (to date)'), '损益 · 2026年10月（截至目前）');
  assert.equal(zh('rina · update home layout'), 'rina · 更新首页布局');
  assert.equal(zh('Cash basis. Not counted in profit: none'), '现金制。未计入利润：无');
});

test('copy tables translate strings, arrays and functions', () => {
  const copy = zhCopy({ title: 'Your tasks', steps: ['Check bills', 'View records'], count: n => (n ? 'Show more' : 'Nothing yet.') });
  assert.equal(copy.title, '您的任务');
  assert.deepEqual(copy.steps, ['检查账单', '查看记录']);
  assert.equal(copy.count(1), '显示更多');
});

test('every dictionary entry has a Chinese translation', () => {
  const brandsAndCodes = /^(English|Nagad|Rocket|中文|⇩ CSV|⇩ PDF)$/;
  for (const [en, value] of Object.entries(ZH)) {
    assert.ok(value && value.trim(), `empty translation for ${en}`);
    if (!brandsAndCodes.test(en)) assert.match(value, HAN, `no Chinese for "${en}"`);
  }
});
