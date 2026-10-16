import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {resolve, dirname} from 'node:path';
import {spawn} from 'node:child_process';
import {mkdir, writeFile} from 'node:fs/promises';

export const HERE = dirname(fileURLToPath(import.meta.url));
export const WORK = resolve(HERE, '.work');
export const pause = ms => new Promise(r => setTimeout(r, ms));
export const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export async function browserEngine() {
  const loader = createRequire(import.meta.url);
  return loader(process.env.AIPI_PLAYWRIGHT_MODULE || 'playwright').chromium;
}
export function exec(command, args, options = {}) {
  return new Promise((ok, fail) => {
    const child = spawn(command, args, {stdio: ['ignore','pipe','pipe'], ...options});
    let stdout = '', stderr = '';
    child.stdout.on('data', chunk => {stdout += chunk;});
    child.stderr.on('data', chunk => {stderr += chunk;});
    child.on('error', fail);
    child.on('close', code => code === 0 ? ok(stdout) : fail(new Error(`${command} failed (${code}): ${stderr.slice(-2500)}`)));
  });
}
export async function save(name, value) {
  await mkdir(WORK, {recursive:true});
  await writeFile(resolve(WORK,name), JSON.stringify(value,null,2)+'\n');
}
export async function poll(fn, ready, timeout = 120000) {
  const start = performance.now();
  while (performance.now()-start < timeout) {
    const value = await fn();
    if (ready(value)) return value;
    await pause(250);
  }
  throw new Error('Timed out waiting for a genuine application result');
}
export function loopback(value) {
  const url = new URL(value);
  if (!['localhost','127.0.0.1'].includes(url.hostname) || url.protocol !== 'http:') throw new Error('Capture is restricted to the local lab');
  return url.origin;
}
