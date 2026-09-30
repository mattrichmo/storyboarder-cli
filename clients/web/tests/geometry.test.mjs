import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
let ts;
try{ts=require('typescript');}catch{ts=require(process.env.STORYBOARDER_TYPESCRIPT_PATH);}
const source=fs.readFileSync(new URL('../src/canvas/geometry.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText;
const {screenToWorld,zoomAt,hitTest,tidy,fit,edgePath,descendants,clamp,NODE_W,NODE_H}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
const entity=(id,kind='asset',parent_id=null,position=0,type='reference')=>({id,kind,parent_id,position,title:id,fields:{type}});
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);

test('screen/world conversion accounts for translation and zoom',()=>{
 assert.deepEqual(screenToWorld({x:320,y:210},{x:20,y:10,scale:2}),{x:150,y:100});
});
test('zoom preserves the world point under the pointer',()=>{
 const v={x:-102,y:72,scale:.65},p={x:283,y:172},before=screenToWorld(p,v),after=screenToWorld(p,zoomAt(v,p,1.8));
 close(before.x,after.x);close(before.y,after.y);
});
test('zoom stays within accessible operational bounds',()=>{
 assert.equal(zoomAt({x:0,y:0,scale:1},{x:0,y:0},100).scale,3);
 assert.equal(zoomAt({x:0,y:0,scale:1},{x:0,y:0},.001).scale,.15);
 assert.equal(clamp(15,-1,10),10);
});
test('hit testing includes card boundaries and favors topmost card',()=>{
 const positions={a:{x:0,y:0},b:{x:50,y:50}};
 assert.equal(hitTest({x:50,y:50},positions),'b');
 assert.equal(hitTest({x:0,y:0},positions),'a');
 assert.equal(hitTest({x:50+NODE_W,y:50+NODE_H},positions),'b');
 assert.equal(hitTest({x:-1,y:0},positions),null);
});
test('asset tidy uses semantic type columns deterministically',()=>{
 const nodes=[entity('z','asset',null,0,'prop'),entity('m','asset',null,0,'character'),entity('l','asset',null,0,'location')];
 const a=tidy(nodes,[],'assets');
 assert.deepEqual(a,tidy([...nodes].reverse(),[],'assets'));
 assert.ok(a.m.x<a.l.x&&a.l.x<a.z.x);
 assert.equal(nodes[0].id,'z');
});
test('story tidy places hierarchy in columns without changing order',()=>{
 const nodes=[entity('seq','sequence'),entity('scene','scene','seq'),entity('b','shot','scene',1),entity('a','shot','scene',0)];
 const a=tidy(nodes,[],'story');assert.ok(a.seq.x<a.scene.x&&a.scene.x<a.a.x);assert.ok(a.a.y<a.b.y);
 assert.deepEqual(a,tidy([...nodes].reverse(),[],'story'));
});
test('scene-board tidy separates ordered shots from source images',()=>{
 const a=tidy([entity('scene','scene'),entity('shot1','shot','scene'),entity('shot2','shot','scene',1),entity('asset')],[],'scene');
 assert.ok(a.shot1.x<a.shot2.x);assert.ok(a.asset.y>a.shot1.y);assert.ok(a.scene.y<a.shot1.y);
});
test('fit centers and contains ordinary layouts',()=>{
 const p={a:{x:-100,y:-200},b:{x:500,y:300}},v=fit(p,1200,900);
 for(const point of Object.values(p)){assert.ok(point.x*v.scale+v.x>=0);assert.ok(point.y*v.scale+v.y>=0);assert.ok((point.x+NODE_W)*v.scale+v.x<=1200);assert.ok((point.y+NODE_H)*v.scale+v.y<=900);}
 assert.deepEqual(fit({},1000,800),{x:60,y:60,scale:1});
});
test('edge paths and labels are finite for forward and backward edges',()=>{
 for(const p of [{x:600,y:100},{x:-100,y:-300}]){
  const r=edgePath({x:0,y:0},p);assert.match(r.path,/^M .* C /);assert.ok(Number.isFinite(r.label.x)&&Number.isFinite(r.label.y));assert.ok(!r.path.includes('NaN'));
 }
});
test('collapsed descendants hide presentation children, not their parent',()=>{
 const nodes=[entity('seq','sequence'),entity('scene','scene','seq'),entity('shot','shot','scene'),entity('asset')];
 assert.deepEqual([...descendants(nodes,['seq'])],['scene','shot']);assert.equal(descendants(nodes,['scene']).has('scene'),false);
});
