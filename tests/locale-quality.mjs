import test from 'node:test';
import assert from 'node:assert/strict';
import {assetHash,verifyLocaleAssets} from '../web/locale-quality.mjs';
const source={'Войти':'Войти'},catalog={'Войти':'Sign in'};
function fixture(){return {languages:{en:{critical_ready:true,source_sha256:assetHash(source),catalog_sha256:assetHash(catalog),source_key_count:1,catalog_key_count:1,structural_invalid_keys:[]}}};}
test('exact versioned assets admitted',()=>assert.deepEqual(verifyLocaleAssets(source,fixture(),{en:catalog}),['en']));
test('catalog changed after review rejected',()=>assert.throws(()=>verifyLocaleAssets(source,fixture(),{en:{'Войти':'Opposite meaning'}}),/Stale/));
test('source changed after review rejected',()=>assert.throws(()=>verifyLocaleAssets({'Войти':'Другой смысл'},fixture(),{en:catalog}),/Stale/));
test('empty copy rejected even with recomputed digest',()=>{const qa=fixture(),empty={'Войти':''};qa.languages.en.catalog_sha256=assetHash(empty);assert.throws(()=>verifyLocaleAssets(source,qa,{en:empty}),/Stale/);});
test('unreviewed draft remains disabled',()=>{const qa=fixture();qa.languages.en.critical_ready=false;assert.deepEqual(verifyLocaleAssets(source,qa,{en:catalog}),[]);});
