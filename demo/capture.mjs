/** Capture real UI and condensed real host-runner output. Never stub an API. */
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {HERE, WORK, pause, exec, esc, browserEngine, save, poll, loopback} from './shared.mjs';

const {values} = parseArgs({options:{'lab-root':{type:'string'},'web-url':{type:'string'},'api-url':{type:'string'}}});
const labRoot = resolve(values['lab-root'] || resolve(HERE,'..'));
const web = loopback(values['web-url'] || `http://127.0.0.1:${process.env.AIPI_WEB_PORT || 5173}`);
const api = loopback(values['api-url'] || `http://127.0.0.1:${process.env.AIPI_API_PORT || 8000}`);
async function get(path) {
  const response = await fetch(api+path, {signal:AbortSignal.timeout(60000)});
  assert(response.ok, `API ${path}: ${response.status}`);
  return response.json();
}
assert.equal((await get('/readyz')).status,'ready');
await mkdir(WORK,{recursive:true});
const chromium = await browserEngine();
const browser = await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? {executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH} : {})});
const context = await browser.newContext({viewport:{width:1280,height:720}, recordVideo:{dir:WORK,size:{width:1280,height:720}},timezoneId:'UTC',locale:'en-US',colorScheme:'light'});
await context.addInitScript(() => {
  addEventListener('DOMContentLoaded', () => {
    const dot = document.createElement('div');
    dot.setAttribute('data-capture-cursor','true');
    dot.style.cssText='position:fixed;left:-100px;top:-100px;width:16px;height:16px;background:#fff;border:2px solid #cb502b;border-radius:50%;box-shadow:0 1px 5px #0007;pointer-events:none;z-index:99999;transform:translate(-50%,-50%);';
    document.body.append(dot);
    addEventListener('mousemove', e => {dot.style.left=e.clientX+'px';dot.style.top=e.clientY+'px';});
    addEventListener('mousedown', () => dot.animate([{boxShadow:'0 0 0 0 #cb502b99'},{boxShadow:'0 0 0 18px #cb502b00'}],{duration:450}));
  });
});
const page = await context.newPage();
page.setDefaultTimeout(20000);
const video = page.video();
const origin = performance.now();
const now = () => (performance.now()-origin)/1000;
const scenes = [];
async function scene(id, duration, act) {
  const start = now();
  await act();
  await pause(Math.max(2000,duration*1000-(now()-start)*1000));
  scenes.push({id,start,end:now(),duration});
  console.log(`Captured ${id}`);
}
async function click(locator) {
  await locator.scrollIntoViewIfNeeded();
  const box=await locator.boundingBox();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:14});
  await pause(180);await locator.click();
}
async function focus(locator) {
  await locator.evaluate(e=>e.scrollIntoView({behavior:'smooth',block:'center'}));
  await pause(700);
}
let capture;
try {
  const start = new Date().toISOString();
  console.log('Collecting 30 seconds of healthy seeded baseline (not included in edit).');
  await pause(30000);
  const runnerBase = `<style>body{margin:0;background:#14231f;color:#eaf2ec;font:20px Arial;padding:72px}h1{font-size:36px;margin:18px 0 35px}small{letter-spacing:3px;color:#a5b6ad}pre{font:21px/1.9 monospace;border:1px solid #3b4a42;border-radius:12px;padding:30px;background:#101b17;white-space:pre-wrap}.ok{color:#b8dfb3}footer{color:#a5b6ad;margin-top:24px}</style><small>OPERATOR CAPTURE · REAL LAB RUNNER</small><h1>One controlled fault. Observable recovery.</h1>`;
  await page.setContent(runnerBase+'<pre>$ make chaos-kill\n\nRunning the bounded checkout fault and recovery checks…</pre><footer>Host-only chaos operation. Investigation tools cannot execute it.</footer>');
  const pendingStart=now();
  const running=exec('make',['-s','chaos-kill'],{cwd:labRoot,env:{...process.env,UV_CACHE_DIR:process.env.UV_CACHE_DIR || '/tmp/aipi-uv-cache'}});
  await pause(2200);
  scenes.push({id:'fault-command',start:pendingStart,end:now(),duration:2});
  const stdout=await running;
  await writeFile(resolve(WORK,'chaos-output.json'),stdout);
  const run=JSON.parse(stdout);
  assert.equal(run.passed,true);assert.equal(run.recovery_status,'verified');
  const events=run.observations.runtime_events;
  const die=events.find(e=>e.event==='die' && String(e.exit_code)==='137');
  const recovered=events.find(e=>e.event==='start' && e.ts>die?.ts);
  assert(die && recovered,'The actual run must contain die(137) → start');
  // The form uses whole seconds; round forward so completed_at stays covered.
  const end=new Date(Math.ceil(Date.now()/1000)*1000).toISOString();
  const lines=['$ make chaos-kill','',`die   checkout-api  exit_code=137  ${die.ts.slice(11,19)} UTC`,`start checkout-api                ${recovered.ts.slice(11,19)} UTC`,'',`Gateway 5xx probes: ${run.observations.gateway_5xx_requests}`,`Failed gateway spans: ${run.observations.gateway_failed_spans}`,`Recovery: ${run.recovery_status}`];
  await page.setContent(runnerBase+`<pre>${esc(lines.join('\n'))}</pre><footer class="ok">Observed telemetry and recovery checks · condensed actual stdout</footer>`);
  await scene('fault-result',6,async()=>{});
  await page.goto(web+'/#/incidents');
  await page.getByRole('heading',{name:'Incidents.',exact:true}).waitFor();
  await scene('create',8,async()=>{
    await click(page.getByRole('button',{name:'+ New incident'}));
    await page.getByLabel('Incident title',{exact:true}).pressSequentially('Checkout errors — recorded demo',{delay:18});
    await page.getByLabel('Window start',{exact:true}).fill(start.slice(0,19));
    await page.getByLabel('Window end',{exact:true}).fill(end.slice(0,19));
    await page.getByLabel('Symptoms',{exact:true}).fill('Gateway checkout requests returned errors.');
    assert.equal(await page.getByLabel('gateway',{exact:true}).isChecked(),true);
    await pause(1500);
    await click(page.getByRole('button',{name:'Create incident',exact:true}));
    await page.waitForURL(/#\/incidents\/[0-9a-f-]+$/);
    await page.getByRole('button',{name:'Start investigation',exact:true}).waitFor();
  });
  const id=page.url().split('/').at(-1);
  const incident=await get(`/api/incidents/${id}`);
  assert.equal(incident.service,'checkout-api');assert(incident.related_services.includes('gateway'));
  const first=await get(`/api/incidents/${id}/evidence`);
  let job;
  await scene('trace',8,async()=>{
    await click(page.getByRole('button',{name:'Start investigation',exact:true}));
    await page.getByRole('heading',{name:'Investigation execution'}).waitFor();
    job=await poll(()=>get(`/api/incidents/${id}/investigation`),j=>j.status==='completed');
    assert.equal(job.provider,'mock');
    await focus(page.locator('.trace-stats'));
    await pause(2000);
    await focus(page.locator('.trace-event').last());
  });
  const report=await get(`/api/incidents/${id}/report`);
  assert.match(report.root_cause.statement,/terminated/i);
  await scene('evidence',7,async()=>{
    await click(page.getByRole('tab',{name:'Evidence',exact:true}));
    await page.getByLabel('Filter evidence by type').selectOption('event');
    await focus(page.locator('.evidence-list'));
    assert(await page.locator('.evidence-row').count()>=2);
    await page.screenshot({path:resolve(WORK,'evidence.png')});
  });
  await scene('hypotheses',7,async()=>{
    await click(page.getByRole('tab',{name:'Hypotheses',exact:true}));
    await focus(page.locator('.hypothesis.leading'));
    await page.screenshot({path:resolve(WORK,'hypotheses.png')});
    await pause(2300);
    await focus(page.locator('.hypothesis').nth(1));
    assert(await page.locator('.hypothesis').nth(1).getByText(/AGAINST/).isVisible());
  });
  let outside;
  await scene('outside',6,async()=>{
    await click(page.getByRole('tab',{name:'Report',exact:true}));
    const chip=page.locator('.report .evidence-chip[aria-label*="outside bundle"]').first();
    outside=(await chip.getAttribute('aria-label')).match(/ev_[0-9a-f]+/)[0];
    assert(!first.items.some(e=>e.evidence_id===outside));
    await click(chip);
    await page.getByRole('dialog').getByRole('heading',{name:'Evidence detail'}).waitFor();
    await page.getByRole('dialog').getByRole('heading',{name:'Payload',exact:true}).waitFor();
    await focus(page.getByRole('dialog').locator('pre'));
    await page.screenshot({path:resolve(WORK,'outside.png')});
  });
  await scene('report',7,async()=>{
    await click(page.getByRole('button',{name:'Close evidence'}));
    await focus(page.locator('.root-cause'));
    await pause(2000);
    await focus(page.getByText('Requires human approval',{exact:true}));
    const download=page.waitForEvent('download');
    await click(page.getByRole('button',{name:'↓ Export Markdown'}));
    await (await download).saveAs(resolve(WORK,'exported-report.md'));
    assert(report.recommendations.every(r=>r.requires_approval && !r.executed));
  });
  let evaluation;
  await scene('evaluation',10,async()=>{
    await click(page.getByRole('link',{name:'Open evaluation ↗'}));
    await page.getByLabel('Chaos run ID',{exact:true}).fill(run.run_id);
    await click(page.getByRole('button',{name:'Run replay →'}));
    await page.getByRole('heading',{name:'Evaluation passed',exact:true}).waitFor({timeout:90000});
    const eid=new URLSearchParams(page.url().split('?')[1]).get('evaluation');
    evaluation=await get(`/api/evaluations/${eid}`);
    assert(evaluation.scorecard.passed);
    assert.equal(evaluation.scorecard.scores.critical_unsupported_claims,0);
    await focus(page.locator('.scorecard'));
    await page.screenshot({path:resolve(WORK,'evaluation.png')});
    await pause(2500);
    await focus(page.getByRole('heading',{name:'Ground truth',exact:true}));
  });
  // Verify all cited observations after recording; these requests are not staged UI output.
  const cited=[...new Set([
    ...report.claims.flatMap(c=>c.evidence_ids),
    ...report.ranked_hypotheses.flatMap(h=>[...h.for,...h.against]),
    ...report.recommendations.flatMap(r=>r.evidence_ids),
    ...report.timeline.flatMap(t=>t.evidence_ids),
  ])];
  const resolved=[];
  for(let i=0;i<cited.length;i+=4) {
    resolved.push(...await Promise.all(cited.slice(i,i+4).map(async evidenceId=>{
      const item=await get(`/api/incidents/${id}/evidence/${evidenceId}`);
      assert.equal(item.evidence_id,evidenceId);
      assert([incident.service,...incident.related_services].includes(item.service));
      assert(Date.parse(item.timestamp)>=Date.parse(incident.start_time) && Date.parse(item.timestamp)<=Date.parse(incident.end_time));
      return evidenceId;
    })));
  }
  const again=await get(`/api/incidents/${id}/evidence`);
  assert.deepEqual(first.items.map(e=>e.evidence_id),again.items.map(e=>e.evidence_id));
  const eventsSnapshot=await get(`/api/investigations/${job.id}/events?format=json`);
  for(const node of ['Triage','Retriever','Hypothesis','Verifier','Ranker','Reporter']) assert(eventsSnapshot.events.some(e=>e.node===node && e.kind==='node_completed'));
  assert(report.ranked_hypotheses.slice(1).some(h=>h.against.length));
  capture={recorded_at:new Date().toISOString(),browser:browser.version(),viewport:{width:1280,height:720},scenario:run.scenario_id,chaos:run,incident_id:id,investigation_id:job.id,evaluation_id:evaluation.id,incident_window:{start_time:incident.start_time,end_time:incident.end_time},provider:job.provider,model:job.model,scores:evaluation.scorecard.scores,gate_failures:evaluation.scorecard.failures,report_root_cause:report.root_cause,selected_evidence_count:first.items.length,cited_ids_resolved:resolved.length,cited_outside_bundle:cited.filter(e=>!first.items.some(item=>item.evidence_id===e)),shown_outside_bundle:outside,identical_bundle_ids_on_rerun:true,six_nodes_completed:true,read_only_recommendations:true,scenes,source:'Real Playwright browser capture and condensed actual CLI stdout; no API interception, seeded report, invented score or altered application UI.',editing:'Setup/baseline/waits shortened; captions and explanatory cards added. Deterministic mock; this run is not an LLM accuracy measurement.'};
} catch(error) {
  await page.screenshot({path:resolve(WORK,'capture-failure.png')}).catch(()=>{});
  await save('capture-failure.json',{message:error.message,url:page.url()});
  throw error;
} finally {
  await context.close();
  await browser.close();
}
assert(capture,'Capture must pass all actual execution checks');
capture.raw_video=await video.path();
await save('capture.json',capture);
console.log(`Verified actual workflow; ${capture.cited_ids_resolved} citations resolved; manifest: ${resolve(WORK,'capture.json')}`);
