import test from 'node:test';
import assert from 'node:assert/strict';
import { buildGuidance, upcomingItems } from '../../frontend/guidance.js';

const base = { asOf: '2026-10-17', recordCount: 20, canWrite: true };
const alert = (id, kind, extra = {}) => ({ id, kind, title: `Recorded issue ${id}`, message: 'Source evidence', severity: 'warning', status: 'open', data: {}, ...extra });

test('cash risk is prioritized over overdue collections and routine spending', () => {
  const g = buildGuidance({ ...base, alerts: [alert(1, 'spending_spike'), alert(2, 'overdue_invoice'), alert(3, 'low_balance', { severity: 'critical' })] });
  assert.equal(g.primary.id, 3);
  assert.deepEqual(g.tasks.map(t => t.id), [3, 2, 1]);
  assert.equal(g.primary.action.href, '#chat');
  assert.match(g.primary.question, /Source evidence/);
});

test('personal reminders stay out of urgent tasks until their due date', () => {
  const today = alert(1, 'custom', { due_date: base.asOf, severity: 'info' });
  const future = alert(2, 'custom', { due_date: '2026-10-19', severity: 'info' });
  const g = buildGuidance({ ...base, alerts: [future, today, alert(3, 'payable_due')] });
  assert.equal(g.primary.id, 3);
  assert.deepEqual(g.reminders.map(a => a.id), [2]);
  assert.equal(g.tasks[1].id, 1);
});

test('empty businesses start with an entry and never claim their cash is healthy', () => {
  const g = buildGuidance({ ...base, recordCount: 0, alerts: [alert(1, 'low_balance')] });
  assert.equal(g.primary.kind, 'routine');
  assert.match(g.primary.title, /Start with one/);
  assert.equal(g.primary.action.href, '#data');
  assert.doesNotMatch(g.primary.why, /fine|urgent issue/);
  assert.equal(g.tasks.length, 1); // Do not infer a crisis from a missing transaction history.
});

test('viewers get no reminder write action; payment suggestions always open bills', () => {
  const a = alert(1, 'overdue_invoice', { data: { suggested_tool: { name: 'create_payment_reminder', args: { invoice_id: 15 } } } });
  assert.equal(buildGuidance({ ...base, alerts: [a] }).primary.action.tool, 'create_payment_reminder');
  assert.equal(buildGuidance({ ...base, canWrite: false, alerts: [a] }).primary.action.tool, undefined);
  assert.equal(buildGuidance({ ...base, canWrite: false, alerts: [a] }).primary.action.href, '#invoices');
  const bill = alert(2, 'payable_due', { data: { suggested_tool: { name: 'pay_supplier_invoice', args: { invoice_id: 8 } } } });
  assert.deepEqual(buildGuidance({ ...base, alerts: [bill] }).primary.action, { label: 'Check bills', href: '#invoices' });
});

test('Home gets one recommendation while Tasks retains every active issue in priority order', () => {
  const items = [1, 2, 3, 4, 5].map(i => alert(i, 'overdue_invoice'));
  const g = buildGuidance({ ...base, alerts: [...items, items[0], alert(6, 'custom', { status: 'acknowledged' })] });
  assert.equal(g.primary.id, 1); assert.equal(g.tasks.length, 5); assert.equal(g.count, 5);
  assert.equal(g.secondary, undefined); assert.equal(g.remaining, undefined);
  const varied = buildGuidance({ ...base, alerts: [...items, alert(7, 'payable_due'), alert(8, 'stock_low')] });
  assert.deepEqual(varied.tasks.map(t => t.id), [1, 2, 3, 4, 5, 7, 8]);
});

test('guidance is localized while original business evidence is preserved', () => {
  const g = buildGuidance({ ...base, language: 'bn', alerts: [alert(1, 'overdue_invoice')] });
  assert.match(g.primary.title, /বকেয়া/); assert.equal(g.primary.source.message, 'Source evidence');
  assert.match(g.primary.question, /আমার ব্যবসার/);
});

test('upcoming items omit past payments, use chronological order and retain long-term personal reminders', () => {
  const items = upcomingItems({ asOf: base.asOf, scheduled: [
    { date: '2026-10-16', label: 'Past', amount: -100 },
    { date: '2026-10-19', label: 'Supplier', amount: -200, kind: 'payable' },
    { date: '2026-11-30', label: 'Far payment', amount: 100 },
  ], reminders: [alert(1, 'custom', { due_date: '2026-11-15', title: 'My later task' }), alert(2, 'custom', { due_date: '2026-10-18', title: 'My next task' })] });
  assert.deepEqual(items.map(x => x.title), ['My next task', 'Supplier', 'My later task']);
  assert.equal(items[1].estimated, true);
  assert.equal(items[1].amount, -200);
});
