// Isolated browser fixture only; no purchases, external messages or owner data.
import { chromium } from '../../data/ui-review/node_modules/playwright-core/index.mjs';
import assert from 'node:assert/strict';
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ baseURL: 'http://127.0.0.1:8002', viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
await context.addInitScript(() => {
  localStorage.setItem('tour_done:tanvir', '1');
  localStorage.setItem('more_languages', '1');
  localStorage.setItem('ui_mode', 'simple');
});
const page = await context.newPage(), errors = [];
page.on('pageerror', e => errors.push(e.message));
const noOverflow = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
const getCase = async id => (await page.request.get(`/api/pilot/cases/${id}`)).json();
const values = {
  item: 'Frozen mango pulp, kg', evidence: 'Owner entered 30 kg monthly demand from past orders',
  buy_date: '2026-10-25', months: 4, quantity: 100, unit_cost: 50, quote_source: 'Supplier quote 17 October',
  setup: 100, later_price: 100, later_source: 'Owner estimate; needs a fresh quote', monthly_use: 30,
  existing_stock: 0, capacity: 110, safe_months: 6, loss_percent: 10, monthly_storage: 100, finance_cost: 100,
  cash: 50000, commitments: 10000, reserve: 5000, storage_plan: 'Product protocol and backup power to verify',
  rule_notes: null, review_date: '2026-10-22',
};
try {
  await page.goto('/');
  await page.locator('#auth-username').fill('tanvir');
  await page.locator('#auth-password').fill('tanvir-demo-2026');
  await page.locator('.auth-submit').click(); await page.locator('.guided-home').waitFor();
  await page.locator('#nav-strategy').click(); await page.locator('.strategy-page').waitFor();
  assert.equal(await page.locator('.strategy-idea').count(), 3);
  const more = page.getByRole('button', { name: 'Show more', exact: true });
  const initialPlans = (await (await page.request.get('/api/pilot/cases')).json()).filter(c => c.kind === 'strategy');
  if (initialPlans.length <= 5) assert.equal(await more.isVisible(), false);
  await noOverflow(); await page.screenshot({ path: 'data/ui-review/strategy-desktop.png', fullPage: true });
  await page.locator('.strategy-idea[href*=seasonal]').focus(); await page.keyboard.press('Enter');
  await page.locator('#pilot-input').waitFor();
  const id = Number(new URL(page.url()).hash.split('case=')[1]);
  assert.ok(id);
  await page.locator('#pilot-input').fill('Mango draft');
  await page.locator('.language-toggle').selectOption('bn');
  await page.locator('#pilot-question').filter({ hasText: 'কোন পণ্য' }).waitFor();
  assert.equal(await page.locator('#pilot-input').inputValue(), 'Mango draft');
  await page.locator('.language-toggle').selectOption('zh');
  await page.locator('#pilot-question').filter({ hasText: '哪种商品' }).waitFor();
  assert.equal(await page.locator('#pilot-input').inputValue(), 'Mango draft');
  await page.locator('.language-toggle').selectOption('en');
  await page.locator('#pilot-question').filter({ hasText: 'Which item' }).waitFor();
  let checkpoints = 0;
  for (let step = 0; step < 40; step++) {
    const c = await getCase(id);
    if (!c.next_question) break;
    if (c.checkpoint_due) {
      await page.getByRole('button', { name: 'Continue deeper', exact: true }).click();
      await page.locator('#pilot-input').waitFor(); checkpoints++;
    }
    const field = c.next_question.id;
    assert.ok(field in values, field);
    const pending = page.waitForResponse(r => r.url().endsWith(`/cases/${id}/answer`));
    if (values[field] === null) await page.getByRole('button', { name: 'I don’t know', exact: true }).click();
    else {
      await page.locator('#pilot-input').fill(String(values[field]));
      await page.getByRole('button', { name: 'Continue', exact: true }).click();
    }
    assert.equal((await pending).status(), 200);
    // Wait for the DOM produced by that response, not merely the HTTP event.
    await page.waitForFunction(() => document.querySelector('.pilot-page')?.getAttribute('aria-busy') === null);
  }
  assert.ok(checkpoints >= 3);
  await page.getByRole('heading', { name: 'Worth checking before you commit' }).waitFor();
  assert.equal(await page.locator('.strategy-scenario').count(), 3);
  await page.screenshot({ path: 'data/ui-review/strategy-comparison.png', fullPage: true });
  await page.getByRole('button', { name: 'Save plan for review', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm and save', exact: true }).click();
  await page.getByText('Saved. You remain in control of the next step.', { exact: true }).waitFor();
  const saved = await getCase(id);
  assert.equal(saved.result.human_review, 'pending');
  assert.ok(saved.result.effects.alert_id && saved.result.effects.document_id);
  assert.equal(await page.locator('.pilot-documents').getAttribute('open'), null);
  assert.equal(await page.getByRole('button', { name: 'I have submitted it', exact: true }).count(), 0);
  await page.reload(); await page.getByText('Saved. You remain in control of the next step.', { exact: true }).waitFor();
  await page.setViewportSize({ width: 360, height: 800 }); await noOverflow();
  await page.locator('.theme-toggle').click();
  await page.screenshot({ path: 'data/ui-review/strategy-mobile-comparison-dark.png', fullPage: true });
  await page.goto('/#more'); await page.locator('.more-card[href="#strategy"]').click();
  await page.locator('.strategy-page').waitFor(); await noOverflow();
  assert.equal(await page.locator('#nav-strategy').isVisible(), false);
  await page.screenshot({ path: 'data/ui-review/strategy-mobile.png', fullPage: true });
  await page.locator('.strategy-idea[href*=bulk]').click(); await page.locator('#pilot-input').waitFor();
  const pendingId = Number(new URL(page.url()).hash.split('case=')[1]);
  await context.setOffline(true);
  await page.locator('#pilot-input').fill('Sugar, kg');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.getByText('Saved on this device only.', { exact: false }).waitFor();
  await context.setOffline(false);
  assert.equal((await getCase(pendingId)).answers.item, undefined);
  assert.deepEqual(errors, []);
  console.log('Strategy browser checks passed: three choices, guided calculation, checkpoints, EN/BN/ZH draft preservation, review save, resume, mobile/dark, offline draft.');
} finally { await browser.close(); }
