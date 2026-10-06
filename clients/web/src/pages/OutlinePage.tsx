import React, {useState} from '../react';
import type {Entity} from '../types';
import {activeEntities, commandDefaults, human, displayTitle} from '../utils';
import {PageHeading, Empty, Icon} from '../components/Primitives';
import type {PageProps} from './Pages';

function shotTitle(entity:Entity){
 const number=String(entity.fields.number||'');
 return number&&entity.title.startsWith(number)
  ? entity.title.slice(number.length).replace(/^\s*[·—:-]\s*/,'')||entity.title
  : entity.title;
}

function outlineTitle(entity:Entity){
 if(entity.kind==='shot')return shotTitle(entity);
 return displayTitle(entity.title.replace(/^\d{2}\s*[·—:-]\s*/,'')||entity.title);
}

function shotAction(entity:Entity){
 const action=String(entity.fields.action||entity.description||'No action added yet.');
 const title=shotTitle(entity);
 return action.endsWith(` — ${title}`)?action.slice(0,-title.length-3):action;
}

function repeatsShotSummaries(entity:Entity,shots:Entity[]){
 const lines=String(entity.fields.summary||'').split(/\n+/).map(line=>line.trim()).filter(Boolean);
 return shots.length>0&&lines.length===shots.length&&lines.every((line,index)=>{
  const title=shotTitle(shots[index]);
  return line.toLowerCase().startsWith(`${title.toLowerCase()}:`);
 });
}

function framingParts(entity:Entity){
 const framing=String(entity.fields.framing||'');
 const split=framing.indexOf(' — ');
 return split<0?{label:framing,detail:''}:{label:framing.slice(0,split),detail:framing.slice(split+3)};
}

export function OutlinePage(p:PageProps){
 const [query,setQuery]=useState('');
 const [collapsed,setCollapsed]=useState<string[]>([]);
 const records=activeEntities(p.state).filter(e=>['sequence','scene','shot'].includes(e.kind));
 const byId=new Map(records.map(e=>[e.id,e]));
 const childrenByParent=new Map<string,Entity[]>();
 for(const record of records){
  if(!record.parent_id)continue;
  const siblings=childrenByParent.get(record.parent_id)||[];
  siblings.push(record);
  childrenByParent.set(record.parent_id,siblings);
 }
 for(const siblings of childrenByParent.values())siblings.sort((a,b)=>a.position-b.position);

 const visibleIds=new Set(records.filter(e=>[
  e.title,e.fields.action||'',e.fields.summary||'',e.fields.number||'',e.fields.framing||'',
 ].join(' ').toLowerCase().includes(query.toLowerCase())).map(e=>e.id));
 for(const id of [...visibleIds]){
  let current=byId.get(id);
  while(current?.parent_id){
   visibleIds.add(current.parent_id);
   current=byId.get(current.parent_id);
  }
 }
 const children=(id:string)=>(childrenByParent.get(id)||[]).filter(e=>visibleIds.has(e.id));
 const sequenceShotCounts=new Map<string,number>();
 for(const shot of records.filter(e=>e.kind==='shot')){
  const scene=byId.get(shot.parent_id||'');
  if(scene?.parent_id)sequenceShotCounts.set(scene.parent_id,(sequenceShotCounts.get(scene.parent_id)||0)+1);
 }
 const totals={
  sequences:records.filter(e=>e.kind==='sequence').length,
  scenes:records.filter(e=>e.kind==='scene').length,
  shots:records.filter(e=>e.kind==='shot').length,
 };

 const render=(entity:Entity):any=>{
  const nested=children(entity.id);
  const isCollapsed=collapsed.includes(entity.id);
  const sceneCount=nested.filter(e=>e.kind==='scene').length;
  const shotCount=entity.kind==='sequence'
   ? sequenceShotCounts.get(entity.id)||0
   : nested.filter(e=>e.kind==='shot').length;
  const sceneShots=(childrenByParent.get(entity.id)||[]).filter(child=>child.kind==='shot');
  const rawSummary=entity.kind==='shot'
   ? shotAction(entity)
   : entity.kind==='scene'
    ? String(entity.fields.summary||entity.description||'')
    : String(entity.fields.arc||entity.description||'Add a short story direction.');
  const summary=entity.kind==='scene'&&(repeatsShotSummaries(entity,sceneShots)||/^Grouped from source scene\b/.test(rawSummary))?'':rawSummary;
  const frame=entity.kind==='shot'?framingParts(entity):null;
  const number=String(entity.fields.number||String(entity.position+1).padStart(2,'0'));
  const title=outlineTitle(entity);

  return <div key={entity.id} className={`story-node ${entity.kind}`}>
   <div className={`story-row ${p.selected===entity.id?'is-selected':''}`}>
    {entity.kind==='shot'
     ? <span className="shot-order">{number}</span>
     : <button className="collapse-button" aria-label={`${isCollapsed?'Expand':'Collapse'} ${entity.title}`} aria-expanded={!isCollapsed} onClick={()=>setCollapsed(value=>isCollapsed?value.filter(id=>id!==entity.id):[...value,entity.id])}>{isCollapsed?'+':'−'}</button>}
    <div className="story-main">
     <div className="story-heading-line">
      <span className="eyebrow">{human(entity.kind)} · {String(entity.position+1).padStart(2,'0')}</span>
      {entity.kind==='sequence'&&<span className="story-count">{sceneCount} scenes · {shotCount} shots</span>}
      {entity.kind==='scene'&&<span className="story-count">{shotCount} {shotCount===1?'shot':'shots'}</span>}
     </div>
     <button className="title-button" onClick={()=>p.select(entity.id)}>{title}</button>
     {summary&&<p>{summary}</p>}
     {frame&&<div className="shot-meta-strip">
      {frame.label&&<span className="shot-meta-kind">{frame.label}</span>}
      {entity.fields.duration!=null&&<span>{Number(entity.fields.duration)} sec</span>}
      {entity.fields.time&&<span>{String(entity.fields.time)}</span>}
     </div>}
    </div>
    <div className="row-actions">
     {entity.kind!=='shot'&&<button onClick={()=>p.action(entity.kind==='sequence'?'scene.create':'shot.create',{parent_id:entity.id})}><Icon name="plus" size={14}/>{entity.kind==='sequence'?'Scene':'Shot'}</button>}
     <button onClick={()=>p.action(entity.kind+'.update',commandDefaults(entity))}>Edit</button>
     <button onClick={()=>p.action('story.move',commandDefaults(entity))}>Move / reorder</button>
    </div>
   </div>
   {!isCollapsed&&nested.length>0&&<div className={`story-children children-${entity.kind} ${entity.kind==='scene'&&shotCount===1?'single-shot':''}`}>
    {nested.map(render)}
   </div>}
  </div>;
 };

 const sequences=children(p.state.project.id).filter(e=>e.kind==='sequence');
 return <>
  <PageHeading eyebrow="Story outline" title="Build the story, scene by scene." description="Organize scenes and shots into sequences, then rearrange them as the story changes." actions={<button className="primary" onClick={()=>p.action('sequence.create')}><Icon name="plus"/>New sequence</button>}/>
  <div className="outline-toolbar">
   <div className="outline-totals" aria-label="Story outline items">
    <span><strong>{totals.sequences}</strong> sequences</span><i/>
    <span><strong>{totals.scenes}</strong> scenes</span><i/>
    <span><strong>{totals.shots}</strong> shots</span>
   </div>
   <div className="list-toolbar">
    <label className="search"><Icon name="search"/><input aria-label="Search story outline" value={query} onChange={(e:any)=>setQuery(e.target.value)} placeholder="Find a scene or shot…"/></label>
    <button onClick={()=>setCollapsed([])}>Expand all</button>
    <button onClick={()=>p.go('canvas')}>Open story canvas</button>
   </div>
  </div>
  <div className="story-outline">{sequences.map(render)}</div>
  {!records.length&&<Empty title="Start with a sequence" action={<button onClick={()=>p.action('sequence.create')}>Create a sequence</button>}>Add scenes and shots to shape the story. Reorder them here whenever the story changes.</Empty>}
 </>;
}
