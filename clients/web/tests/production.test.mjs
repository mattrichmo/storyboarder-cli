import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
let ts;try{ts=require('typescript');}catch{ts=require(process.env.STORYBOARDER_TYPESCRIPT_PATH);}
const source=fs.readFileSync(new URL('../src/production/model.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText;
const m=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
const data=new Map();Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}});
const record={id:crypto.randomUUID(),version:1,revision:3,kind:'scene',data:{kind:'scene',title:'Scene',orders:{narrative:1}}};

test('object merge preserves independent edits',()=>{assert.deepEqual({...m.mergeDraft({a:1,b:1},{a:2,b:1},{a:1,b:2}).value},{a:2,b:2});});
test('arrays stay atomic and conflicting order is not silently merged',()=>{const r=m.mergeDraft({keys:[1,2]},{keys:[2,1]},{keys:[1,2,3]});assert.deepEqual(r.conflicts,['/keys']);assert.deepEqual(r.value.keys,[2,1]);});
test('JSON pointer paths escape hostile keys without prototype mutation',()=>{const base=JSON.parse('{"__proto__":{"a":1},"/tilde~":1}');const ours=JSON.parse('{"__proto__":{"a":2},"/tilde~":2}');const theirs=JSON.parse('{"__proto__":{"a":1},"/tilde~":3}');const r=m.mergeDraft(base,ours,theirs);assert.equal(Object.getPrototypeOf(r.value),null);assert.deepEqual(r.conflicts,['/~1tilde~0']);assert.equal({}.a,undefined);});
test('local drafts are partitioned by project and record',()=>{const d=m.newDraft('a',record,10);d.raw=JSON.stringify({...record.data,title:'Changed'});assert.equal(m.storeDraft(d),'');assert.equal(m.getDraft('a',record.id).draft.raw,d.raw);assert.equal(m.getDraft('b',record.id).draft,null);assert.ok(m.isDirty(d));});
test('malformed local draft is retained with a visible recovery warning',()=>{const k='storyboarder.production.draft:x:y';data.set(k,'{broken');assert.ok(m.getDraft('x','y').error);assert.equal(data.get(k),'{broken');});
test('batch pins base version, header revision and checkpoint, and preserves retry ID',()=>{const d=m.newDraft('x',record,10);const b=m.makeBatch(d,false);assert.equal(b.expected_checkpoint,10);assert.equal(b.operations[0].expected_revision,3);assert.equal(b.operations[0].base_version,1);assert.equal(b.operations[0].select,false);assert.equal(m.makeBatch(d,false).operation_id,b.operation_id);});
test('dirty JSON is never treated as clean',()=>{assert.ok(m.isDirty({...m.newDraft('x',record,0),raw:'{'}));assert.equal(m.isDirty(m.newDraft('x',record,0)),false);});
test('exact source index keeps older pinned versions separate from selection',()=>{const old={...record,version:1,data:{title:'Old'}},current={...record,version:2,data:{title:'Current'}};const index=m.indexVersions({records:[current],pinned_versions:[old]});assert.equal(index.get(m.refKey(m.pin(old))).data.title,'Old');assert.equal(index.get(m.refKey(m.pin(current))).data.title,'Current');});
test('new timing records inherit production timebase without adding invalid fields',()=>{const records=[{kind:'production',is_selected:true,data:{frame_rate:{numerator:24000,denominator:1001},aspect_ratio:{width:2.39,height:1}}}];assert.deepEqual(m.starter('shot',records).frame_rate,records[0].data.frame_rate);assert.equal(m.starter('shot',records).aspect_ratio,undefined);assert.deepEqual(m.starter('camera_setup',records).aspect_ratio,records[0].data.aspect_ratio);});
