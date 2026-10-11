import ts from '../web/node_modules/typescript/lib/typescript.js';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../web/src');
const values=new Set();
const normalize=x=>x.replace(/\s+/g,' ').trim();
for(const filename of fs.readdirSync(root).filter(x=>/\.tsx?$/.test(x))){
 const source=ts.createSourceFile(filename,fs.readFileSync(path.join(root,filename),'utf8'),ts.ScriptTarget.Latest,true,filename.endsWith('tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);
 function visit(node){
  if(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node)||ts.isJsxText(node)){
   const text=normalize(node.text);
   if(/[А-Яа-яЁё]/.test(text))values.add(text);
  }
  ts.forEachChild(node,visit);
 }
 visit(source);
}
const catalog=[...values].sort();
fs.mkdirSync(path.join(root,'locales'),{recursive:true});
fs.writeFileSync(path.join(root,'locales','ru.json'),JSON.stringify(Object.fromEntries(catalog.map(x=>[x,x])),null,2)+'\n');
console.log(JSON.stringify({entries:catalog.length,long:catalog.filter(x=>x.length>160).length,characters:catalog.join('').length}));
