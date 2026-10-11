import http from 'node:http';
import fs from 'node:fs';
import {performance} from 'node:perf_hooks';
const agent=new http.Agent({keepAlive:true,maxSockets:50});
const base=new URL(process.env.PROOFIT_URL||'http://127.0.0.1');
let cookie='';
function request(path,body){return new Promise((resolve,reject)=>{const req=http.request({host:'127.0.0.1',port:Number(base.port||80),path:'/api'+path,method:body?'POST':'GET',agent,headers:{cookie,Origin:base.origin,Host:base.host,...(body?{'content-type':'application/json'}:{})}},res=>{let data='';res.on('data',s=>data+=s);res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,data}));});req.on('error',reject);req.setTimeout(30000,()=>req.destroy(new Error('timeout')));req.end(body?JSON.stringify(body):undefined);});}
const account=JSON.parse(fs.readFileSync('runtime/test-accounts.json','utf8')).employer;
const auth=await request('/auth/login',{email:account.email,password:account.password});if(auth.status!==200)throw Error('Authentication failed');cookie=auth.headers['set-cookie'][0].split(';')[0];
const first=JSON.parse((await request('/candidates?limit=1')).data).items[0].id;
const options=['/candidates?specialization=backend_python&limit=20','/candidates?specialization=devops&grade=middle&limit=20','/candidates?vacancy_id=RV0001&limit=5','/candidates/'+first,'/invitations','/vacancies?limit=30','/candidates?limit=12'];
const times=[],errors=[],by={};let next=0;const start=performance.now();
await Promise.all(Array.from({length:50},async()=>{while(next<2000){const path=options[next++%options.length],t=performance.now();try{const r=await request(path);const ms=performance.now()-t;times.push(ms);(by[path]??=[]).push(ms);if(r.status!==200)errors.push({path,status:r.status});}catch(e){errors.push({path,error:e.message})}}}));
const elapsed=(performance.now()-start)/1000;const percentile=(v,p)=>Number([...v].sort((a,b)=>a-b)[Math.min(v.length-1,Math.floor(v.length*p))].toFixed(2));
const report={concurrency:50,requests:2000,errors:errors.length,p50_ms:percentile(times,.5),p95_ms:percentile(times,.95),p99_ms:percentile(times,.99),elapsed_seconds:Number(elapsed.toFixed(2)),requests_per_second:Number((2000/elapsed).toFixed(2)),workload:'Node native HTTP keep-alive, 50 closed-loop clients, 2000 authenticated mixed requests through gateway; public Host, real login, loopback transport. Windows i7-7700HQ/32 GB, same laptop hosts generator and service. Includes ranked/full-bank search, profile, invitations, vacancies; excludes OCR/LLM/forecast generation. Separate from extended product workload.',by_endpoint:Object.fromEntries(Object.entries(by).map(([p,v])=>[p,{requests:v.length,p95_ms:percentile(v,.95)}])),error_details:errors};
report.measured_at_utc=new Date().toISOString();
fs.writeFileSync('validation/reports/current/performance-native.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));agent.destroy();
if(errors.length)throw Error(`Native load verification failed: ${errors.length} HTTP errors`);
