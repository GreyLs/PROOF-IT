import React, { useEffect, useRef, useState } from 'react';
import { languages,readyLanguages,setLanguage,useLanguage } from './i18n';
export function LanguageSelector() {
  const language=useLanguage();const [open,setOpen]=useState(false);const container=useRef<HTMLDivElement>(null);
  useEffect(()=>{const close=(event:PointerEvent)=>{if(!container.current?.contains(event.target as Node))setOpen(false);};document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close);},[]);
  const selected=languages.find(x=>x.code===language)!;
  if(readyLanguages.length<2)return null;
  return <div className="language-selector" ref={container} data-no-translate onKeyDown={e=>{if(e.key==='Escape')setOpen(false);}}>
    <button type="button" className="language-trigger" title="Machine-assisted translations; critical flows reviewed" aria-label={`Language: ${selected.name}`} aria-expanded={open} aria-controls="proofit-language-menu" onClick={()=>setOpen(!open)}><span aria-hidden>{selected.flag}</span><small>{language.toUpperCase()}</small></button>
    {open&&<div id="proofit-language-menu" className="language-menu" role="group" aria-label="Language">{readyLanguages.map(x=><button type="button" key={x.code} data-language={x.code} lang={x.code} aria-pressed={x.code===language} onClick={()=>{setLanguage(x.code);setOpen(false);}}><span aria-hidden>{x.flag}</span>{x.name}{x.code===language&&<span aria-hidden>✓</span>}</button>)}</div>}
  </div>;
}
