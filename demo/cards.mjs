/** Editorial cards and caption graphics; application screenshots stay unmodified. */
import {mkdir,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {HERE,WORK,browserEngine,esc} from './shared.mjs';

export const CAPTIONS = {
  'fault-command':['Inject one controlled service failure.','Actual make chaos-kill command · host operator only'],
  'fault-result':['Verify the failure — and its recovery.','Condensed actual stdout · die (137) → start · waiting period shortened'],
  create:['Declare the scope before investigating.','checkout-api + gateway · explicit service and time boundaries'],
  trace:['Follow every step of the investigation.','Six LangGraph stages · audited read-only tools · deterministic mock'],
  evidence:['Freeze observations. Keep their provenance.','Runtime events · 50-item display cap · full-scope correlation'],
  hypotheses:['Compare causes, including counterevidence.','FOR / AGAINST citations · confidence from a fixed evidence formula'],
  outside:['Follow a citation beyond the display cap.','Actual scoped evidence-by-ID lookup · frozen source payload'],
  report:['Keep facts, hypotheses and next checks separate.','Requires human approval · export the stored Markdown report'],
  evaluation:['Score this recovered fault against protected truth.','Scorer opens labels after investigation · these scores describe this run'],
};
const BASE = `<style>
*{box-sizing:border-box}html,body{width:1920px;height:1080px;margin:0;overflow:hidden;font-family:Arial,sans-serif;color:#eff4ec;background:#14231e}
body{background:radial-gradient(ellipse at 85% 15%,#2a4335 0,transparent 55%),#14231e}
.grid{position:absolute;inset:0;background-image:linear-gradient(#78967e0a 1px,transparent 1px),linear-gradient(90deg,#78967e0a 1px,transparent 1px);background-size:72px 72px;mask-image:linear-gradient(90deg,transparent,#000)}
.brand{position:absolute;left:100px;top:70px;font-size:34px;font-weight:bold;letter-spacing:2px;display:flex;align-items:center;gap:18px}.mark{width:52px;height:52px;background:#ca5a36;border-radius:12px;text-align:center;line-height:52px;color:#fff7ed;font-size:32px}
.kicker{font-size:22px;letter-spacing:4px;color:#b5c6b3;text-transform:uppercase}.accent{color:#e98c61}.muted{color:#b3c2b0}.foot{position:absolute;left:102px;right:102px;bottom:65px;display:flex;justify-content:space-between;font-size:21px;color:#b5c2b2;border-top:1px solid #6e8e6c55;padding-top:22px}
h1{font-size:102px;line-height:1.06;letter-spacing:-4px;margin:30px 0}p{font-size:31px;line-height:1.5;font-weight:normal}.pill{display:inline-block;border:1px solid #7f98765c;background:#304c37;padding:12px 21px;border-radius:50px;font-size:22px;color:#d7e6cf}
.card{padding:38px;border:1px solid #59715188;border-radius:16px;background:#1d3228}.label{font-size:19px;letter-spacing:3px;text-transform:uppercase;color:#acc4a6}h2{font-size:39px;line-height:1.2;margin:20px 0}h3{font-size:29px;margin:20px 0}.arrow{color:#d58a5f;font-size:42px;text-align:center}
</style><div class="grid"></div><div class="brand"><span class="mark">▥</span>AIPI</div>`;
const foot = text => `<div class="foot"><span>${text}</span><span>LOCAL LAB · DETERMINISTIC MOCK</span></div>`;
const title = BASE+`<section style="position:absolute;left:102px;top:255px"><div class="kicker">AI Production Incident Investigator</div><h1>From scattered signals<br>to a <span class="accent">defensible diagnosis.</span></h1><p class="muted">Real faults. Scoped evidence. Competing explanations.<br>A report you can inspect — and evaluate.</p><div style="margin-top:42px"><span class="pill">OpenTelemetry</span> <span class="pill">FastAPI + PostgreSQL</span> <span class="pill">LangGraph + React</span></div></section>`+foot('Actual browser capture · captioned walkthrough · edited for pace');
const architecture = BASE+`<section style="position:absolute;left:102px;right:102px;top:200px"><div class="kicker">System overview</div><h1 style="font-size:74px">Deterministic correlation comes first.</h1><div style="display:grid;grid-template-columns:1fr 65px 1fr 65px 1fr;align-items:center;margin-top:65px"><div class="card"><div class="label">Observe</div><h2>Docker fault lab</h2><p>Checkout + gateway<br>PostgreSQL replica<br>Logs · metrics · traces</p></div><div class="arrow">→</div><div class="card"><div class="label">Investigate</div><h2>Scoped evidence</h2><p>OTel → PostgreSQL<br>Six LangGraph stages<br>Read-only diagnostic tools</p></div><div class="arrow">→</div><div class="card"><div class="label">Verify</div><h2>Cited report</h2><p>FOR / AGAINST<br>Separate scorer service<br>Protected truth credential</p></div></div></section>`+foot('Ground-truth labels never enter the investigation workflow.');
const engineering = BASE+`<section style="position:absolute;left:102px;right:102px;top:205px"><div class="kicker">Engineering highlights</div><h1 style="font-size:79px">Safety and traceability are testable.</h1><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:28px;margin-top:60px"><div class="card"><div class="label">01 / Least privilege</div><h2>Read-only tools</h2><p>Typed, scoped queries.<br>No remediation API.</p></div><div class="card"><div class="label">02 / Consistency</div><h2>Frozen evidence</h2><p>Stable source-derived IDs.<br>Full-scope witnesses.<br>Deterministic replay.</p></div><div class="card"><div class="label">03 / Evaluation</div><h2>Fail on fabrication</h2><p>Reject unknown cited IDs,<br>invented values and<br>unsupported critical claims.</p></div></div></section>`+foot('Automated unit, live Docker, golden and UI checks accompany the implementation.');
const ending=BASE+`<section style="position:absolute;left:102px;top:235px"><div class="kicker">Inspect the evidence. Challenge the conclusion.</div><h1>Investigate.<br>Verify. <span class="accent">Explain.</span></h1><p class="muted">Reproduce the complete workflow with <strong style="color:#f2f4ec">make demo</strong>.</p><p style="font-size:26px;margin-top:42px">Deterministic mock · two curated fault scenarios<br>No real-LLM accuracy claim · no remediation executed</p></section>`+foot('Source, runbooks, tests and reproduction instructions are in the repository.');
export async function makeCards() {
  await mkdir(WORK,{recursive:true});
  const browser=await (await browserEngine()).launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{})});
  const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  for(const [name,html] of Object.entries({title,architecture,engineering,ending})) {
    await page.setContent(html);await page.screenshot({path:resolve(WORK,`${name}.png`)});
  }
  for(const [id,[headline,sub]] of Object.entries(CAPTIONS)) {
    await page.setContent(`<style>html,body{margin:0;width:1920px;height:1080px;background:transparent;font-family:Arial,sans-serif}.bottom{position:absolute;bottom:0;left:0;right:0;height:170px;background:linear-gradient(transparent,#10211cf7 28%);color:#f7f9f1;padding:48px 55px 20px}.title{font-size:35px;font-weight:bold;letter-spacing:-.5px}.sub{font-size:23px;color:#c4d2c0;margin-top:10px}.badge{position:absolute;right:25px;top:20px;background:#15271ff2;border:1px solid #82966c;color:#eaf2dd;font-size:17px;padding:10px 15px;border-radius:6px;letter-spacing:1px}</style><div class="badge">ACTUAL ${id.startsWith('fault')?'CLI':'UI'} · MOCK · EDITED FOR PACE</div><div class="bottom"><div class="title">${esc(headline)}</div><div class="sub">${esc(sub)}</div></div>`);
    await page.screenshot({path:resolve(WORK,`overlay-${id}.png`),omitBackground:true});
  }
  const screenshot=(await readFile(resolve(WORK,'hypotheses.png'))).toString('base64');
  await page.setContent(BASE+`<section style="position:absolute;left:100px;top:250px;width:770px"><div class="kicker">An engineering project walkthrough</div><h1 style="font-size:100px">Real faults.<br><span class="accent">Cited answers.</span></h1><p class="muted">Chaos → investigation → evaluation</p><div style="margin-top:50px"><span class="pill">1080p · captioned demo</span></div></section><div style="position:absolute;left:945px;top:240px;width:880px;height:600px;border:2px solid #899c78;border-radius:20px;overflow:hidden;box-shadow:0 30px 100px #0006"><img src="data:image/png;base64,${screenshot}" style="height:100%;width:100%;object-fit:cover;object-position:70% 50%"><div style="position:absolute;left:355px;top:220px;width:125px;height:125px;border-radius:50%;background:#ca5a36f5;border:3px solid #ffe8d3;display:grid;place-items:center;color:white;font-size:64px;padding-left:9px">▶</div></div>`+foot('Actual local application · deterministic mock · no paid model required'));
  await page.screenshot({path:resolve(HERE,'aipi-demo-thumbnail.png')});
  await browser.close();
}
