import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

// Same canonical flat-string JSON representation as the Python QA writer.
export function assetHash(value){
 const canonical='{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+': '+JSON.stringify(value[key])).join(', ')+'}';
 return createHash('sha256').update(canonical,'utf8').digest('hex');
}
export function verifyLocaleAssets(source,qa,catalogs){
 const sourceHash=assetHash(source),keys=Object.keys(source),ready=[];
 for(const language of ['en','kk','uz','az','be']){
  const state=qa.languages?.[language],catalog=catalogs[language];
  if(state?.critical_ready!==true)continue; // Intentional drafts remain disabled.
  if(!catalog||state.source_sha256!==sourceHash||state.catalog_sha256!==assetHash(catalog)
    ||Object.keys(catalog).length!==keys.length||!keys.every(key=>typeof catalog[key]==='string'&&catalog[key].trim())
    ||state.source_key_count!==keys.length||state.catalog_key_count!==keys.length
    ||state.structural_invalid_keys?.length!==0){
   throw new Error('Stale or invalid locale QA: '+language+'. Review the exact assets before enabling them.');
  }
  ready.push(language);
 }
 return ready;
}
export function localeQualityGate(){
 return {name:'proofit-locale-integrity',buildStart(){
  const read=name=>JSON.parse(readFileSync(new URL('./src/locales/'+name+'.json',import.meta.url),'utf8'));
  verifyLocaleAssets(read('ru'),read('qa-status'),Object.fromEntries(['en','kk','uz','az','be'].map(lang=>[lang,read(lang)])));
 }};
}
