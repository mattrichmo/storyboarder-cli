import React,{useState} from '../react';
import type {Command,State,Meta} from '../types';
import {runCommand,ApiError} from '../api';
import {selectOptions,allRecords,commandDefaults,fieldLabel,emptySourceMessage} from '../utils';
import {Modal,ErrorNotice,Badge} from './Primitives';

export function ActionDialog({command,state,meta,defaults={},onClose,onDone,onReload}:{command:Command;state:State;meta:Meta;defaults?:Record<string,any>;onClose:()=>void;onDone:(result:any,name:string)=>void|Promise<void>;onReload:()=>Promise<State>}){
 const initialize=(initial:Record<string,any>)=>({...Object.fromEntries(command.fields.map(f=>[f.name,initial[f.name]??f.default??(f.type==='boolean'?false:f.type==='json'?'{}':'')])),...(initial.asset_id?{asset_id:initial.asset_id}:{})});
 const [values,setValues]=useState<Record<string,any>>(()=>initialize(defaults));
 const [busy,setBusy]=useState(false);const [error,setError]=useState<ApiError|null>(null);
 const [confirmed,setConfirmed]=useState(false);
 const set=(name:string,value:any)=>{setValues(previous=>{const next={...previous,[name]:value};const record=allRecords(state).find(r=>r.id===value);
  if(record&&['id','source_id'].includes(name)){next.revision=record.revision;if(command.name.endsWith('.update')){Object.assign(next,commandDefaults(record));}}
  if(record&&name==='target_id'&&'target_revision'in next)next.target_revision=record.revision;
  if(name==='asset_id')next.media_id='';return next;});};
 async function submit(e:any){e.preventDefault();setBusy(true);setError(null);try{
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
 const result=await runCommand(state.project.id,command.name,payload);await onDone(result,command.name);onClose();
 }catch(e){setError(e instanceof ApiError?e:new ApiError('invalid',e instanceof Error?e.message:String(e)));}finally{setBusy(false);}}
 async function cancelRun(){try{const fresh=await onReload();const job=fresh.jobs.find(j=>j.id===values.id);if(job&&['queued','running'].includes(job.status))await runCommand(state.project.id,'job.cancel',{id:job.id,revision:job.revision});}catch(e){setError(e instanceof ApiError?e:new ApiError('invalid',String(e)));}}
 async function reload(){const fresh=await onReload();const current=allRecords(fresh).find(r=>r.id===values.id);if(current){setValues(initialize(commandDefaults(current)));setError(null);}}
 return <Modal title={command.label} onClose={()=>{if(!busy)onClose();}} wide={command.fields.length>10}><form onSubmit={submit}><div className="modal-body"><p className="muted">{command.read_only?'View information saved in this project.':'Changes are saved to this project and appear throughout Storyboarder.'}</p>{command.name==='job.run'&&<div className="notice warning">Only run tools you trust. They run on this computer with the access allowed to your account.</div>}{error&&<ErrorNotice error={error.message}>{error.status===409&&<><p>Your edits are still here. Refresh the project to see the latest saved details, then reapply your changes.</p><button type="button" onClick={reload}>Refresh project details</button></>}</ErrorNotice>}
 <div className={command.fields.length>10?'form-grid':'form-stack'}>{command.fields.map(f=>{const opts=selectOptions(f,state,meta,values);const isSource=!!f.source||!!f.options.length;const label=fieldLabel(f.name,f.label);
 if(f.name==='revision'||f.name==='target_revision')return <input type="hidden" key={f.name} value={values[f.name]??''}/>;
 if(f.type==='boolean')return <label className="check-field" key={f.name}><input type="checkbox" checked={!!values[f.name]} onChange={(e:any)=>set(f.name,e.target.checked)}/><span>{label}</span></label>;
 return <label className={`field ${f.type==='textarea'||f.type==='json'?'full':''}`} key={f.name}><span>{label}{f.required&&<span aria-hidden="true"> *</span>}</span>{isSource?<select value={values[f.name]??''} onChange={(e:any)=>set(f.name,e.target.value)} required={f.required}><option value="">{f.required?'Choose…':f.name==='location_id'?'Use location from above':'Not set'}</option>{opts.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select>:f.type==='textarea'||f.type==='json'?<textarea rows={f.type==='json'?5:3} value={typeof values[f.name]==='object'?JSON.stringify(values[f.name],null,2):values[f.name]??''} onChange={(e:any)=>set(f.name,e.target.value)} required={f.required} spellCheck={f.type!=='json'}/>:<input type={f.type==='integer'||f.type==='number'?'number':'text'} step={f.type==='number'?'any':undefined} value={Array.isArray(values[f.name])?values[f.name].join(', '):values[f.name]??''} onChange={(e:any)=>set(f.name,e.target.value)} required={f.required}/>} {f.help&&<small>{f.help}</small>}{isSource&&!opts.length&&f.required&&<small className="warning-text">{emptySourceMessage(f.source)}</small>}</label>;
 })}</div>{command.destructive&&<label className="confirm-field"><input type="checkbox" checked={confirmed} onChange={(e:any)=>setConfirmed(e.target.checked)} required/>I understand this will change the project.</label>}</div><div className="modal-footer">{busy&&command.name==='job.run'&&<button type="button" className="danger" onClick={cancelRun}>Stop this run</button>}<button type="button" onClick={onClose} disabled={busy}>Cancel</button><button className={command.destructive?'danger':'primary'} type="submit" disabled={busy||(command.destructive&&!confirmed)}>{busy?'Working…':command.read_only?'Show result':command.label}</button></div></form></Modal>;
}
