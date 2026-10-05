import React,{useEffect,useRef,useState} from '../react';
import type {Command,State,Meta} from '../types';
import {api,projectPath,ApiError} from '../api';
import {selectOptions,allRecords,commandDefaults,fieldLabel,emptySourceMessage} from '../utils';
import {Modal,ErrorNotice,Badge} from './Primitives';

const remoteSources=new Set(['documents','document_nodes','versions','provenance_edges','annotations','provenance_endpoints','provenance_source','provenance_target','provenance_typed_endpoint']);
type ChoiceRecord={id:string;label:string;revision?:number;document_revision?:number;[key:string]:any};
type ChoicePage={items:ChoiceRecord[];next_offset:number|null};

export function ActionDialog({command,state,meta,defaults={},onClose,onDone,onReload}:{command:Command;state:State;meta:Meta;defaults?:Record<string,any>;onClose:()=>void;onDone:(result:any,name:string)=>void|Promise<void>;onReload:()=>Promise<State>}){
 const initialize=(initial:Record<string,any>)=>({...Object.fromEntries(command.fields.map(f=>[f.name,initial[f.name]??f.default??(f.type==='boolean'?false:f.type==='json'?'{}':'')])),...(initial.asset_id?{asset_id:initial.asset_id}:{})});
 const [values,setValues]=useState<Record<string,any>>(()=>initialize(defaults));
 const [busy,setBusy]=useState(false);const busyRef=useRef(false);const [cancelBusy,setCancelBusy]=useState(false);const [error,setError]=useState<ApiError|null>(null);
 const [confirmed,setConfirmed]=useState(false);
 const [choices,setChoices]=useState<Record<string,ChoicePage>>({});
 const [queries,setQueries]=useState<Record<string,string>>({});
 const [choiceRecords,setChoiceRecords]=useState<Record<string,ChoiceRecord>>({});
 const [choiceLoading,setChoiceLoading]=useState<Record<string,boolean>>({});
 const [resolving,setResolving]=useState<Record<string,boolean>>({});
 const valuesRef=useRef(values);valuesRef.current=values;
 const queriesRef=useRef(queries);queriesRef.current=queries;
 const alive=useRef(true);
 const requests=useRef<Record<string,AbortController>>({});
 const stateRef=useRef(state);stateRef.current=state;
 const contextFields=['id','document_id','version_id','source_type','target_type','endpoint_type','kind','record_id','endpoint_id'];
 const context=Object.fromEntries(command.fields.filter(f=>['id','document_id','version_id','source_type','target_type','endpoint_type','kind','record_id','endpoint_id'].includes(f.name)).map(f=>[f.name,values[f.name]]));
 const contextKey=JSON.stringify(context);
 function contextFor(current:Record<string,any>){return JSON.stringify(Object.fromEntries(command.fields.filter(f=>contextFields.includes(f.name)).map(f=>[f.name,current[f.name]])));}
 function selectionKey(current:Record<string,any>){return JSON.stringify(Object.fromEntries(command.fields.filter(f=>remoteSources.has(f.source)||f.name.endsWith('_id')).map(f=>[f.name,current[f.name]])));}
 function scopedRequestKey(current:Record<string,any>){return JSON.stringify({project:stateRef.current.project.id,command:command.name,context:contextFor(current),selection:selectionKey(current)});}
 function scopedRequestIsCurrent(name:string,controller:AbortController,key:string,current=valuesRef.current){return alive.current&&!controller.signal.aborted&&requests.current[name]===controller&&scopedRequestKey(current)===key;}
 function invalidateScopedRequests(previous:Record<string,any>,next:Record<string,any>){
  const changed=command.fields.some(f=>(remoteSources.has(f.source)||f.name.endsWith('_id')||contextFields.includes(f.name))&&previous[f.name]!==next[f.name]);
  if(changed)for(const name of ['reload','cancelRun']){requests.current[name]?.abort();delete requests.current[name];}
 }
 function fieldContext(name:string,current=valuesRef.current){
  const source=command.fields.find(f=>f.name===name)?.source;
  const names=source==='document_nodes'?['document_id','version_id']:source==='versions'?['document_id','id']:source==='provenance_source'?['source_type']:source==='provenance_target'?['target_type']:source==='provenance_typed_endpoint'?['kind','endpoint_type']:source==='provenance_endpoints'?['source_type','target_type','kind','endpoint_type']:[];
  return JSON.stringify(Object.fromEntries(names.filter(key=>command.fields.some(f=>f.name===key)).map(key=>[key,current[key]])));
 }
 function requestKey(name:string){return fieldContext(name)+'|'+(queriesRef.current[name]||'');}
 function dependentFields(name:string){
  if(name==='document_id'||name==='id'&&command.fields.find(f=>f.name===name)?.source==='documents')return ['version_id','node_id','parent_id'];
  return ({version_id:['parent_id','node_id'],source_type:['source_id'],target_type:['target_id'],kind:['record_id'],endpoint_type:['endpoint_id']} as Record<string,string[]>)[name]||[];
 }
 function clearDependents(name:string,value:any){
  const cleared=valuesRef.current[name]!==value?dependentFields(name):[];
  for(const field of cleared){requests.current['record:'+field]?.abort();delete requests.current['record:'+field];}
  if(cleared.length){invalidateScopedRequests(valuesRef.current,{...valuesRef.current,...Object.fromEntries(cleared.map(field=>[field,'']))});setResolving(previous=>({...previous,...Object.fromEntries(cleared.map(field=>[field,false]))}));setChoiceRecords(previous=>{const next={...previous};for(const field of cleared)delete next[field];return next;});}
  return cleared;
 }
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;for(const controller of Object.values(requests.current))controller.abort();};},[]);
 function choicePath(name:string,id?:string){return projectPath(stateRef.current.project.id,`/commands/${encodeURIComponent(command.name)}/fields/${encodeURIComponent(name)}/choices${id?'/'+encodeURIComponent(id):''}`);}
 function asError(e:unknown){return e instanceof ApiError?e:new ApiError('invalid',e instanceof Error?e.message:String(e));}
 function recordValues(previous:Record<string,any>,name:string,record:ChoiceRecord,preserveDraft=false){
  const next={...previous};
  if(['id','document_id','node_id','edge_id','annotation_id'].includes(name)&&record.revision!==undefined)next.revision=record.revision;
  if(!preserveDraft&&command.name==='annotation.update'&&name==='annotation_id'){next.content=record.text;next.state=record.state;}
  return next;
 }
 useEffect(()=>{
  const controller=new AbortController();
  for(const field of command.fields.filter(f=>remoteSources.has(f.source))){
   requests.current['page:'+field.name]?.abort();
   delete requests.current['page:'+field.name];
   const key=requestKey(field.name);
   setChoiceLoading(previous=>({...previous,[field.name]:true}));
   const params=new URLSearchParams({values:contextKey,query:queries[field.name]||'',limit:'100',offset:'0'});
   api<ChoicePage>(choicePath(field.name)+'?'+params,'GET',undefined,controller.signal)
    .then(page=>{if(alive.current&&!controller.signal.aborted&&requestKey(field.name)===key)setChoices(previous=>({...previous,[field.name]:page}));})
    .catch(e=>{if(alive.current&&e.name!=='AbortError'&&!controller.signal.aborted)setError(asError(e));})
    .finally(()=>{if(!controller.signal.aborted)setChoiceLoading(previous=>({...previous,[field.name]:false}));});
  }
  return()=>controller.abort();
 },[command.name,state.project.id,contextKey,JSON.stringify(queries)]);
 useEffect(()=>{for(const field of command.fields.filter(f=>remoteSources.has(f.source)&&valuesRef.current[f.name]))void selectRemote(field.name,valuesRef.current[field.name]);},[command.name,state.project.id]);
 async function selectRemote(name:string,value:string){
  requests.current['record:'+name]?.abort();
  const before=valuesRef.current;
  const cleared=clearDependents(name,value);
  const nextValues={...before,...Object.fromEntries(cleared.map(field=>[field,''])),[name]:value,...(['id','document_id','node_id','edge_id','annotation_id'].includes(name)?{revision:''}:{})};
  invalidateScopedRequests(before,nextValues);
  setValues(previous=>({...previous,...Object.fromEntries(cleared.map(field=>[field,''])),[name]:value,...(['id','document_id','node_id','edge_id','annotation_id'].includes(name)?{revision:''}:{})}));
  setChoiceRecords(previous=>{const next={...previous};delete next[name];return next;});
  if(!value){delete requests.current['record:'+name];setResolving(previous=>({...previous,[name]:false}));return;}
  const controller=new AbortController();requests.current['record:'+name]=controller;
  const key=fieldContext(name);
  setResolving(previous=>({...previous,[name]:true}));
  try{
   const record=await api<ChoiceRecord>(choicePath(name,value)+'?'+new URLSearchParams({values:contextKey}),'GET',undefined,controller.signal);
   if(!alive.current||controller.signal.aborted||requests.current['record:'+name]!==controller||fieldContext(name)!==key||valuesRef.current[name]!==value)return;
   setValues(previous=>previous[name]===value?recordValues(previous,name,record):previous);
   setChoiceRecords(previous=>({...previous,[name]:record}));
  }catch(e){if(alive.current&&!controller.signal.aborted)setError(asError(e));}finally{if(alive.current&&requests.current['record:'+name]===controller){delete requests.current['record:'+name];setResolving(previous=>({...previous,[name]:false}));}}
 }
 async function moreChoices(name:string){
  const offset=choices[name]?.next_offset;if(offset==null)return;
  requests.current['page:'+name]?.abort();
  const controller=new AbortController();requests.current['page:'+name]=controller;
  const key=requestKey(name);
  setChoiceLoading(previous=>({...previous,[name]:true}));
  try{
   const page=await api<ChoicePage>(choicePath(name)+'?'+new URLSearchParams({values:contextKey,query:queries[name]||'',limit:'100',offset:String(offset)}),'GET',undefined,controller.signal);
   if(!alive.current||controller.signal.aborted||requestKey(name)!==key)return;
   setChoices(previous=>({...previous,[name]:{...page,items:[...(previous[name]?.items||[]),...page.items]}}));
  }catch(e){if(alive.current&&!controller.signal.aborted)setError(asError(e));}finally{if(alive.current&&requests.current['page:'+name]===controller){delete requests.current['page:'+name];setChoiceLoading(previous=>({...previous,[name]:false}));}}
 }
 const set=(name:string,value:any)=>{const before=valuesRef.current,cleared=clearDependents(name,value),next={...before,...Object.fromEntries(cleared.map(field=>[field,''])),[name]:value};const record=allRecords(state).find(r=>r.id===value);
  if(record&&['id','source_id'].includes(name)){next.revision=record.revision;if(command.name.endsWith('.update')){Object.assign(next,commandDefaults(record));}}
  if(record&&name==='target_id'&&'target_revision'in next)next.target_revision=record.revision;
  if(name==='asset_id')next.media_id='';invalidateScopedRequests(before,next);setValues(next);};
 async function submit(e:any){e.preventDefault();if(busyRef.current||Object.values(resolving).some(Boolean)||!alive.current)return;busyRef.current=true;setBusy(true);setError(null);const controller=new AbortController();requests.current.submit?.abort();requests.current.submit=controller;try{
 const payload:Record<string,any>={};
 for(const f of command.fields){let v=values[f.name];
  if(v===''&&!f.required){
   if(command.name.endsWith('.update')&&['location_id','duration','media_id'].includes(f.name)){payload[f.name]=null;continue;}
   if(f.source||['integer','number','json','select'].includes(f.type))continue;
   if(!command.name.endsWith('.update')&&!['content','notes'].includes(f.name)&&f.type!=='tags')continue;
  }
  if(f.type==='integer')v=Number.parseInt(v,10);
  if(f.type==='number')v=v===''?null:Number(v);
  if(f.type==='json')v=typeof v==='string'?JSON.parse(v):v;
  if(f.type==='tags')v=Array.isArray(v)?v:String(v).split(',').map(s=>s.trim()).filter(Boolean);
  payload[f.name]=v;
 }
 const result=await api(projectPath(stateRef.current.project.id,`/commands/${encodeURIComponent(command.name)}`),'POST',payload,controller.signal);
 if(!alive.current||controller.signal.aborted||requests.current.submit!==controller)return;
 await onDone(result,command.name);
 if(alive.current&&!controller.signal.aborted&&requests.current.submit===controller)onClose();
 }catch(e){if(alive.current&&!controller.signal.aborted&&requests.current.submit===controller)setError(e instanceof ApiError?e:new ApiError('invalid',e instanceof Error?e.message:String(e)));}finally{busyRef.current=false;if(alive.current&&requests.current.submit===controller){delete requests.current.submit;setBusy(false);}}}
 async function cancelRun(){
  if(!alive.current||cancelBusy)return;
  requests.current.cancelRun?.abort();const controller=new AbortController();requests.current.cancelRun=controller;const key=scopedRequestKey(valuesRef.current);setCancelBusy(true);
  const current=()=>scopedRequestIsCurrent('cancelRun',controller,key);
  try{const fresh=await onReload();if(!current())return;const job=fresh.jobs.find(j=>j.id===valuesRef.current.id);if(job&&['queued','running'].includes(job.status)){await api(projectPath(stateRef.current.project.id,'/commands/job.cancel'),'POST',{id:job.id,revision:job.revision},controller.signal);}}
  catch(e){if(current())setError(asError(e));}
  finally{if(requests.current.cancelRun===controller){delete requests.current.cancelRun;if(alive.current&&!controller.signal.aborted)setCancelBusy(false);}}
 }
 async function reload(){
  requests.current.reload?.abort();const controller=new AbortController();requests.current.reload=controller;
  const selected={...valuesRef.current};const key=scopedRequestKey(selected);const serializedContext=contextFor(selected);
  const current=()=>scopedRequestIsCurrent('reload',controller,key);
  try{
   const fresh=await onReload();if(!current())return;
   const field=command.fields.find(f=>remoteSources.has(f.source)&&['id','document_id','node_id','edge_id','annotation_id'].includes(f.name)&&selected[f.name]);
   if(field){
    const recordId=selected[field.name];
    const record=await api<ChoiceRecord>(choicePath(field.name,recordId)+'?'+new URLSearchParams({values:serializedContext}),'GET',undefined,controller.signal);
    if(!current()||valuesRef.current[field.name]!==recordId)return;
    setValues(previous=>scopedRequestKey(previous)===key&&previous[field.name]===recordId?recordValues(previous,field.name,record,true):previous);
    setChoiceRecords(previous=>scopedRequestKey(valuesRef.current)===key&&valuesRef.current[field.name]===recordId?({...previous,[field.name]:record}):previous);
    if(current())setError(null);
    return;
   }
   const currentRecord=allRecords(fresh).find(record=>record.id===selected.id);
   if(currentRecord){
    setValues(previous=>scopedRequestKey(previous)===key&&previous.id===selected.id?recordValues(previous,'id',currentRecord,true):previous);
    if(current())setError(null);
   }
  }catch(e){if(current())setError(asError(e));}
  finally{if(requests.current.reload===controller)delete requests.current.reload;}
 }
 return <Modal title={command.label} returnFocusSelector="[data-action-search]" onClose={()=>{if(!busy)onClose();}} wide={command.fields.length>10}><form onSubmit={submit}><div className="modal-body"><p className="muted">{command.read_only?'View information saved in this project.':'Changes are saved to this project and appear throughout Storyboarder.'}</p>{command.name==='job.run'&&<div className="notice warning">Only run tools you trust. They run on this computer with the access allowed to your account.</div>}{busy&&<div className="notice" role="status">Saving this action. Editing is paused until the request finishes.</div>}{error&&<ErrorNotice error={error.message}>{error.status===409&&<><p>Your edits are still here. Refresh the project to see the latest saved details, then reapply your changes.</p><button type="button" onClick={reload}>Refresh project details</button></>}</ErrorNotice>}
 <fieldset className="action-fields" disabled={busy}><div className={command.fields.length>10?'form-grid':'form-stack'}>{command.fields.map(f=>{const remote=remoteSources.has(f.source);const records=choices[f.name]?.items||[];const opts=remote?records.map(r=>({value:r.id,label:r.label})):selectOptions(f,state,meta,values);const chosen=choiceRecords[f.name];if(remote&&chosen&&chosen.id===values[f.name]&&!opts.some(o=>o.value===chosen.id))opts.push({value:chosen.id,label:chosen.label||chosen.title||chosen.id});const isSource=!!f.source||!!f.options.length;const label=fieldLabel(f.name,f.label);
 if(f.name==='revision'||f.name==='target_revision')return <input type="hidden" key={f.name} value={values[f.name]??''}/>;
 if(f.type==='boolean')return <label className="check-field" key={f.name}><input type="checkbox" checked={!!values[f.name]} onChange={(e:any)=>set(f.name,e.target.checked)}/><span>{label}</span></label>;
 return <div className={`field ${f.type==='textarea'||f.type==='json'?'full':''}`} key={f.name}>{remote&&<input aria-label={`Search ${label}`} type="search" placeholder={`Search ${label.toLowerCase()}…`} value={queries[f.name]||''} onChange={(e:any)=>setQueries(previous=>({...previous,[f.name]:e.target.value}))}/>}<label className="field"><span>{label}{f.required&&<span aria-hidden="true"> *</span>}</span>{isSource?<select value={values[f.name]??''} onChange={(e:any)=>remote?void selectRemote(f.name,e.target.value):set(f.name,e.target.value)} required={f.required}><option value="">{f.required?'Choose…':f.name==='location_id'?'Use location from above':'Not set'}</option>{opts.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select>:f.type==='textarea'||f.type==='json'?<textarea rows={f.type==='json'?5:3} value={typeof values[f.name]==='object'?JSON.stringify(values[f.name],null,2):values[f.name]??''} onChange={(e:any)=>set(f.name,e.target.value)} required={f.required} spellCheck={f.type!=='json'}/>:<input type={f.type==='integer'||f.type==='number'?'number':'text'} step={f.type==='number'?'any':undefined} value={Array.isArray(values[f.name])?values[f.name].join(', '):values[f.name]??''} onChange={(e:any)=>set(f.name,e.target.value)} required={f.required}/>}</label>{remote&&choiceLoading[f.name]&&<small role="status">Loading choices…</small>}{remote&&choices[f.name]?.next_offset!=null&&<button type="button" disabled={choiceLoading[f.name]} onClick={()=>void moreChoices(f.name)}>Load more {label.toLowerCase()} choices</button>} {f.help&&<small>{f.help}</small>}{isSource&&!opts.length&&!choiceLoading[f.name]&&f.required&&<small className="warning-text">{emptySourceMessage(f.source)}</small>}</div>;
 })}</div></fieldset>{command.destructive&&<label className="confirm-field"><input type="checkbox" checked={confirmed} onChange={(e:any)=>setConfirmed(e.target.checked)} required disabled={busy}/>I understand this will change the project.</label>}</div><div className="modal-footer">{busy&&command.name==='job.run'&&<button type="button" className="danger" disabled={cancelBusy} onClick={cancelRun}>Stop this run</button>}<button type="button" onClick={onClose} disabled={busy}>Cancel</button><button className={command.destructive?'danger':'primary'} type="submit" disabled={busy||Object.values(resolving).some(Boolean)||(command.destructive&&!confirmed)}>{busy?'Working…':command.read_only?'Show result':command.label}</button></div></form></Modal>;
}
