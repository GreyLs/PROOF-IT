import type {Plugin} from 'vite';
export function assetHash(value:Record<string,string>):string;
export function verifyLocaleAssets(source:Record<string,string>,qa:unknown,catalogs:Record<string,Record<string,string>>):string[];
export function localeQualityGate():Plugin;
