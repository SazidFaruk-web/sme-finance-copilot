// Optional rendered checks: see tests/browser/README.md. Runtime files stay in ignored data/.
import { chromium } from '../../data/ui-review/node_modules/playwright-core/index.mjs';
import assert from 'node:assert/strict';
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ baseURL: 'http://127.0.0.1:8002', viewport: { width: 1280, height: 900 }, colorScheme: 'light', reducedMotion: 'reduce' });
const page = await context.newPage(); const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('requestfailed', r => console.log('REQUEST FAILED', r.url(), r.failure()?.errorText));
page.on('console', m => { if (m.type() === 'error') console.log('BROWSER', m.text()); });
async function go(hash) { await page.goto('/' + hash); await page.locator('.pilot-page').waitFor(); await page.waitForFunction(() => document.querySelector('.pilot-page')?.getAttribute('aria-busy') !== 'true'); }
async function btn(name) { await page.getByRole('button', { name, exact: true }).click(); await page.waitForFunction(() => document.querySelector('.pilot-page')?.getAttribute('aria-busy') !== 'true'); }
try {
  await page.goto('/'); await page.locator('#auth-username').fill('nusrat'); await page.locator('#auth-password').fill('owner-demo-2026'); await page.locator('.auth-submit').click();
  await page.locator('.guided-home').waitFor();
  assert.equal(await page.locator('.home-main-grid > *').count(), 2);
  await go('#chat'); assert.equal(await page.locator('.pilot-choices > button').count(), 3);
  await page.screenshot({ path: 'data/ui-review/pilot-desktop.png', fullPage: true });
  await btn('Record or check money'); await page.getByRole('heading', { name: 'What happened?' }).waitFor();
  await btn('Sale / daily sales'); await btn('Use today'); await btn('Continue');
  await page.locator('#pilot-input').fill('১২৩৪');
  await page.getByRole('button', { name: 'Switch to Bangla', exact: true }).click();
  await page.locator('#pilot-input').waitFor(); assert.equal(await page.locator('#pilot-input').inputValue(), '১২৩৪');
  assert.match(await page.locator('#pilot-question').textContent(), /মোট/);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.screenshot({ path: 'data/ui-review/pilot-bangla-mobile.png', fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await btn('পরের ধাপ'); await page.locator('#pilot-input').fill('আজকের বিক্রি'); await btn('পরের ধাপ'); await btn('হ্যাঁ'); await btn('নগদ');
  await page.getByRole('heading', { name: 'আপনার যাচাইয়ের জন্য প্রস্তুত' }).waitFor();
  await btn('দেখে সংরক্ষণ করুন'); await btn('নিশ্চিত করে সেভ');
  await page.getByText('সেভ হয়েছে। পরের পদক্ষেপ আপনার সিদ্ধান্ত।', { exact: true }).waitFor();
  await page.reload(); await page.getByText('সেভ হয়েছে। পরের পদক্ষেপ আপনার সিদ্ধান্ত।', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'ইংরেজিতে দেখুন', exact: true }).click();
  await page.setViewportSize({ width: 1280, height: 900 });
  await go('#chat?start=stock'); await page.getByRole('heading', { name: 'Which product would you like to try?' }).waitFor();
  const stock = { product: 'Soap', quantity: 20, unit_cost: 50, delivery: 100, price: 75, selling_cost: 5, expected: 15, evidence: 'Customers asked', risk: 'May remain unsold', collection_days: 0, cash: 10000, reserve: 5000, review_date: '2026-11-15' };
  for (const value of Object.values(stock)) {
    if (await page.getByRole('button', { name: 'Continue deeper', exact: true }).count()) await btn('Continue deeper');
    await page.locator('#pilot-input').fill(String(value)); await btn('Continue');
  }
  await page.getByRole('heading', { name: 'Start with a small test' }).waitFor(); await btn('Test a smaller batch'); await btn('Confirm and save');
  await page.screenshot({ path: 'data/ui-review/pilot-stock-result.png', fullPage: true });
  await go('#chat?start=loan'); await page.locator('#pilot-input').waitFor();
  const loan = { lender: 'Pilot actual quote', quote_source: 'Written quote 17 Oct 2026', principal: 10000, fees: 200,
    schedule: [{ date: '2027-10-21', amount: 12000 }], quote_complete: 'yes', cash: 50000, purchase: 5000,
    income: 20000, slow_income: 10000, cash_timing: 'daily', expenses: 3000, household: 2000,
    existing_debt: 500, other_schedule: [], reserve: 10000, facts_complete: 'yes', security: 'No pledge in quote', review_date: '2026-10-20' };
  const loanId = new URLSearchParams(new URL(page.url()).hash.split('?')[1]).get('case');
  while (true) {
    const c = await (await page.request.get(`/api/pilot/cases/${loanId}`)).json();
    if (!c.next_question) break;
    if (c.checkpoint_due) await btn('Continue deeper');
    const q = c.next_question, value = loan[q.id]; assert.notEqual(value, undefined, q.id);
    if (q.type === 'choice') await btn(q.options.find(o => o.value === value).label.en);
    else if (q.type === 'schedule') {
      for (const payment of value) { await btn('Add a payment'); await page.getByLabel('Payment date', { exact: true }).last().fill(payment.date); await page.getByLabel('Payment amount', { exact: true }).last().fill(String(payment.amount)); }
      await btn('Continue');
    } else { await page.locator('#pilot-input').fill(String(value)); await btn('Continue'); }
  }
  await btn('Save for review'); await btn('Confirm and save');
  assert.match(await page.locator('.pilot-page').textContent(), /Waiting for pilot reviewer/);
  await page.emulateMedia({ colorScheme: 'dark' }); await page.setViewportSize({ width: 320, height: 800 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: 'data/ui-review/pilot-loan-dark-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 }); await page.emulateMedia({ colorScheme: 'light' });
  await go('#chat?tab=notifications'); await page.getByRole('heading', { name: 'Reminders that suit you' }).waitFor();
  await go('#chat?tab=offline');
  await page.getByLabel('What happened?', { exact: true }).fill('offline sale'); await page.getByLabel('Amount', { exact: true }).fill('500');
  await btn('Save on this device'); await page.getByRole('heading', { name: 'offline sale' }).waitFor();
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await context.setOffline(true); await page.reload();
  await page.getByRole('heading', { name: 'offline sale' }).waitFor(); assert.match(await page.locator('body').textContent(), /Connection unavailable/);
  await context.setOffline(false); await page.reload(); await page.getByRole('heading', { name: 'offline sale' }).waitFor();
  await btn('Send for review'); await page.getByRole('heading', { name: 'Was money paid now?' }).waitFor();
  assert.equal(errors.length, 0, errors.join('\n'));
  console.log('PASS Home budget, three choices, record confirmation, Bangla numerals, language draft preservation, mobile overflow, stock checkpoint, complete loan schedule, dark mobile, reminders, offline cache and manual sync.');
} catch (e) { console.log('URL', page.url(), 'ERRORS', errors); console.log((await page.locator('body').textContent()).slice(-5000)); await page.screenshot({ path: 'data/ui-review/pilot-failure.png', fullPage: true }); throw e; } finally { await browser.close(); }
