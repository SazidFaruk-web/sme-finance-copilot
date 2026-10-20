// Real browser checks against the isolated fixture, never owner data or live models.
import { chromium } from '../../data/ui-review/node_modules/playwright-core/index.mjs';
import assert from 'node:assert/strict';
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ baseURL: 'http://127.0.0.1:8002', viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
await context.addInitScript(() => {
  localStorage.setItem('tour_done:tanvir', '1'); localStorage.setItem('more_languages', '1'); localStorage.setItem('ui_mode', 'simple'); localStorage.setItem('theme', 'light');
});
const page = await context.newPage(), errors = [];
page.on('pageerror', e => errors.push(e.message));
const noOverflow = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
const getCase = async id => (await page.request.get(`/api/pilot/cases/${id}`)).json();
const caseId = () => Number(new URL(page.url()).hash.split('case=')[1]);
const waitSaved = async action => {
  const response = page.waitForResponse(r => /\/cases\/\d+\/(answer|control|preview|confirm)$/.test(r.url()));
  await action(); assert.equal((await response).status(), 200);
  await page.waitForFunction(() => document.querySelector('.pilot-page')?.getAttribute('aria-busy') === null);
};
const clickAnswer = async name => waitSaved(() => page.getByRole('button', { name, exact: true }).click());
const start = async plan => {
  await page.goto('/#strategy'); await page.locator('.strategy-page').waitFor();
  await page.locator('.strategy-manual > summary').click();
  await page.locator(`.strategy-idea[href*=${plan}]`).click();
  await page.locator('#pilot-question').waitFor(); return caseId();
};
try {
  await page.goto('/'); await page.locator('#auth-username').fill('tanvir'); await page.locator('#auth-password').fill('tanvir-demo-2026'); await page.locator('.auth-submit').click();
  await page.locator('.guided-home').waitFor();
  const id = await start('equipment');
  assert.equal(await page.locator('#pilot-input:visible').count(), 0);
  await clickAnswer('Freezer');
  await page.getByRole('checkbox', { name: 'Customers are waiting', exact: true }).check();
  await page.getByRole('checkbox', { name: 'I need more storage', exact: true }).check();
  await page.screenshot({ path: 'data/ui-review/strategy-choices-desktop.png', fullPage: true });
  await page.locator('.language-toggle').selectOption('bn'); await page.getByRole('heading', { name: 'এতে কী সুবিধা হবে? যা মেলে বাছুন।', exact: true }).waitFor();
  assert.equal(await page.locator('.pilot-select input:checked').count(), 2);
  await page.locator('.language-toggle').selectOption('zh'); await page.getByRole('heading', { name: '这能解决什么问题？可选择多项。', exact: true }).waitFor();
  assert.equal(await page.locator('.pilot-select input:checked').count(), 2);
  await page.locator('.language-toggle').selectOption('en'); await page.getByRole('heading', { name: 'What would this help with? Choose any that fit.', exact: true }).waitFor();
  await clickAnswer('Continue'); await clickAnswer('Just exploring'); await clickAnswer('It is an idea to test'); await clickAnswer('In a week');
  await page.getByRole('heading', { name: 'Here’s a starting point', exact: true }).waitFor();
  const initial = await getCase(id);
  assert.equal(initial.result.preliminary, true); assert.deepEqual(initial.result.metrics, {});
  assert.ok(Object.keys(initial.answers).filter(k => !k.startsWith('_')).length <= 6);
  assert.equal(await page.locator('.pilot-metric').count(), 0);
  await page.screenshot({ path: 'data/ui-review/strategy-starting-plan.png', fullPage: true });
  await clickAnswer('Check the costs (optional)'); await page.locator('#pilot-input').waitFor();
  await clickAnswer('Back to my starting plan'); await page.getByRole('heading', { name: 'Here’s a starting point', exact: true }).waitFor();
  await clickAnswer('Save this starting plan'); await clickAnswer('Confirm and save');
  await page.getByText('Saved. You remain in control of the next step.', { exact: true }).waitFor();
  const saved = await getCase(id); assert.ok(saved.result.effects.alert_id); assert.equal(saved.result.preliminary, true);
  await page.reload(); await page.getByText('Saved. You remain in control of the next step.', { exact: true }).waitFor();
  await page.setViewportSize({ width: 360, height: 800 }); await noOverflow(); await page.locator('.theme-toggle').click();
  await page.screenshot({ path: 'data/ui-review/strategy-starting-plan-mobile-dark.png', fullPage: true });
  const pendingId = await start('equipment'); await clickAnswer('Freezer');
  await page.getByRole('checkbox', { name: 'Customers are waiting', exact: true }).check();
  await context.setOffline(true); await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.getByText('Saved on this device only.', { exact: false }).waitFor();
  await context.setOffline(false); assert.equal((await getCase(pendingId)).answers.drivers, undefined);
  const reply = '## A small next step\n\n**Keep bill money aside.**\n\n1. Ask for a quote.\n2. Compare storage costs.\n   - Power\n   - Delivery\n\n| Option | Cost |\n| --- | --- |\n| Small batch | ৳৫০০ |\n| Full batch | ৳1,000 |\n\n```text\nReview before buying.\n```\n\n[Official source](https://example.gov.bd/rules)\n\n<script>window.markdownExecuted = true</script>\n![track](https://tracking.invalid/pixel) [bad](javascript:alert(1))';
  let imageRequests = 0; page.on('request', r => { if (r.url().includes('tracking.invalid')) imageRequests++; });
  await page.route('**/api/chat/stream', route => route.fulfill({ status: 200, contentType: 'text/event-stream', body:
    'event: delta\ndata: ' + JSON.stringify({ text: '**Keep bill' }) + '\n\n' +
    'event: done\ndata: ' + JSON.stringify({ conversation_id: 123, tool_calls: [], reply, pending_actions: [], language: 'en', profile: 'rules-offline' }) + '\n\n' }));
  await page.goto('/#chat'); await page.locator('.chat-question').fill('A review fixture');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  const bot = page.locator('.msg.bot').last(); await bot.locator('table').waitFor();
  assert.equal(await bot.locator('strong').innerText(), 'Keep bill money aside.');
  assert.equal(await bot.locator('ol > li').count(), 2); assert.equal(await bot.locator('ul > li').count(), 2);
  assert.equal(await bot.locator('th').count(), 2); assert.equal(await bot.locator('td').count(), 4);
  assert.equal(await bot.locator('pre code').innerText(), 'Review before buying.');
  assert.equal(await bot.locator('script, img').count(), 0); assert.equal(await bot.locator('a').count(), 1);
  assert.equal(await page.evaluate(() => Boolean(window.markdownExecuted)), false); assert.equal(imageRequests, 0);
  await noOverflow(); await page.screenshot({ path: 'data/ui-review/markdown-mobile-dark.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 }); await page.locator('.theme-toggle').click(); await noOverflow();
  await page.screenshot({ path: 'data/ui-review/markdown-desktop.png', fullPage: true });
  assert.deepEqual(errors, []);
  console.log('Passed: five tap-based Strategy answers, dynamic branch, multi-select locale persistence, optional costs, save/resume, mobile/dark/offline, safe Markdown in chat.');
} finally { await browser.close(); }
