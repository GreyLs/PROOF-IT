import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from '../web/node_modules/typescript/lib/typescript.js';
import {graphSkills,graphSources,hasVerifiedTransfer} from '../web/src/graph-model.ts';

const source=fs.readFileSync(new URL('../web/src/navigation.tsx',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
const module={exports:{}};
new Function('require','module','exports',compiled)(name=>name==='react'?{}:new Proxy({}, {get:(_,key)=>String(key)}),module,module.exports);
const {workspaceNavigation}=module.exports;

for(const employer of [false,true])test('navigation preserves scoped pages, seven primary groups: '+employer,()=>{
  const groups=workspaceNavigation(employer),pages=groups.flatMap(group=>group.entries.map(entry=>entry.page));
  assert.equal(groups.length,7);assert.equal(new Set(pages).size,pages.length);
  assert.ok(pages.includes('messages')&&pages.includes('security')&&pages.includes('validation'));
  for(const page of employer?['search','vacancies','applications','invitations','horizon','evidence','strategy','research-lab','assessment-lab','tasks','documents','company']:['horizon','proof-graph','evidence','research-lab','career-route','arena','professional-assessment','profile','resumes','assessment','vacancies','invitations','applications','tasks','documents','career'])assert.ok(pages.includes(page),page);
  assert.ok(!pages.includes(employer?'resumes':'search'));
});

const graph={nodes:[{id:'s:python',label:'python',kind:'skill',strength:.8},{id:'s:git',label:'git',kind:'skill',strength:0},{id:'r:backend',kind:'role',label:'Backend',required_skills:['python','git','sql']},{id:'e:a',label:'Practice',kind:'evidence',source_id:'a'}],
  edges:[{from:'e:a',to:'s:python',weight:.8,relation:'supports'},{from:'s:python',to:'r:backend',weight:.84,relation:'transfers_to'}],evidence:[{id:'a',source:'sandbox'}]};
test('missing requirements are shown but never invented as evidence',()=>{const rows=graphSkills(graph,'r:backend');assert.equal(rows.length,3);assert.equal(rows[0].id,'s:python');assert.equal(rows.find(row=>row.id==='s:sql').strength,0);assert.deepEqual(graphSources(graph,'s:sql'),[]);assert.equal(hasVerifiedTransfer(graph,'s:sql','r:backend'),false);});
test('source inspector resolves exact provenance and relation',()=>{const rows=graphSources(graph,'s:python');assert.equal(rows.length,1);assert.equal(rows[0].evidence.id,'a');assert.equal(rows[0].edge.weight,.8);assert.equal(hasVerifiedTransfer(graph,'s:python','r:backend'),true);});
test('skill search is case insensitive and does not mutate source graph',()=>{const before=JSON.stringify(graph);assert.deepEqual(graphSkills(graph,'r:backend',' SQL ').map(row=>row.id),['s:sql']);assert.equal(JSON.stringify(graph),before);});
