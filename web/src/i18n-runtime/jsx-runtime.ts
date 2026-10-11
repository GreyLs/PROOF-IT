/** Local product-copy translation; no DOM rewriting, external requests or input mutation. */
import { jsx as reactJsx, jsxs as reactJsxs, Fragment } from 'react/jsx-runtime';
import { translate } from '../i18n';
export { Fragment };
export type { JSX } from 'react/jsx-runtime';
const textProps=['title','subtitle','description','eyebrow','label','placeholder','aria-label','alt','text','message'];
function child(value:unknown):unknown {
  if(typeof value==='string')return translate(value);
  if(Array.isArray(value))return value.map(child);
  return value;
}
export function localize(props:any):any {
  if(!props||props['data-no-translate'])return props;
  const result={...props};
  if('children' in props)result.children=child(props.children);
  for(const name of textProps)if(typeof props[name]==='string')result[name]=translate(props[name]);
  // Values, IDs, URLs, code, submitted answers and user input stay untouched.
  return result;
}
export function jsx(type:any,props:any,key?:string) {return reactJsx(type,localize(props),key);}
export function jsxs(type:any,props:any,key?:string) {return reactJsxs(type,localize(props),key);}
