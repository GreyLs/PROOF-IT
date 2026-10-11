import { jsxDEV as reactJsxDEV } from 'react/jsx-dev-runtime';
import { localize } from './jsx-runtime';
export { Fragment } from 'react/jsx-runtime';
export type { JSX } from 'react/jsx-runtime';
export function jsxDEV(type:any,props:any,key:any,isStaticChildren:boolean,source:any,self:any) {
  return reactJsxDEV(type,localize(props),key,isStaticChildren,source,self);
}
