/** Small view contracts; the authoritative strict schemas come from production.schema. */
export type Ref={id:string;version:number};
export type Vec={x:number;y:number;z:number};
export type Pose={position:Vec;yaw_deg:number;pitch_deg:number;roll_deg:number};
export interface RecordVersion{ id:string;kind:string;revision:number;version:number;head_version:number;selected_version:number|null;archived:boolean;is_selected:boolean;sha256:string;data:Record<string,any>;version_created_at:string }
export interface Snapshot{checkpoint:number;records:RecordVersion[];pinned_versions:RecordVersion[];total:number;next_offset:number|null;snapshot_sha256:string}
export interface Finding{code:string;message:string;record_id:string|null;version:number|null;title:string;field:string;category:string;severity:string;status:string;reason?:string;responsibility:string;next_action:string;details:any}
export interface Report{checkpoint:number;summary:{selected_records:number;scenes:number;shots:number;open_issues:number;stale_records:number;proposals:number};structural:{valid:boolean;errors:number};planning:{complete:boolean;gaps:number};creative:{accepted:boolean;shots:any[]};issues:Finding[];coverage:{material:any[];beats:any[];summary:any};equipment:{items:any[];limitations:string[]}}
export interface Evaluation{checkpoint:number;evaluator:string;source:Ref&{sha256:string};action_frame:number;frame_rate:{numerator:number;denominator:number}|null;duration_frames:number;seconds:number;location:any;instances:any[];cameras:any[];fixtures:any[];paths:any[];beats:any[];warnings:any[];limitations:string[]}
export interface Draft {format:'production-draft/v1';project:string;id:string;base_revision:number;base_version:number;checkpoint:number;base:Record<string,any>;raw:string;operation_id:string;updated_at:string}
export const KINDS=['production','sequence','script','location','asset','scene','action','camera_setup','lighting_setup','shot','panel','animatic','edit','take','review','annotation','exception'];
export const VIEWS=['Spatial','Script','Coverage','Records','Panels','Review'];
export const pretty=(value:unknown)=>JSON.stringify(value,null,2);
export const pin=(r:RecordVersion):Ref=>({id:r.id,version:r.version});
export const refKey=(ref:Ref)=>`${ref.id}@${ref.version}`;
export const label=(value:string)=>value.replace(/_/g,' ');
export const uid=()=>crypto.randomUUID();
export function indexVersions(snapshot:Snapshot):Map<string,RecordVersion>{
 const map=new Map<string,RecordVersion>();for(const r of [...snapshot.pinned_versions,...snapshot.records])map.set(refKey(pin(r)),r);return map;
}
export function getDraft(project:string,id:string):{draft:Draft|null;error:string}{
 try{const raw=localStorage.getItem(`storyboarder.production.draft:${project}:${id}`);if(!raw)return{draft:null,error:''};
 if(raw.length>2_000_000)return{draft:null,error:'Stored draft exceeds 2 MB. It was left in browser storage, not deleted.'};
 const d=JSON.parse(raw);if(d.format!=='production-draft/v1'||d.project!==project||d.id!==id||typeof d.raw!=='string'||!d.base||!Number.isSafeInteger(d.base_revision)||!Number.isSafeInteger(d.base_version))return{draft:null,error:'A stored draft could not be validated. It was not deleted.'};return{draft:d,error:''};
 }catch{return{draft:null,error:'Local draft storage is unavailable. Export your draft JSON before navigating away.'};}
}
export function storeDraft(draft:Draft):string{
 try{const raw=JSON.stringify(draft);if(raw.length>2_000_000)return'Draft exceeds the browser storage limit. Export JSON to preserve it.';localStorage.setItem(`storyboarder.production.draft:${draft.project}:${draft.id}`,raw);return'';}catch{return'Browser storage is full or unavailable. Your in-memory draft is NOT backed up. Export draft JSON.';}
}
export function clearDraft(project:string,id:string):string{try{localStorage.removeItem(`storyboarder.production.draft:${project}:${id}`);return'';}catch{return'The saved draft could not be removed from browser storage.';}}
export function newDraft(project:string,r:RecordVersion,checkpoint:number):Draft{return{format:'production-draft/v1',project,id:r.id,base_revision:r.revision,base_version:r.version,checkpoint,base:structuredClone(r.data),raw:pretty(r.data),operation_id:uid(),updated_at:new Date().toISOString()};}
export function isDirty(draft:Draft|null):boolean{if(!draft)return false;try{return JSON.stringify(JSON.parse(draft.raw))!==JSON.stringify(draft.base);}catch{return true;}}
/** Object fields merge independently; arrays are atomic, never reordered or heuristically joined. */
export function mergeDraft(base:any,ours:any,theirs:any,path=''): {value:any;conflicts:string[]}{
 const same=(a:any,b:any)=>JSON.stringify(a)===JSON.stringify(b);
 if(same(ours,base))return{value:theirs,conflicts:[]};if(same(theirs,base)||same(ours,theirs))return{value:ours,conflicts:[]};
 const object=(v:any)=>v!==null&&typeof v==='object'&&!Array.isArray(v);
 if(object(base)&&object(ours)&&object(theirs)){
 const value:Record<string,any>=Object.create(null),conflicts:string[]=[];
 for(const key of new Set([...Object.keys(base),...Object.keys(ours),...Object.keys(theirs)])){const result=mergeDraft(base[key],ours[key],theirs[key],`${path}/${key.replace(/~/g,'~0').replace(/\//g,'~1')}`);if(result.value!==undefined)value[key]=result.value;conflicts.push(...result.conflicts);}return{value,conflicts};}
 return{value:ours,conflicts:[path||'/']};
}
export function makeBatch(draft:Draft,select:boolean){return{expected_checkpoint:draft.checkpoint,operation_id:draft.operation_id,operations:[{op:'put',id:draft.id,expected_revision:draft.base_revision,base_version:draft.base_version||null,select,data:JSON.parse(draft.raw)}]};}
export function downloadJSON(value:unknown,name:string){const url=URL.createObjectURL(new Blob([pretty(value)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function starter(kind:string,records:RecordVersion[]):Record<string,any>{
 const first=(k:string)=>{const r=records.find(x=>x.kind===k&&x.is_selected);return r?pin(r):null;};
 const defaults=records.find(r=>r.kind==='production'&&r.is_selected)?.data;
 const data:Record<string,any>={kind,title:`New ${label(kind)}`,provenance:{origin:'human',rationale:''}};
 if(defaults&&['action','shot','animatic','edit','take'].includes(kind))data.frame_rate=structuredClone(defaults.frame_rate);
 if(defaults&&kind==='camera_setup')data.aspect_ratio=structuredClone(defaults.aspect_ratio);
 if(kind==='asset')data.category='prop';
 if(['action','camera_setup','lighting_setup','shot'].includes(kind))data.scene=first('scene');
 if(['action','camera_setup','lighting_setup'].includes(kind))data.location=first('location');
 if(kind==='action')data.duration_frames=240;
 if(['panel','take'].includes(kind))data.shot=first('shot');
 if(kind==='take')data.slate='Unslated';
 if(kind==='review')Object.assign(data,{subject:first('shot')||first('scene'),decision:'changes_requested',dimension:'creative',reviewer:'',reason:''});
 if(kind==='annotation')Object.assign(data,{subject:first('shot')||first('scene'),body:'',author:''});
 if(kind==='exception')Object.assign(data,{subject:first('shot'),check_code:'',reason:'',reviewer:''});
 return data;
}
