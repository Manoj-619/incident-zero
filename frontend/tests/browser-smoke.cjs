const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const { mkdir } = require('node:fs/promises');
const assert = require('node:assert/strict');

(async () => {
  const server = spawn('npm', ['run', 'preview', '--', '--host', '127.0.0.1', '--port', '4173'], { stdio: 'inherit' });
  let browser;
  try {
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch('http://127.0.0.1:4173')).ok) break; } catch {}
      await new Promise(resolve => setTimeout(resolve, 200));
      if (i === 99) throw new Error('Preview server did not start');
    }
    browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
    const failures = [];
    page.on('pageerror', error => failures.push(error.message));
    page.on('console', message => { if (message.type() === 'error' && message.text().includes('THREE.WebGL')) failures.push(message.text()); });
    await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle' });
    await page.getByText('Verified candidate. Your decision.').waitFor();
    await page.locator('.orbit-render canvas').waitFor();
    const webgl = await page.locator('.orbit-render canvas').evaluate(canvas => !!canvas.getContext('webgl2'));
    assert.ok(webgl, 'A real WebGL2 context is required; fallback UI does not count');
    await mkdir('browser-artifacts', { recursive: true });
    await page.screenshot({ path: 'browser-artifacts/desktop-mission-control.png', fullPage: true });
    const replay = page.getByRole('button', { name: /PLAY RECORDED MISSION/ });
    await replay.click();
    await page.getByText('Mission decision: approval pending').waitFor();
    await page.getByText('Verified candidate. Your decision.').waitFor();
    await page.getByRole('button', { name: /REVIEW & APPROVE/ }).click();
    await page.getByRole('dialog').waitFor();
    assert.equal(await page.getByText('Simulated maneuver accepted').count(), 0, 'Opening review must not approve');
    await page.getByRole('button', { name: /ACCEPT SIMULATED MANEUVER/ }).click();
    await page.getByText('Simulated maneuver accepted').waitFor();
    await page.getByRole('button', { name: /Quiet orbit/ }).click();
    await replay.click();
    await page.getByText('Stand down. Preserve propellant.').waitFor();
    assert.equal(await page.getByRole('button', { name: /REVIEW & APPROVE/ }).count(), 0);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: 'browser-artifacts/mobile-mission-control.png', fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Mobile layout must not overflow horizontally');
    assert.deepEqual(failures, [], 'Uncaught browser or shader errors');
    console.log('PASS: real Chromium/WebGL2, replay completion, explicit approval, no-burn decision, mobile layout');
  } finally {
    await browser?.close();
    server.kill('SIGTERM');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
