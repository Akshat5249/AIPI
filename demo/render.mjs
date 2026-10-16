/** Assemble real recorded clips and editorial cards into a portable H.264 MP4. */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {HERE,WORK,exec} from './shared.mjs';
import {makeCards,CAPTIONS} from './cards.mjs';
const ffmpeg=process.env.FFMPEG || 'ffmpeg';
const capture=JSON.parse(await readFile(resolve(WORK,'capture.json'),'utf8'));
await makeCards();
const pickups=JSON.parse(await readFile(resolve(WORK,'pickups.json'),'utf8'));
assert.equal(pickups.incident_id,capture.incident_id,'Close-ups must belong to the captured incident');
assert.equal(pickups.evaluation_id,capture.evaluation_id,'Close-ups must show the same scored run');
assert(capture.cited_outside_bundle.includes(pickups.shown_outside_bundle));
const edited=capture.scenes.flatMap(c=>{
  const detail=pickups.clips[c.id];
  if(!detail)return [c];
  const lead=c.id==='trace'?1.5:c.id==='evaluation'?2:0;
  return [...(lead?[{...c,id:c.id+'-lead',caption_id:c.id,duration:lead,end:c.start+lead}]:[]),{...detail,id:c.id,caption_id:c.id,duration:c.duration-lead,raw_video:pickups.raw_video}];
});
const clips=[{id:'title',duration:6},{id:'architecture',duration:6},...edited,{id:'engineering',duration:7},{id:'ending',duration:6}];
let position=0;
for(let i=0;i<clips.length;i++) {
  const clip=clips[i];clip.output=resolve(WORK,`edit-${String(i).padStart(2,'0')}.mp4`);clip.timeline_start=position;position+=clip.duration;
  const fade=`fade=t=in:st=0:d=0.18,fade=t=out:st=${clip.duration-0.18}:d=0.18,format=yuv420p`;
  const args=['-hide_banner','-loglevel','error','-y'];
  if(clip.start!==undefined) {
    const rawDuration=clip.end-clip.start;
    args.push('-ss',String(clip.start),'-t',String(rawDuration),'-i',clip.raw_video || capture.raw_video,'-loop','1','-i',resolve(WORK,`overlay-${clip.caption_id || clip.id}.png`),'-filter_complex',`[0:v]setpts=${clip.duration/rawDuration}*(PTS-STARTPTS),fps=30,scale=1920:1080:flags=lanczos,setsar=1,tpad=stop_mode=clone:stop_duration=1[base];[base][1:v]overlay=0:0,${fade}[v]`,'-map','[v]');
  } else {
    args.push('-loop','1','-i',resolve(WORK,`${clip.id}.png`),'-vf',`fps=30,${fade}`);
  }
  args.push('-t',String(clip.duration),'-an','-c:v','libx264','-preset','fast','-crf','21','-threads','2','-pix_fmt','yuv420p','-r','30','-movflags','+faststart',clip.output);
  await exec(ffmpeg,args);
  console.log(`Encoded ${clip.id}: ${clip.duration}s`);
}
const list=resolve(WORK,'concat.txt');
await writeFile(list,clips.map(c=>`file '${c.output.replaceAll("'","'\\''")}'`).join('\n')+'\n');
const output=resolve(HERE,'aipi-demo.mp4');
await exec(ffmpeg,['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',list,'-c','copy','-movflags','+faststart',output]);
const bytes=await readFile(output);
if(bytes.length>25_000_000) throw new Error('Video exceeds the conservative 25 MB repository budget; prepare a release asset instead.');
const final={...capture};delete final.raw_video;delete final.scenes;
final.shown_outside_bundle=pickups.shown_outside_bundle;final.outside_witness_type=pickups.witness_type;final.detail_capture_source=pickups.source;
final.video={file:'aipi-demo.mp4',width:1920,height:1080,fps:30,duration_seconds:position,codec:'H.264',pixel_format:'yuv420p',audio:'none; professional on-screen captions',bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),faststart:true};
final.chapters=clips.map(c=>({id:c.id,start:c.timeline_start,duration:c.duration,caption:CAPTIONS[c.caption_id || c.id]?.[0] || c.id}));
await writeFile(resolve(HERE,'capture-manifest.json'),JSON.stringify(final,null,2)+'\n');
function clock(seconds) {const ms=Math.round(seconds*1000), s=Math.floor(ms/1000);return `00:${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')},${String(ms%1000).padStart(3,'0')}`;}
await writeFile(resolve(HERE,'aipi-demo.srt'),clips.map((c,i)=>`${i+1}\n${clock(c.timeline_start)} --> ${clock(c.timeline_start+c.duration)}\n${CAPTIONS[c.caption_id || c.id]?.join('\n') || ({title:'AIPI — Real faults. Scoped evidence. Cited reports.',architecture:'OpenTelemetry → PostgreSQL → LangGraph → isolated evaluation',engineering:'Read-only tools. Frozen evidence. Gates against fabricated claims.',ending:'Reproduce with make demo. Deterministic mock; no remediation executed.'}[c.id])}\n`).join('\n'));
console.log(`Rendered ${position}s, 1920×1080 H.264, ${(bytes.length/1e6).toFixed(2)} MB: ${output}`);
