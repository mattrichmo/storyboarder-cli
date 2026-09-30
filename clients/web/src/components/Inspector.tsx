import React,{useEffect,useState,useRef} from '../react';
import type {State,Entity,ActionFn,ResolvedContext} from '../types';
import {mediaUrl,originalUrl,runCommand} from '../api';
import {kindLabel,commandDefaults,human,statusLabel,roleLabel,displayTitle} from '../utils';
import {Icon,Badge,ContextView} from './Primitives';

function shotTitle(entity:Entity){
 const number=String(entity.fields.number||'');
 return number&&entity.title.startsWith(number)
  ? entity.title.slice(number.length).replace(/^\s*[·—:-]\s*/,'')||entity.title
  : entity.title;
}

function labeledRows(value:unknown){
 return String(value||'').split(/\n+/).flatMap(line=>{
  const colon=line.indexOf(':');
  if(colon<1)return [];
  const label=line.slice(0,colon).trim(),text=line.slice(colon+1).trim();
  return label&&text?[{label,value:text}]:[];
 });
}

function SpecList({rows,className=''}:{rows:{label:string;value:string}[];className?:string}){
 return <dl className={`shot-spec-list ${className}`}>{rows.map((row,index)=><div className="shot-spec" key={`${row.label}-${index}`}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>;
}

function ShotDetails({entity,state}:{entity:Entity;state:State}){
 const fields=entity.fields;
 const cameraRows=labeledRows(fields.camera);
 const noteRows=labeledRows(fields.notes);
 const framing=String(fields.framing||'');
 const framingBreak=framing.indexOf(' — ');
 const framingLabel=framingBreak<0?framing:framing.slice(0,framingBreak);
 const framingDetail=framingBreak<0?'':framing.slice(framingBreak+3);
 const location=state.entities.find(e=>e.id===fields.location_id)?.title;
 const scene=state.entities.find(e=>e.id===entity.parent_id);
 const sequence=scene&&state.entities.find(e=>e.id===scene.parent_id);
 const frames=state.frames.filter(frame=>frame.shot_id===entity.id);
 const special=new Set(['number','action','framing','duration','time','location_id','camera','notes','continuity','constraints']);
 const otherFields=Object.entries(fields).filter(([key,value])=>!special.has(key)&&value!==null&&value!=='');
 const action=String(fields.action||entity.description||'No action has been added yet.');
 const displayBeat=shotTitle(entity);
 const summary=action.endsWith(` — ${displayBeat}`)?action.slice(0,-displayBeat.length-3):action;
 const duration=fields.duration==null?'':`${Number(fields.duration)} sec`;

 return <>
  <div className="shot-detail-hero">
   {(sequence||scene)&&<div className="shot-path">{sequence?displayTitle(sequence.title):''}{sequence&&scene?' / ':''}{scene?displayTitle(scene.title):''}</div>}
   <p className="shot-action">{summary}</p>
   <div className="shot-facts">
    {framing&&<div className="shot-fact"><span>Framing</span><strong>{framingLabel}</strong>{framingDetail&&<small>{framingDetail}</small>}</div>}
    {fields.time&&<div className="shot-fact"><span>Time</span><strong>{String(fields.time)}</strong></div>}
    {duration&&<div className="shot-fact"><span>Duration</span><strong>{duration}</strong></div>}
    <div className="shot-fact"><span>Location</span><strong>{location?displayTitle(location):'Not assigned'}</strong></div>
    <div className="shot-fact"><span>Storyboard</span><strong>{frames.length?`${frames.length} storyboard image${frames.length===1?'':'s'}`:'No storyboard image yet'}</strong></div>
   </div>
  </div>
  {fields.camera&&<section className="detail-field shot-camera-field"><div className="shot-section-heading"><h4>Camera plan</h4>{cameraRows.length>0&&<small>{cameraRows.length} settings</small>}</div>{cameraRows.length?<SpecList rows={cameraRows}/>:<p className="prose">{String(fields.camera)}</p>}</section>}
  {fields.continuity&&<section className="detail-field shot-callout"><h4>Continuity</h4><p className="prose">{String(fields.continuity)}</p></section>}
  {fields.constraints&&<section className="detail-field shot-callout"><h4>Production notes</h4><p className="prose">{String(fields.constraints)}</p></section>}
  {fields.notes&&<details className="shot-notes-block"><summary><span>Image, sound & story notes</span><small>{noteRows.length?`${noteRows.length} notes`:'Show notes'}</small></summary>{noteRows.length?<SpecList rows={noteRows} className="shot-note-list"/>:<p className="prose">{String(fields.notes)}</p>}</details>}
  {otherFields.map(([key,value])=><section className="detail-field" key={key}><h4>{human(key)}</h4><p className="prose">{String(value)}</p></section>)}
 </>;
}

export function Inspector({state,id,onClose,onSelect,action}:{state:State;id:string;onClose:()=>void;onSelect:(id:string)=>void;action:ActionFn}){
 const entity=state.entities.find(e=>e.id===id);const [tab,setTab]=useState('details'),[context,setContext]=useState<ResolvedContext|null>(null),[error,setError]=useState('');
 useEffect(()=>{setContext(null);setError('');if(entity&&entity.kind!=='asset')runCommand(state.project.id,'context.resolve',{owner_id:id}).then(setContext).catch(e=>setError(e.message));},[state,id]);
 const panel=useRef<HTMLElement|null>(null);const closeRef=useRef(onClose);closeRef.current=onClose;
 useEffect(()=>{if(entity?.kind==='asset'&&tab==='context')setTab('details');},[entity?.kind,tab]);
 useEffect(()=>{const narrow=window.matchMedia('(max-width:800px)');const el=panel.current;let previous:HTMLElement|null=null;
  const sync=()=>{const main=document.getElementById('main-content');if(main)main.inert=narrow.matches;
   if(el){el.setAttribute('role',narrow.matches?'dialog':'complementary');if(narrow.matches){el.setAttribute('aria-modal','true');previous=document.activeElement as HTMLElement|null;el.querySelector<HTMLElement>('button')?.focus();}else el.removeAttribute('aria-modal');}};
  const key=(e:KeyboardEvent)=>{if(!narrow.matches)return;if(e.key==='Escape'){e.preventDefault();closeRef.current();}
   if(e.key==='Tab'){const items=Array.from(el?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input,select,textarea,[tabindex="0"]')||[]).filter(i=>i.offsetParent!==null);const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}};
  sync();narrow.addEventListener('change',sync);el?.addEventListener('keydown',key);return()=>{narrow.removeEventListener('change',sync);el?.removeEventListener('keydown',key);const main=document.getElementById('main-content');if(main)main.inert=false;previous?.focus();};
 },[]);
 if(!entity)return null;
 const members=state.asset_media.filter(m=>m.asset_id===id),assignments=state.assignments.filter(a=>a.shot_id===id||a.asset_id===id),links=state.links.filter(l=>l.source_id===id||l.target_id===id),frames=state.frames.filter(f=>f.shot_id===id);
 return <aside ref={panel} className="inspector" aria-label="Item details"><div className="inspector-top"><span className="eyebrow">Details</span><button className="icon-button" onClick={onClose} aria-label="Close inspector"><Icon name="close"/></button></div><div className="inspector-title"><Badge kind={kindLabel(entity)}>{kindLabel(entity)}</Badge>{!!entity.archived&&<Badge>Archived</Badge>}<h2>{entity.kind==='shot'?displayTitle(shotTitle(entity)):displayTitle(entity.title)}</h2>{entity.kind==='shot'&&<span className="shot-code">Shot {String(entity.fields.number||String(entity.position+1).padStart(2,'0'))}</span>}<details className="technical-meta"><summary>Technical details</summary><small>Internal ID {id} · saved version {entity.revision}</small></details><button className="full-button" onClick={()=>action(entity.kind+'.update',commandDefaults(entity))}><Icon name="edit"/>Edit {kindLabel(entity).toLowerCase()} details</button></div>
 <div className="tabs" role="tablist" aria-label="Item details sections">{['details','references','context'].filter(t=>t!=='context'||entity.kind!=='asset').map(t=><button key={t} role="tab" aria-selected={tab===t} onClick={()=>setTab(t)}>{human(t)}</button>)}</div><div className="inspector-body">
 {tab==='details'&&<>{entity.kind==='shot'?<ShotDetails entity={entity} state={state}/>:<><p className="prose">{entity.description||'No description yet.'}</p>{Object.entries(entity.fields).filter(([k,v])=>v!==null&&v!==''&&k!=='type').map(([key,value])=><section className="detail-field" key={key}><h4>{human(key)}</h4><p className="prose">{key==='location_id'?displayTitle(state.entities.find(e=>e.id===value)?.title||String(value)):String(value)}</p></section>)}</>}{entity.tags.length>0&&<section><h4>Tags</h4><div className="tags">{entity.tags.map(t=><span key={t} className="tag">{t}</span>)}</div></section>}{entity.aliases.length>0&&<section><h4>Also known as</h4><p>{entity.aliases.join(', ')}</p></section>}{entity.parent_id&&<button className="text-button" onClick={()=>onSelect(entity.parent_id!)}>Part of: {displayTitle(state.entities.find(n=>n.id===entity.parent_id)?.title||'')} →</button>}
 {links.length>0&&<h4>Connected to</h4>}{links.map(l=><div key={l.id} className="neighbor-row"><button className="text-button" onClick={()=>onSelect(l.source_id===id?l.target_id:l.source_id)}>{l.source_id===id?'→':'←'} {state.entities.find(n=>n.id===(l.source_id===id?l.target_id:l.source_id))?.title?displayTitle(state.entities.find(n=>n.id===(l.source_id===id?l.target_id:l.source_id))!.title):'Connected item'}</button><small>{human(l.relation)}</small><button onClick={()=>action('link.remove',commandDefaults(l))}>Remove…</button></div>)}{entity.kind==='asset'&&<button onClick={()=>action('link.create',{source_id:id})}>Connect to another library item</button>}{['sequence','scene','shot'].includes(entity.kind)&&<button onClick={()=>action('story.move',commandDefaults(entity))}>Move / reorder…</button>}
 <details className="record-actions"><summary>More options</summary><p className="muted">Changes affect this item wherever it appears.</p><button onClick={()=>action('entity.usage',{id})}>See where it’s used</button><button onClick={()=>action(entity.archived?'entity.restore':'entity.archive',commandDefaults(entity))}>{entity.archived?'Restore item':'Archive item…'}</button><button className="danger" onClick={()=>action('entity.delete',commandDefaults(entity))}>Delete item…</button>{entity.kind==='asset'&&<button onClick={()=>action('asset.merge',{source_id:id,revision:entity.revision})}>Combine with another library item…</button>}</details></>}
 {tab==='references'&&<>{entity.kind==='asset'&&<><div className="section-heading"><h3>Reference images</h3><button onClick={()=>action('asset.attach',{asset_id:id})}>Add image</button></div>{members.map(m=>{const image=state.media.find(media=>media.id===m.media_id);return <div className="inspector-image" key={m.id}><a href={originalUrl(state.project.id,m.media_id)} target="_blank" rel="noreferrer"><img src={mediaUrl(state.project.id,m.media_id)} alt={image?.original_name||'Library image'}/></a><strong>{image?.original_name}</strong><small>{image?.width} × {image?.height} · {image?.format?.toUpperCase()}</small><div className="button-row">{m.is_primary?<Badge>Cover image</Badge>:<button onClick={()=>action('asset.primary',commandDefaults(m))}>Set as cover image</button>}<button onClick={()=>action('asset.detach',commandDefaults(m))}>Remove…</button></div></div>;})}{!members.length&&<p className="muted">No images here yet. Import one, then add it to this library item.</p>}</>}
 {assignments.length>0&&<h3>{entity.kind==='asset'?'Used by shots':'References in this shot'}</h3>}{assignments.map(a=>{const other=state.entities.find(n=>n.id===(entity.kind==='asset'?a.shot_id:a.asset_id));return <div className="reference-row" key={a.id}>{a.media_id&&<img src={mediaUrl(state.project.id,a.media_id,160)} alt={`${roleLabel(a.role)} reference`}/>}<div><button className="text-button" onClick={()=>onSelect(other!.id)}>{other?displayTitle(other.title):'Library item'}</button><small>{roleLabel(a.role)} · {a.media_id?'specific image selected':'no specific image selected'}</small><div className="button-row"><button onClick={()=>action('assignment.update',{...commandDefaults(a),asset_id:a.asset_id})}>Edit</button><button onClick={()=>action('assignment.remove',commandDefaults(a))}>Remove…</button></div></div></div>;})}{entity.kind==='shot'&&<><button onClick={()=>action('assignment.create',{shot_id:id})}>Add a reference</button><h3>Storyboard frames</h3>{frames.map(f=><div className="frame-mini" key={f.id}><img src={mediaUrl(state.project.id,f.media_id)} alt={`Storyboard image ${f.version}`}/><span>Image {f.version}</span><Badge kind={f.state}>{statusLabel(f.state)}</Badge></div>)}<button onClick={()=>action('frame.attach',{shot_id:id})}>Add storyboard image</button></>}</>}
 {tab==='context'&&<>{error&&<p role="alert">{error}</p>}{context?<ContextView value={context}/>:<p>Loading story direction…</p>}<button onClick={()=>action('context.put',{owner_id:id})}>Add direction note</button></>}
 </div></aside>;
}
