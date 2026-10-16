/** Read-only close-ups of the SAME actual frozen incident, report and scorecard. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {HERE,WORK,pause,browserEngine,save,loopback} from './shared.mjs';
const m=JSON.parse(await readFile(resolve(WORK,'capture.json'),'utf8'));
const {values}=parseArgs({options:{'web-url':{type:'string'},'api-url':{type:'string'}}});
const web=loopback(values['web-url'] || process.env.AIPI_VIDEO_WEB_URL || `http://127.0.0.1:${process.env.AIPI_WEB_PORT || 5173}`);
const api=loopback(values['api-url'] || process.env.AIPI_VIDEO_API_URL || `http://127.0.0.1:${process.env.AIPI_API_PORT || 8000}`);
async function get(path){const r=await fetch(api+path,{signal:AbortSignal.timeout(60000)});assert(r.ok);return r.json();}
// Prefer a cited runbook chunk: it is readable and has no network metadata.
const report=await get(`/api/incidents/${m.incident_id}/report`);
const candidates=[...new Set(report.recommendations.flatMap(r=>r.evidence_ids))].filter(id=>m.cited_outside_bundle.includes(id));
let witness;
for(const id of candidates) {
  const item=await get(`/api/incidents/${m.incident_id}/evidence/${id}`);
  if(item.type==='runbook'){witness=item;break;}
}
if(!witness) witness=await get(`/api/incidents/${m.incident_id}/evidence/${m.shown_outside_bundle}`);
assert(m.cited_outside_bundle.includes(witness.evidence_id));
const engine=await browserEngine();
const browser=await engine.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{})});
const ctx=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:WORK,size:{width:1280,height:720}},timezoneId:'UTC',locale:'en-US'});
const page=await ctx.newPage();page.setDefaultTimeout(60000);
const video=page.video(),base=performance.now();
const now=()=>(performance.now()-base)/1000;
const clips={};
async function focus(item){await item.evaluate(e=>e.scrollIntoView({behavior:'smooth',block:'center'}));await pause(700);}
async function record(id,act){const start=now();await act();clips[id]={start,end:now()};console.log('Close-up '+id);}
try {
  await page.goto(web+`/#/incidents/${m.incident_id}`);
  await page.getByRole('button',{name:'Investigate again',exact:true}).waitFor();
  await page.getByRole('tab',{name:'Agent Trace',exact:true}).click();
  await page.locator('.trace-stats').waitFor();
  await record('trace',async()=>{
    await focus(page.locator('.trace-stats'));await pause(2900);
    await focus(page.locator('.trace-event').last());await pause(2900);
  });
  await page.getByRole('tab',{name:'Report',exact:true}).click();
  const chip=page.locator(`.report button[title="${witness.evidence_id}"]`).first();
  // The normal UI collapses long witness lists. Expand one actual fact list.
  if(!await chip.count()) {
    const buttons=await page.locator(witness.type==='runbook'?'.recommendation .text-button':'.report .claim .text-button').all();
    for(const button of buttons){await button.click();if(await chip.count())break;}
  }
  await page.locator(`.report button[title="${witness.evidence_id}"]`).first().click();
  await page.getByRole('dialog').locator('pre').waitFor();
  await record('outside',async()=>{
    await focus(page.getByRole('dialog').locator('.full-id'));await pause(2200);
    await focus(page.getByRole('dialog').locator('pre'));await pause(2400);
  });
  await page.getByRole('button',{name:'Close evidence'}).click();
  await record('report',async()=>{
    await focus(page.locator('.root-cause'));await pause(1500);
    await focus(page.locator('.recommendation'));await pause(3200);
    const download=page.waitForEvent('download');
    await page.getByRole('button',{name:'↓ Export Markdown'}).click();
    await(await download).saveAs(resolve(WORK,'exported-report.md'));await pause(1000);
  });
  await page.goto(web+`/#/evaluations?evaluation=${m.evaluation_id}&incident=${m.incident_id}`);
  await page.getByRole('heading',{name:'Evaluation passed',exact:true}).waitFor();
  await record('evaluation',async()=>{
    await focus(page.locator('.scorecard'));await pause(4200);
    await focus(page.getByRole('heading',{name:'Ground truth',exact:true}));await pause(2500);
  });
} finally {await ctx.close();await browser.close();}
const output={raw_video:await video.path(),clips,shown_outside_bundle:witness.evidence_id,witness_type:witness.type,incident_id:m.incident_id,evaluation_id:m.evaluation_id,source:'Additional real read-only browser close-ups of the same frozen incident/report/scorecard. No mutation, new investigation or score substitution.'};
await save('pickups.json',output);
console.log('Verified close-ups of the original captured result.');
