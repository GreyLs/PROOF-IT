import { useSyncExternalStore } from 'react';
import en from './locales/en.json';
import kk from './locales/kk.json';
import uz from './locales/uz.json';
import az from './locales/az.json';
import be from './locales/be.json';
import ru from './locales/ru.json';
import qa from './locales/qa-status.json';

export const languages = [
  {code:'ru',flag:'🇷🇺',name:'Русский',locale:'ru-RU'},
  {code:'en',flag:'🇬🇧',name:'English',locale:'en-GB'},
  {code:'kk',flag:'🇰🇿',name:'Қазақша',locale:'kk-KZ'},
  {code:'uz',flag:'🇺🇿',name:'O‘zbekcha',locale:'uz-UZ'},
  {code:'az',flag:'🇦🇿',name:'Azərbaycanca',locale:'az-AZ'},
  {code:'be',flag:'🇧🇾',name:'Беларуская',locale:'be-BY'},
] as const;
export type Language = typeof languages[number]['code'];
const catalogs: Partial<Record<Language,Record<string,string>>>={en,kk,uz,az,be};
// Incomplete draft catalogs must never be advertised as translated site versions.
const sourceKeys=Object.keys(ru);
const qaLanguages=qa.languages as Record<string,{critical_ready?:boolean;structural_invalid_keys?:string[];semantic_ready?:boolean}>;
export const readyLanguages=languages.filter(x=>{
  if(x.code==='ru')return true;
  const catalog=catalogs[x.code]||{},status=qaLanguages[x.code];
  return Object.keys(catalog).length===sourceKeys.length && sourceKeys.every(key=>typeof catalog[key]==='string'&&catalog[key].trim().length>0)
    && status?.critical_ready===true && status.structural_invalid_keys?.length===0;
});
const listeners=new Set<()=>void>();
let language:Language='ru';
try {const saved=localStorage.getItem('proofit.language');if(readyLanguages.some(x=>x.code===saved))language=saved as Language;} catch { /* private browsing */ }
document.documentElement.lang=language;
export const getLanguage=()=>language;
export const getLocale=()=>languages.find(x=>x.code===language)!.locale;
export function setLanguage(value:Language) {
  if(!readyLanguages.some(x=>x.code===value))return;
  language=value;
  document.documentElement.lang=value;
  try {localStorage.setItem('proofit.language',value);}catch { /* storage is optional */ }
  listeners.forEach(listener=>listener());
}
export function useLanguage() {
  return useSyncExternalStore(listener=>{listeners.add(listener);return()=>{listeners.delete(listener);};},getLanguage,()=> 'ru' as Language);
}
export function translate(text:string):string {
  if(language==='ru')return text;
  const normalized=text.replace(/\s+/g,' ').trim();
  const result=catalogs[language]?.[normalized];
  return result ? (text.match(/^\s*/)?.[0]||'')+result+(text.match(/\s*$/)?.[0]||'') : text;
}
