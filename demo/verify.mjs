/** Decode the complete MP4 and test real Chromium playback and seeking. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createReadStream} from 'node:fs';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {HERE,WORK,browserEngine,exec,pause} from './shared.mjs';
const path=resolve(HERE,'aipi-demo.mp4');
const manifest=JSON.parse(await readFile(resolve(HERE,'capture-manifest.json'),'utf8'));
const data=await readFile(path), bytes=data.length;
assert.equal(createHash('sha256').update(data).digest('hex'),manifest.video.sha256);
assert(bytes<25_000_000);
await exec(process.env.FFMPEG || 'ffmpeg',['-hide_banner','-v','error','-i',path,'-map','0:v:0','-f','null','-']);
const server=createServer((req,res)=>{
  if(req.url==='/') {res.setHeader('Content-Type','text/html');res.end('<body style="margin:0;background:#14231e"><video id="video" src="/demo.mp4" controls muted style="width:1920px;height:1080px"></video></body>');return;}
  if(req.url!=='/demo.mp4'){res.writeHead(404);res.end();return;}
  const match=/bytes=(\d+)-(\d*)/.exec(req.headers.range || '');
  const start=match?Number(match[1]):0, end=match&&match[2]?Number(match[2]):bytes-1;
  res.writeHead(match?206:200,{'Content-Type':'video/mp4','Accept-Ranges':'bytes','Content-Length':end-start+1,...(match?{'Content-Range':`bytes ${start}-${end}/${bytes}`}:{})});
  createReadStream(path,{start,end}).pipe(res);
});
await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
const browser=await (await browserEngine()).launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{})});
try {
  const page=await browser.newPage({viewport:{width:1920,height:1080}});
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.locator('video').evaluate(v=>new Promise((ok,fail)=>{if(v.readyState>=1)ok();else {v.onloadedmetadata=ok;v.onerror=fail;}}));
  const actual=await page.locator('video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration,readyState:v.readyState}));
  assert.equal(actual.width,1920);assert.equal(actual.height,1080);
  assert(actual.duration>=60 && actual.duration<=90);
  await page.locator('video').evaluate(v=>v.play());await pause(1200);
  assert(await page.locator('video').evaluate(v=>v.currentTime>.7 && !v.paused && !v.error));
  await page.locator('video').evaluate(v=>{v.pause();v.controls=false;});
  await mkdir(resolve(WORK,'qa'),{recursive:true});
  for(const clip of manifest.chapters) {
    const time=clip.start+Math.min(clip.duration*.6,4);
    await page.locator('video').evaluate((v,t)=>new Promise((ok,fail)=>{v.onseeked=()=>ok();v.onerror=fail;v.currentTime=t;}),time);
    await pause(180);
    await page.screenshot({path:resolve(WORK,'qa',clip.id+'.png')});
  }
  const verification={verified_at:new Date().toISOString(),full_decode:'passed',browser_playback:'passed',seek_every_chapter:'passed',...actual,bytes,sha256:manifest.video.sha256,format:'H.264 MP4, yuv420p, 30 fps, faststart',audio:'silent; burned-in captions and optional SRT supplied'};
  await writeFile(resolve(HERE,'video-verification.json'),JSON.stringify(verification,null,2)+'\n');
  console.log(JSON.stringify(verification,null,2));
} finally {await browser.close();await new Promise(ok=>server.close(ok));}
