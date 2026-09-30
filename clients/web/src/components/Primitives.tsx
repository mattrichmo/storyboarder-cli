import React,{useEffect,useRef} from '../react';
import type {ReactNode} from '../react';
import type {Issue,ResolvedContext,ExportResult} from '../types';
import {exportUrl} from '../api';
import {human,sourceLabel,operationLabel,displayTitle} from '../utils';

export function Icon({name,size=18}:{name:string;size?:number}){
 const paths:Record<string,ReactNode>={
  grid:<><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  home:<><path d="m3 10 9-7 9 7v11H3z"/><path d="M9 21v-8h6v8"/></>,
  inbox:<><path d="M4 4h16l2 13v4H2v-4z"/><path d="M2 15h6l2 3h4l2-3h6"/></>,
  library:<><rect x="3" y="3" width="18" height="18" rx="2"/><path d="m4 17 5-6 4 3 3-4 5 7"/><circle cx="8" cy="7" r="1"/></>,
  graph:<><rect x="2" y="8" width="6" height="6" rx="1"/><rect x="16" y="2" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="m8 11 8-6M8 11l8 8"/></>,
  outline:<><path d="M5 4v16M5 7h14M5 13h14M5 19h14"/><circle cx="5" cy="7" r="1"/><circle cx="5" cy="13" r="1"/></>,
  guide:<><path d="M3 4h7l2 2 2-2h7v16h-7l-2 1-2-1H3zM12 6v15"/></>,
  edit:<><path d="m4 16 12-12 4 4L8 20l-5 1zM13 7l4 4"/></>,
  frames:<><rect x="2" y="5" width="14" height="14" rx="1"/><path d="M19 3h3v18h-3M2 15l4-4 4 4 3-2 3 4"/></>,
  export:<><path d="M12 3v12m-5-5 5 5 5-5M3 17v4h18v-4"/></>,
  settings:<><path d="M3 6h18M3 12h18M3 18h18"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/></>,
  automation:<><path d="m9 4-6 8 6 8M15 4l6 8-6 8M14 3l-4 18"/></>,
  plus:<path d="M12 4v16M4 12h16"/>,
  close:<path d="m6 6 12 12M18 6 6 18"/>,
  chevron:<path d="m9 5 7 7-7 7"/>,
  search:<><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,
  check:<path d="m4 12 5 5L20 6"/>,
  arrow:<path d="M3 12h18m-7-7 7 7-7 7"/>,
  refresh:<><path d="M20 8a8 8 0 1 0 1 7M20 3v5h-5"/></>,
  menu:<path d="M3 5h18M3 12h18M3 19h18"/>,
 };
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.grid}</svg>;
}
export function Empty({title,children,action}:{title:string;children?:ReactNode;action?:ReactNode}){return <div className="empty"><span className="empty-mark"><Icon name="outline" size={28}/></span><h3>{title}</h3><p>{children}</p>{action}</div>;}
export function PageHeading({eyebrow,title,description,actions}:{eyebrow:string;title:string;description?:string;actions?:ReactNode}){return <header className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{description&&<p className="lede">{description}</p>}</div>{actions&&<div className="heading-actions">{actions}</div>}</header>;}
export function Badge({kind,children}:{kind?:string;children:ReactNode}){return <span className={`badge ${kind||''}`}>{children}</span>;}
export function ErrorNotice({error,children}:{error:string;children?:ReactNode}){return <div className="notice error" role="alert"><strong>We couldn’t complete that.</strong><p>{error}</p>{children}</div>;}
export function Modal({title,children,onClose,wide=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean}){
 const dialog=useRef<HTMLDivElement|null>(null);const closeRef=useRef(onClose);closeRef.current=onClose;
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;const el=dialog.current;const focusable=()=>Array.from(el?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]')||[]).filter(x=>x.offsetParent!==null);
 (focusable()[0]||el)?.focus();const handler=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();closeRef.current();}if(event.key==='Tab'){const items=focusable();const first=items[0],last=items[items.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}};el?.addEventListener('keydown',handler);return()=>{el?.removeEventListener('keydown',handler);previous?.focus();};},[]);
 return <div className="modal-backdrop" onMouseDown={(e:any)=>{if(e.target===e.currentTarget)onClose();}}><div ref={dialog} className={`modal ${wide?'wide':''}`} role="dialog" aria-modal="true" aria-labelledby="modal-title" tabIndex={-1}><div className="modal-heading"><h2 id="modal-title">{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button></div>{children}</div></div>;
}
export function Validation({issues}:{issues:Issue[]}){if(!issues.length)return <p className="success-line"><Icon name="check"/> All selected images are available.</p>;return <div className="validation"><h3>Production checks <span className="count">{issues.length}</span></h3>{issues.map((i,n)=><div key={`${i.code}-${n}`} className={`check-row ${i.severity}`}><Badge>{human(i.severity)}</Badge><span>{i.message}</span></div>)}</div>;}
export function ContextView({value}:{value:ResolvedContext}){return <div className="context-view"><div className="scope-chain">{value.chain.map((c,i)=><span key={c.id}>{i>0&&' / '}{displayTitle(c.title)}</span>)}</div>{Object.entries(value.scalars).map(([key,entry])=><div className="context-value" key={key}><span className="eyebrow">{human(key)}</span><strong>{entry.label||entry.value}</strong><small>{sourceLabel(entry.source.kind)} · {displayTitle(entry.source.title)}</small></div>)}{Object.entries(value.blocks).map(([key,entries])=><section className="direction-block" key={key}><h4>{human(key)}</h4>{entries.map((e,i)=><div key={e.block_id||`${e.source.id}-${i}`}><p className="prose">{e.text}</p><small>{sourceLabel(e.source.kind)} · {displayTitle(e.source.title)}</small></div>)}</section>)}{!Object.keys(value.blocks).length&&!Object.keys(value.scalars).length&&<p className="muted">No direction has been added yet. Add a note here or at a higher story level.</p>}{value.history.filter(h=>h.operation!=='append').map((h,i)=><p className="context-rule" key={`${h.key}-${i}`}><Badge>{operationLabel(h.operation)}</Badge> {human(h.key)} · {displayTitle(h.source.title)}{h.removed_sources.length?` · ${h.removed_sources.length} earlier ${h.removed_sources.length===1?'note was changed':'notes were changed'}`:''}</p>)}</div>;}
export function ExportLinks({project,result}:{project:string;result:ExportResult}){return <div className="export-result"><p className="success-line"><Icon name="check"/> Export saved in your project folder.</p><code>{result.path}</code><div className="button-row">{result.archive&&<a className="button primary" href={exportUrl(project,result.archive,true)}>Download project package (.zip) <Icon name="export"/></a>}{result.view&&<a className="button" href={exportUrl(project,result.view)} target="_blank" rel="noreferrer">Open board <Icon name="arrow"/></a>}</div><details><summary>Individual files</summary><div className="file-links">{result.files?.filter(p=>!p.endsWith('.zip')).map(path=><a key={path} href={exportUrl(project,path,true)}>{path.split('/').pop()}</a>)}</div></details>{result.validation&&<Validation issues={result.validation}/>}</div>;}
