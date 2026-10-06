import React,{useEffect,useRef,useState} from '../react';
import type {Entity,State} from '../types';
import {api,projectPath,runCommand} from '../api';

type SourceScope='direct-element'|'scene-context';
type SourcePin={edge_id:string;source_scope:SourceScope};
type ScriptIntent={id:string;source_edge_id:string;source_scope:SourceScope;purpose:string;communication:string;basis:'direct'|'interpreted'|'unknown'};
type Requirement={id:string;priority:'must'|'prefer'|'unknown';basis:'direct'|'interpreted'|'unknown';source_edge_ids:string[];statement?:string|null;topic?:string|null};
type Continuity={id:string;related_shot_ids:string[];statement:string};
type ContractBody={schema:'storyboarder.observation-contract/v1';source_pins:SourcePin[];script_intents:ScriptIntent[];requirements:Requirement[];references:string[];continuity:Continuity[];notes:string};
type SourceRow={edge_id:string;target_id:string;node_id:string;version_id:string;logical_id:string;node_type:string;title:string;document_id:string;version_label:string;current_version_id:string;content_sha256?:string;stale:boolean;inherited:boolean};
type ContractVersion={id:string;number:number;parent_version_id:string|null;schema_version:number;content_sha256:string;basis_sha256:string;operation:string;created_at:string};
type Validation={status:string;revision?:number;version_id?:string;findings:Array<Record<string,any>>;requirements:Array<Record<string,any>>;source_pins:Array<Record<string,any>>;references:Array<Record<string,any>>;basis_current:boolean};
type ContractRecord={id:string;shot_id:string;revision:number;current_version_id:string;selected_version_id:string;version:ContractVersion;contract:ContractBody;source_pins:Array<Record<string,any>>;history:ContractVersion[];validation:Validation};
type ContractListItem={id:string;shot_id:string;current_version_id:string;revision:number;shot_title:string;version_number:number};
type SourceDetails={documentTitle?:string;versionNumber?:number;versionLabel?:string;nodeTitle?:string;nodeType?:string;currentVersionId?:string;contentSha256?:string;error?:string};
type RebaseReview={revision:number;expected_basis_sha256:string;saved_basis_sha256:string;current_basis_sha256:string;basis_changed:boolean;changes:Array<{path:string;saved_value:unknown;current_value:unknown}>;changes_truncated:boolean};
type ContractDiff={before_version_id:string;after_version_id:string;changes:Array<{path:string;before:unknown;after:unknown}>};
type DraftCache={body:ContractBody;baseRecord:ContractRecord|null;latestRecord:ContractRecord|null;shotRevision:number;generation:number;conflicted:boolean;validation?:Validation|null;recoveryBaseRecord?:ContractRecord|null};
type DraftEvent={entry?:DraftCache;pending:boolean};
type RetargetPreview={oldEdgeId:string;newEdgeId:string};

const draftCache=new Map<string,DraftCache>();
const pendingDrafts=new Set<string>();
const draftListeners=new Map<string,Set<(event:DraftEvent,origin:object)=>void>>();
const dirtyDraftOwners=new Set<string>();
const acceptedRecordEpochs=new Map<string,number>();
function acceptedRecordEpoch(key:string){return acceptedRecordEpochs.get(key)||0;}
function noteAcceptedRecordWrite(key:string){acceptedRecordEpochs.set(key,acceptedRecordEpoch(key)+1);}
function guardUnsavedUnload(event:BeforeUnloadEvent){if(!dirtyDraftOwners.size&&!pendingDrafts.size)return;event.preventDefault();event.returnValue='';}
function updateUnloadGuard(){if(typeof window==='undefined')return;if(dirtyDraftOwners.size||pendingDrafts.size)window.addEventListener('beforeunload',guardUnsavedUnload);else window.removeEventListener('beforeunload',guardUnsavedUnload);}
function setDraftDirty(key:string,dirty:boolean){if(dirty)dirtyDraftOwners.add(key);else dirtyDraftOwners.delete(key);updateUnloadGuard();}
function notifyDraft(key:string,event:DraftEvent,origin:object){for(const listener of draftListeners.get(key)||[])listener(event,origin);}
function storeDraft(key:string,entry:DraftCache,origin:object){const previous=draftCache.get(key);const accepted={...entry,validation:Object.prototype.hasOwnProperty.call(entry,'validation')?entry.validation??null:previous?.validation??null,recoveryBaseRecord:Object.prototype.hasOwnProperty.call(entry,'recoveryBaseRecord')?entry.recoveryBaseRecord??null:previous?.recoveryBaseRecord??null};draftCache.set(key,accepted);setDraftDirty(key,JSON.stringify(accepted.baseRecord?.contract||emptyBody())!==JSON.stringify(accepted.body));notifyDraft(key,{entry:accepted,pending:pendingDrafts.has(key)},origin);}
function setDraftPending(key:string,pending:boolean,origin:object){if(pending)pendingDrafts.add(key);else pendingDrafts.delete(key);updateUnloadGuard();notifyDraft(key,{pending},origin);}

const emptyBody=():ContractBody=>({schema:'storyboarder.observation-contract/v1',source_pins:[],script_intents:[],requirements:[],references:[],continuity:[],notes:''});
const copy=<T,>(value:T):T=>JSON.parse(JSON.stringify(value));
async function showAndValidateRecord(projectId:string,initial:ContractRecord,active:()=>boolean=()=>true){
 let record=initial;
 for(let attempt=0;attempt<2;attempt++){
  if(!active())return {record,validation:null as Validation|null,unstable:false,stopped:true};
  const validation=await runCommand<Validation>(projectId,'observation.validate',{contract_id:record.id,version_id:record.selected_version_id});
  if(!active())return {record,validation:null as Validation|null,unstable:false,stopped:true};
  const tupleMatches=validation.revision===record.revision&&validation.version_id===record.selected_version_id;
  if(tupleMatches)return {record,validation,unstable:false,stopped:false};
  if(attempt===1)return {record,validation:null as Validation|null,unstable:true,stopped:false};
  record=await runCommand<ContractRecord>(projectId,'observation.show',{contract_id:record.id});
  if(!active())return {record,validation:null as Validation|null,unstable:false,stopped:true};
 }
 return {record,validation:null as Validation|null,unstable:true,stopped:false};
}
function recordValidation(record:ContractRecord):Validation{return {...record.validation,revision:record.revision,version_id:record.selected_version_id};}
function listItem(record:ContractRecord,shotTitle:string):ContractListItem{return {id:record.id,shot_id:record.shot_id,current_version_id:record.current_version_id,revision:record.revision,shot_title:shotTitle,version_number:record.version.number};}
function stableId(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;}
function sourceScope(row:SourceRow):SourceScope{return row.inherited?'scene-context':'direct-element';}
function sourceName(row:SourceRow,details?:SourceDetails){const kind=details?.nodeType||row.node_type;const title=details?.nodeTitle||row.title;return `${row.inherited?'Scene context':'Direct shot link'} · ${kind==='scene'?'Scene node':kind} · ${title||'Untitled source'}`;}
function readablePath(path:string){return path.replace(/^\//,'').split('/').map(part=>part.replace(/_id$/,' ID').replace(/_/g,' ')).join(' · ');}
function displayValue(value:unknown){if(value&&typeof value==='object')return JSON.stringify(value);if(value===undefined)return 'Not present';return String(value);}
type ContractFieldChange={path:string;before:unknown;after:unknown};
function contractBodyChanges(before:unknown,after:unknown):ContractFieldChange[]{
 const changes:ContractFieldChange[]=[];
 const stableArrayKey=(value:unknown):string|null=>{if(!value||typeof value!=='object'||Array.isArray(value))return null;const row=value as Record<string,unknown>;const key=typeof row.id==='string'?row.id:typeof row.edge_id==='string'?row.edge_id:null;return key?`${typeof row.id==='string'?'id':'edge_id'}=${key}`:null;};
 const visit=(left:unknown,right:unknown,path:string)=>{
  if(Object.is(left,right))return;
  if(Array.isArray(left)&&Array.isArray(right)){
   const leftKeys=left.map(stableArrayKey),rightKeys=right.map(stableArrayKey);
   if(leftKeys.every(Boolean)&&rightKeys.every(Boolean)){
    const leftByKey=new Map(left.map((value,index)=>[leftKeys[index]!,value]));const rightByKey=new Map(right.map((value,index)=>[rightKeys[index]!,value]));
    for(const key of Array.from(new Set([...leftByKey.keys(),...rightByKey.keys()])).sort())visit(leftByKey.get(key),rightByKey.get(key),`${path}/${key}`);
   }else{
    for(let index=0;index<Math.max(left.length,right.length);index++)visit(left[index],right[index],`${path}/${index}`);
   }
   return;
  }
  if(left&&right&&typeof left==='object'&&typeof right==='object'&&!Array.isArray(left)&&!Array.isArray(right)){
   const leftRow=left as Record<string,unknown>,rightRow=right as Record<string,unknown>;
   for(const key of Array.from(new Set([...Object.keys(leftRow),...Object.keys(rightRow)])).sort())visit(leftRow[key],rightRow[key],`${path}/${key}`);
   return;
  }
  changes.push({path:path||'/contract',before:left,after:right});
 };
 visit(before,after,'/contract');
 return changes;
}

export function ShotIntent({projectId,shot}:{projectId:string;shot:Entity}){
 const ownerKey=`${projectId}:${shot.id}`;const instance=useRef<object>({});
 const [sources,setSources]=useState<SourceRow[]>([]),[sourceDetails,setSourceDetails]=useState<Record<string,SourceDetails>>({});
 const [items,setItems]=useState<ContractListItem[]>([]),[selectedContract,setSelectedContract]=useState('');
 const [saved,setSaved]=useState<ContractRecord|null>(null),[latest,setLatest]=useState<ContractRecord|null>(null),[draft,setDraft]=useState<ContractBody>(emptyBody);
 const [validation,setValidation]=useState<Validation|null>(null),[remoteDiff,setRemoteDiff]=useState<ContractDiff|null>(null),[historyDiff,setHistoryDiff]=useState<ContractDiff|null>(null),[recoveryBaseRecord,setRecoveryBaseRecord]=useState<ContractRecord|null>(null);
 const [review,setReview]=useState<RebaseReview|null>(null),[reviewGeneration,setReviewGeneration]=useState(-1),[retargetPreview,setRetargetPreview]=useState<RetargetPreview|null>(null);
 const [loading,setLoading]=useState(true),[refreshing,setRefreshing]=useState(false),[busy,setBusy]=useState(false),[ownerPending,setOwnerPending]=useState(pendingDrafts.has(ownerKey)),[error,setError]=useState(''),[sourceError,setSourceError]=useState(''),[notice,setNotice]=useState(''),[ready,setReady]=useState(false),[conflicted,setConflicted]=useState(false),[rebaseNeedsReview,setRebaseNeedsReview]=useState(false);
 const editGeneration=useRef(0),loadSequence=useRef(0),initialShotRevision=useRef(shot.revision),[latestShotRevision,setLatestShotRevision]=useState(shot.revision);
 const dirty=!!saved?JSON.stringify(saved.contract)!==JSON.stringify(draft):JSON.stringify(emptyBody())!==JSON.stringify(draft);

 async function hydrateSources(rows:SourceRow[],active:()=>boolean){
  if(active())setSources(rows);
  const documents=Array.from(new Set(rows.map(row=>row.document_id)));
  const documentDetails:Record<string,{document:any;versions:any[];failed:boolean}>={};
  await Promise.all(documents.map(async documentId=>{
   const [documentResult,versionsResult]=await Promise.allSettled([
    runCommand<any>(projectId,'document.show',{id:documentId}),
    runCommand<any>(projectId,'document.versions',{document_id:documentId,limit:100,offset:0}),
   ]);
   documentDetails[documentId]={document:documentResult.status==='fulfilled'?documentResult.value:null,versions:versionsResult.status==='fulfilled'?versionsResult.value?.items||[]:[],failed:documentResult.status==='rejected'||versionsResult.status==='rejected'};
  }));
  const next:Record<string,SourceDetails>={};
  await Promise.all(rows.map(async row=>{
   const nodeResult=await Promise.allSettled([runCommand<any>(projectId,'document.node',{id:row.node_id})]);
   const node=nodeResult[0].status==='fulfilled'?nodeResult[0].value:null;
   const parent=documentDetails[row.document_id];const version=parent?.versions.find((entry:any)=>entry.id===row.version_id);
    next[row.edge_id]={documentTitle:parent?.document?.title,versionNumber:version?.number,versionLabel:version?.label||row.version_label,nodeTitle:node?.title||row.title,nodeType:node?.node_type||row.node_type,currentVersionId:parent?.document?.current_version_id||row.current_version_id,contentSha256:node?.content_sha256||row.content_sha256,
    error:parent?.failed||nodeResult[0].status==='rejected'?'Some exact source details could not be loaded.':''};
  }));
  if(active())setSourceDetails(old=>({...old,...next}));
  if(documents.length&&active())setSourceError('');
 }

 async function initialLoad(){
  const sequence=++loadSequence.current,acceptedEpoch=acceptedRecordEpoch(ownerKey);const stillCurrent=()=>loadSequence.current===sequence&&acceptedRecordEpoch(ownerKey)===acceptedEpoch;const stopStaleLoad=()=>{if(loadSequence.current===sequence){setReady(true);setLoading(false);}};const cachedAtStart=draftCache.get(ownerKey);editGeneration.current=cachedAtStart?.generation||0;initialShotRevision.current=cachedAtStart?.shotRevision??shot.revision;setLatestShotRevision(shot.revision);setOwnerPending(pendingDrafts.has(ownerKey));setRecoveryBaseRecord(cachedAtStart?.recoveryBaseRecord||null);
  setLoading(true);setReady(false);setError('');setSourceError('');setNotice('');setSaved(null);setLatest(null);setValidation(null);setDraft(copy(cachedAtStart?.body||emptyBody()));setItems([]);setSelectedContract('');setReview(null);setRemoteDiff(null);setHistoryDiff(null);setConflicted(false);setRebaseNeedsReview(false);
  const [sourceResult,listResult]=await Promise.allSettled([
   runCommand<{items:SourceRow[]}>(projectId,'shot.sources',{id:shot.id}),
   runCommand<{items:ContractListItem[]}>(projectId,'observation.list',{shot_id:shot.id,limit:100,offset:0}),
  ]);
  if(!stillCurrent()){stopStaleLoad();return;}
  if(sourceResult.status==='fulfilled')void hydrateSources(sourceResult.value.items||[],()=>loadSequence.current===sequence);
  else setSourceError(messageOf(sourceResult.reason));
  if(listResult.status==='rejected'){setError(messageOf(listResult.reason));setLoading(false);return;}
  const rows=listResult.value.items||[];setItems(rows);setReady(true);
  const cached=draftCache.get(ownerKey);const first=rows.find(item=>item.id===cached?.baseRecord?.id)||rows[0];
  if(!first){const cached=draftCache.get(ownerKey);setSaved(null);setLatest(null);setSelectedContract('');setDraft(copy(cached?.body||emptyBody()));setValidation(null);setConflicted(false);setRecoveryBaseRecord(null);setLoading(false);if(cached)storeDraft(ownerKey,{...cached,body:copy(cached.body),baseRecord:null,latestRecord:null,validation:null,recoveryBaseRecord:null},instance.current);return;}
  setSelectedContract(first.id);
  try{
   const shown=await runCommand<ContractRecord>(projectId,'observation.show',{contract_id:first.id});
   if(!stillCurrent())return;
   const read=await showAndValidateRecord(projectId,shown,stillCurrent);
   if(read.stopped||!stillCurrent())return;
   const record=read.record,checked=read.validation;
   const acceptedItem=listItem(record,shot.title);setItems(old=>old.some(item=>item.id===record.id)?old.map(item=>item.id===record.id?acceptedItem:item):[acceptedItem,...old]);setSelectedContract(record.id);
   const cached=draftCache.get(ownerKey);
   if(cached){
    const base=cached.baseRecord;const pendingOwnCreate=!cached.baseRecord&&pendingDrafts.has(ownerKey);const hasExternal=(!cached.baseRecord&&!pendingOwnCreate)||!!cached.baseRecord&&(cached.baseRecord.revision!==record.revision||cached.baseRecord.current_version_id!==record.current_version_id);
    const conflict=hasExternal||cached.conflicted||read.unstable;
    setSaved(base);setLatest(record);setDraft(copy(cached.body));setValidation(checked);setConflicted(conflict);
    let difference:ContractDiff|null=null;
    if(cached.baseRecord&&hasExternal){try{difference=await runCommand<ContractDiff>(projectId,'observation.diff',{contract_id:record.id,before_version_id:cached.baseRecord.current_version_id,after_version_id:record.current_version_id});}catch(reason){if(stillCurrent())setError(messageOf(reason));}}
    if(!stillCurrent())return;
    setRemoteDiff(difference);storeDraft(ownerKey,{...cached,baseRecord:base,latestRecord:record,conflicted:conflict,validation:checked},instance.current);
    if(read.unstable)setNotice('The saved contract changed while validation was running. No mismatched validation is shown; your local draft and exact pins are retained. Refresh status before saving.');
   }else{setSaved(record);setLatest(record);setDraft(copy(record.contract));setValidation(checked);setConflicted(read.unstable);storeDraft(ownerKey,{body:copy(record.contract),baseRecord:record,latestRecord:record,shotRevision:initialShotRevision.current,generation:editGeneration.current,conflicted:read.unstable,validation:checked},instance.current);if(read.unstable)setNotice('The saved contract changed while validation was running. No mismatched validation is shown. Refresh status before saving.');}
  }catch(reason){if(stillCurrent())setError(messageOf(reason));}
  finally{if(loadSequence.current===sequence)setLoading(false);}
 }

 useEffect(()=>{
  let listeners=draftListeners.get(ownerKey);if(!listeners){listeners=new Set();draftListeners.set(ownerKey,listeners);}
  const listener=(event:DraftEvent,origin:object)=>{if(origin===instance.current)return;setOwnerPending(event.pending);if(event.entry){editGeneration.current=event.entry.generation;initialShotRevision.current=event.entry.shotRevision;setDraft(copy(event.entry.body));setSaved(event.entry.baseRecord);setLatest(event.entry.latestRecord);setConflicted(event.entry.conflicted);setValidation(event.entry.validation||null);setRecoveryBaseRecord(event.entry.recoveryBaseRecord||null);const record=event.entry.latestRecord||event.entry.baseRecord;if(record){const item=listItem(record,shot.title);setItems(old=>old.some(row=>row.id===record.id)?old.map(row=>row.id===record.id?item:row):[item,...old]);setSelectedContract(record.id);}}};
  listeners.add(listener);setOwnerPending(pendingDrafts.has(ownerKey));void initialLoad();
  return()=>{listeners?.delete(listener);if(!listeners?.size)draftListeners.delete(ownerKey);loadSequence.current+=1;};
 },[projectId,shot.id]);

 function changeDraft(next:ContractBody){editGeneration.current+=1;setDraft(next);storeDraft(ownerKey,{body:copy(next),baseRecord:saved,latestRecord:latest,shotRevision:initialShotRevision.current,generation:editGeneration.current,conflicted,validation},instance.current);setReview(null);setReviewGeneration(-1);setHistoryDiff(null);setNotice('');}
 function patchDraft(update:(previous:ContractBody)=>ContractBody){changeDraft(update(draft));}
 function patchIntent(id:string,update:(value:ScriptIntent)=>ScriptIntent){patchDraft(body=>({...body,script_intents:body.script_intents.map(item=>item.id===id?update(item):item)}));}
 function patchRequirement(id:string,update:(value:Requirement)=>Requirement){patchDraft(body=>({...body,requirements:body.requirements.map(item=>item.id===id?update(item):item)}));}
 function addIntent(){if(!draft.source_pins.length){setNotice('Select an exact linked screenplay source before adding its purpose.');return;}const pin=draft.source_pins[0];patchDraft(body=>({...body,script_intents:[...body.script_intents,{id:stableId(),source_edge_id:pin.edge_id,source_scope:pin.source_scope,purpose:'',communication:'',basis:'unknown'}]}));}
 function addRequirement(){patchDraft(body=>({...body,requirements:[...body.requirements,{id:stableId(),priority:'must',basis:'unknown',source_edge_ids:draft.source_pins.slice(0,1).map(pin=>pin.edge_id),statement:'',topic:null}]}));}
 function togglePin(row:SourceRow,selected:boolean){
  const edge=row.edge_id;
  if(!selected){const used=draft.script_intents.some(item=>item.source_edge_id===edge)||draft.requirements.some(item=>item.source_edge_ids.includes(edge));if(used){setNotice('Remove or retarget the purpose and requirements that use this source before unpinning it.');return;}}
  patchDraft(body=>({...body,source_pins:selected?[...body.source_pins,{edge_id:edge,source_scope:sourceScope(row)}]:body.source_pins.filter(pin=>pin.edge_id!==edge)}));
 }
 function previewRetarget(oldEdgeId:string,newEdgeId:string){const target=sourceByEdge.get(newEdgeId);if(!target||target.stale||oldEdgeId===newEdgeId)return;setRetargetPreview({oldEdgeId,newEdgeId});}
 function confirmRetarget(){if(!retargetPreview)return;const {oldEdgeId,newEdgeId}=retargetPreview;const target=sourceByEdge.get(newEdgeId);if(!target||target.stale)return;const scope=sourceScope(target);patchDraft(body=>({...body,source_pins:body.source_pins.some(pin=>pin.edge_id===newEdgeId)?body.source_pins.filter(pin=>pin.edge_id!==oldEdgeId):body.source_pins.map(pin=>pin.edge_id===oldEdgeId?{edge_id:newEdgeId,source_scope:scope}:pin),script_intents:body.script_intents.map(item=>item.source_edge_id===oldEdgeId?{...item,source_edge_id:newEdgeId,source_scope:scope}:item),requirements:body.requirements.map(item=>({...item,source_edge_ids:Array.from(new Set(item.source_edge_ids.map(edge=>edge===oldEdgeId?newEdgeId:edge)))}))}));setRetargetPreview(null);}

 async function refreshStatus(fromConflict=false){
  const sequence=++loadSequence.current;
  setRefreshing(true);setError('');setNotice(fromConflict?'The write conflicted. Refreshing the saved record while keeping your draft…':'Refreshing saved status and exact linked sources…');
  try{
   const [sourceRows,list,projectState]=await Promise.all([
    runCommand<{items:SourceRow[]}>(projectId,'shot.sources',{id:shot.id}),
    runCommand<{items:ContractListItem[]}>(projectId,'observation.list',{shot_id:shot.id,limit:100,offset:0}),
    api<State>(projectPath(projectId,'/state')),
   ]);
   const rows=sourceRows.items||[];if(loadSequence.current!==sequence)return;setSources(rows);void hydrateSources(rows,()=>loadSequence.current===sequence);setItems(list.items||[]);
   const refreshedShot=projectState.entities.find(entity=>entity.id===shot.id);const observedShotRevision=refreshedShot?.revision??shot.revision;setLatestShotRevision(observedShotRevision);
   const candidate=(list.items||[]).find(item=>item.id===selectedContract)||(list.items||[])[0];
   if(!candidate){if(loadSequence.current!==sequence)return;const cached=draftCache.get(ownerKey);const hasConflict=!!saved||observedShotRevision!==initialShotRevision.current;setLatest(null);setValidation(null);setRemoteDiff(null);setConflicted(hasConflict);setRecoveryBaseRecord(null);storeDraft(ownerKey,{body:copy(cached?.body||draft),baseRecord:cached?cached.baseRecord:saved,latestRecord:null,shotRevision:cached?.shotRevision??initialShotRevision.current,generation:cached?.generation??editGeneration.current,conflicted:hasConflict,validation:null,recoveryBaseRecord:null},instance.current);setNotice(saved?'The saved contract is no longer listed. Your draft and exact pins remain here.':'Linked sources refreshed. Your selected exact pins were left unchanged.');return;}
   const shown=await runCommand<ContractRecord>(projectId,'observation.show',{contract_id:candidate.id});
   const read=await showAndValidateRecord(projectId,shown,()=>loadSequence.current===sequence);
   if(read.stopped||loadSequence.current!==sequence)return;
   const record=read.record,checked=read.validation;
   const acceptedItem=listItem(record,shot.title);setItems(old=>old.some(item=>item.id===record.id)?old.map(item=>item.id===record.id?acceptedItem:item):[acceptedItem,...old]);setLatest(record);setValidation(checked);setSelectedContract(record.id);
   const hasExternalChange=read.unstable||!saved||saved.revision!==record.revision||saved.current_version_id!==record.current_version_id;
   setConflicted(hasExternalChange);
   if(read.unstable){setRemoteDiff(null);setNotice('The latest saved header could not be matched to a validation result after one retry. Your draft and exact source pins are retained; validation is not checked. Refresh status to try again.');}
   else if(hasExternalChange){
    if(saved){const difference=await runCommand<ContractDiff>(projectId,'observation.diff',{contract_id:candidate.id,before_version_id:saved.current_version_id,after_version_id:record.current_version_id});if(loadSequence.current!==sequence)return;setRemoteDiff(difference);}
    setNotice(saved?'A newer saved revision is available. Your editor draft and exact source pins were kept unchanged. Compare it or explicitly load it.':'A contract now exists for this shot. Your create draft and exact pins are retained; compare the saved record before choosing how to continue.');
   }else{setRemoteDiff(null);setNotice(fromConflict?'The current saved revision is loaded for comparison. Your draft is unchanged.':'Status refreshed. Your draft and exact source pins were unchanged.');}
   const cached=draftCache.get(ownerKey);storeDraft(ownerKey,{body:copy(cached?.body||draft),baseRecord:cached?cached.baseRecord:saved,latestRecord:record,shotRevision:cached?.shotRevision??initialShotRevision.current,generation:cached?.generation??editGeneration.current,conflicted:hasExternalChange,validation:checked},instance.current);
  }catch(reason){setError(messageOf(reason));}
  finally{setRefreshing(false);}
 }

 function loadLatestIntoDraft(){
  if(!latest)return;
  setSaved(latest);setDraft(copy(latest.contract));setValidation(validation);setConflicted(false);setRemoteDiff(null);setReview(null);setRecoveryBaseRecord(null);editGeneration.current+=1;storeDraft(ownerKey,{body:copy(latest.contract),baseRecord:latest,latestRecord:latest,shotRevision:initialShotRevision.current,generation:editGeneration.current,conflicted:false,validation,recoveryBaseRecord:null},instance.current);setNotice(`Draft replaced with saved contract revision ${latest.revision}.`);setError('');
 }

 function keepDraftOnExistingContract(){
  if(!latest||saved||latest.shot_id!==shot.id||!validation||validation.revision!==latest.revision||validation.version_id!==latest.selected_version_id||busy||ownerPending)return;
  const record=latest;setSelectedContract(record.id);setSaved(record);setLatest(record);setValidation(validation);setConflicted(false);setRemoteDiff(null);setReview(null);setRecoveryBaseRecord(record);
  storeDraft(ownerKey,{body:copy(draft),baseRecord:record,latestRecord:record,shotRevision:initialShotRevision.current,generation:editGeneration.current,conflicted:false,validation,recoveryBaseRecord:record},instance.current);
  setNotice(JSON.stringify(record.contract)===JSON.stringify(draft)?`Your draft already matches contract ${record.id}, revision ${record.revision}. It is saved; no second contract or revision is needed.`:`Your draft and exact pins are preserved on contract ${record.id}, revision ${record.revision}. Compare the saved values below. Save draft will create a new revision on this contract, not a second contract.`);setError('');
 }

 function useLatestShotRevision(){initialShotRevision.current=latestShotRevision;setConflicted(false);setRecoveryBaseRecord(null);storeDraft(ownerKey,{body:copy(draft),baseRecord:saved,latestRecord:latest,shotRevision:latestShotRevision,generation:editGeneration.current,conflicted:false,validation,recoveryBaseRecord:null},instance.current);setNotice(`Create will use the refreshed shot revision ${latestShotRevision}. Your draft and exact pins are unchanged.`);setError('');}

 async function loadContract(id:string){
  if(id===selectedContract||!id)return;
  if(dirty&&!window.confirm('Discard this local shot intent draft and open the selected contract?'))return;
  setLoading(true);setError('');setNotice('');setReview(null);setRemoteDiff(null);setConflicted(false);setRecoveryBaseRecord(null);
  try{const shown=await runCommand<ContractRecord>(projectId,'observation.show',{contract_id:id});const read=await showAndValidateRecord(projectId,shown);const record=read.record;const acceptedItem=listItem(record,shot.title);setItems(old=>old.some(item=>item.id===record.id)?old.map(item=>item.id===record.id?acceptedItem:item):[acceptedItem,...old]);setSaved(record);setLatest(record);setDraft(copy(record.contract));setValidation(read.validation);setConflicted(read.unstable);setSelectedContract(id);editGeneration.current+=1;storeDraft(ownerKey,{body:copy(record.contract),baseRecord:record,latestRecord:record,shotRevision:initialShotRevision.current,generation:editGeneration.current,conflicted:read.unstable,validation:read.validation,recoveryBaseRecord:null},instance.current);if(read.unstable)setNotice('The latest saved header could not be matched to a validation result after one retry. No validation status is shown. Refresh status before saving.');}
  catch(reason){setError(messageOf(reason));}
  finally{setLoading(false);}
 }

 async function submit(operation:'create'|'revise'|'rebase'){
  if(busy||pendingDrafts.has(ownerKey))return;
  const generation=editGeneration.current,body=copy(draft),shotRevision=initialShotRevision.current;setBusy(true);setOwnerPending(true);setDraftPending(ownerKey,true,instance.current);setError('');setNotice('');
  try{
   let record:ContractRecord;
   if(operation==='create')record=await runCommand<ContractRecord>(projectId,'observation.create',{shot_id:shot.id,expected_shot_revision:initialShotRevision.current,contract:body});
   else if(operation==='rebase'){
    if(!review||reviewGeneration!==generation)throw new Error('Review this exact draft again before rebasing.');
    record=await runCommand<ContractRecord>(projectId,'observation.rebase',{contract_id:saved!.id,revision:review.revision,contract:body,expected_basis_sha256:review.expected_basis_sha256});
   }else record=await runCommand<ContractRecord>(projectId,'observation.revise',{contract_id:saved!.id,revision:saved!.revision,contract:body});
   noteAcceptedRecordWrite(ownerKey);
   const acceptedItem=listItem(record,shot.title);setItems(old=>old.some(item=>item.id===record.id)?old.map(item=>item.id===record.id?acceptedItem:item):[acceptedItem,...old]);
   const accepted=recordValidation(record);setSelectedContract(record.id);setSaved(record);setLatest(record);setValidation(accepted);setConflicted(false);setRemoteDiff(null);setReview(null);setReviewGeneration(-1);setRecoveryBaseRecord(null);
   const cached=draftCache.get(ownerKey);const newer=cached&&cached.generation!==generation;const nextBody=newer?copy(cached.body):copy(record.contract);const nextGeneration=newer?cached.generation:generation;
   editGeneration.current=nextGeneration;setDraft(nextBody);storeDraft(ownerKey,{body:nextBody,baseRecord:record,latestRecord:record,shotRevision,generation:nextGeneration,conflicted:false,validation:accepted,recoveryBaseRecord:null},instance.current);
   if(!newer){setNotice(`Shot intent saved as contract revision ${record.revision}.`);}
   else setNotice('The submitted version was saved. Newer edits remain in the editor.');
  }catch(reason){
   setError(messageOf(reason));
   if((reason as any)?.status===409||(reason as any)?.code==='contract_rebase_required'){
    setReview(null);setReviewGeneration(-1);setConflicted(true);
    const cached=draftCache.get(ownerKey);storeDraft(ownerKey,{body:copy(cached?.body||draft),baseRecord:saved,latestRecord:latest,shotRevision:initialShotRevision.current,generation:cached?.generation??generation,conflicted:true},instance.current);
    if(operation==='rebase'||(reason as any)?.code==='contract_rebase_required')setRebaseNeedsReview(true);
    await refreshStatus(true);
   }
  }finally{setBusy(false);setOwnerPending(false);setDraftPending(ownerKey,false,instance.current);}
 }

 async function reviewRebase(){
  if(!saved||busy)return;
  const generation=editGeneration.current;setError('');setNotice('Reviewing the exact proposed contract against the current saved basis…');setReview(null);
  try{const result=await runCommand<RebaseReview>(projectId,'observation.rebase-preview',{contract_id:saved.id,contract:copy(draft)});if(editGeneration.current!==generation){setNotice('The proposed contract changed during review. Review the current draft again.');return;}setReview(result);setReviewGeneration(generation);setRebaseNeedsReview(false);setNotice('Review complete. Confirm the rebase only if these exact changes and source pins are intended.');}
  catch(reason){setError(messageOf(reason));}
 }

 async function compareVersion(versionId:string){
  if(!saved)return;
  try{const result=await runCommand<ContractDiff>(projectId,'observation.diff',{contract_id:saved.id,before_version_id:versionId,after_version_id:saved.current_version_id});setHistoryDiff(result);}
  catch(reason){setError(messageOf(reason));}
 }

 const sourceByEdge=new Map(sources.map(row=>[row.edge_id,row]));
 const validationStatus=validation?.status||'not checked';
 const validationRevision=validation?.revision??latest?.revision??saved?.revision;
 const draftNeedsValidationDisclaimer=dirty||conflicted;
 const validationLabel=draftNeedsValidationDisclaimer?`Saved revision ${validationRevision} validation: ${validationStatus}`:`Current saved revision ${validationRevision}: ${validationStatus}`;
 const validationScope=draftNeedsValidationDisclaimer?`This status covers saved revision ${validationRevision} only; the current local draft has not been checked.`:'This status covers the current saved contract revision.';
 const latestCanBeRecoveryBase=!!latest&&latest.shot_id===shot.id&&!!validation&&validation.revision===latest.revision&&validation.version_id===latest.selected_version_id;
 const recoveryBaseline=recoveryBaseRecord&&saved?.id===recoveryBaseRecord.id?recoveryBaseRecord:null;
 const missingSourcePins=draft.source_pins.filter(pin=>!sourceByEdge.has(pin.edge_id)||!!validation?.source_pins?.find(item=>item.edge_id===pin.edge_id&&item.stale));
 const canSubmit=ready&&!busy&&!ownerPending&&!loading&&!refreshing&&!!draft.script_intents.length&&draft.source_pins.length>0;

 return <section className="shot-intent-panel" aria-label="Shot intent contract">
  <div className="shot-intent-heading"><div><h3>Shot intent</h3><p className="muted">Record what the screenplay asks this shot to communicate. Pins name exact source links; validation does not judge rendered images.</p><p className="shot-intent-draft-scope">Unsaved edits stay in this open app session and follow this shot across tabs and shots. Create, Save draft, or confirm rebase to store them. Reloading or closing the app will prompt while edits remain unsaved.</p></div><button type="button" onClick={()=>void refreshStatus()} disabled={loading||refreshing||busy||ownerPending}>Refresh status</button></div>
  {ownerPending&&<p role="status">A save for this shot is still in progress. Its draft is preserved and editing is paused until it finishes.</p>}
  <label className="field"><span>Observation contract</span><select aria-label="Observation contract" value={selectedContract} onChange={(event:any)=>void loadContract(event.target.value)} disabled={loading||busy||ownerPending||items.length<2}>{!items.length&&<option value="">New contract for this shot</option>}{items.map(item=><option key={item.id} value={item.id}>Revision {item.revision} · {item.id}</option>)}</select><small>Selected shot: {shot.title} · latest shot revision {latestShotRevision}{!saved?` · create will use revision ${initialShotRevision.current}`:` · contract ${saved.id} · header revision ${saved.revision}`}</small></label>
  {loading&&<p role="status">Loading exact sources and saved contract…</p>}
  {error&&<div role="alert" className="notice error"><strong>Shot intent could not be updated.</strong><p>{error}</p><button type="button" onClick={()=>void refreshStatus()} disabled={refreshing||busy||ownerPending}>Retry refresh</button></div>}
  {sourceError&&<div role="alert" className="notice warning"><strong>Linked source details are unavailable.</strong><p>{sourceError}</p><button type="button" onClick={()=>void refreshStatus()} disabled={refreshing||busy}>Retry source refresh</button></div>}
  {notice&&<p role="status" className="shot-intent-status">{notice}</p>}
  {rebaseNeedsReview&&<div role="alert" className="notice warning"><strong>The reviewed basis changed.</strong><p>Your draft, exact pins, and previous header CAS are retained. The prior review token is invalid. Review the current proposal again before any rebase.</p><button type="button" onClick={()=>void reviewRebase()} disabled={busy||loading}>Review this draft again</button></div>}
  {conflicted&&!latest&&!saved&&latestShotRevision!==initialShotRevision.current&&<div role="alert" className="notice warning"><strong>The selected shot revision changed.</strong><p>Create still uses shot revision {initialShotRevision.current}; the latest saved shot revision is {latestShotRevision}. Your local draft and exact pins are retained.</p><button type="button" onClick={useLatestShotRevision} disabled={busy}>Use shot revision {latestShotRevision} for create</button></div>}
  {conflicted&&latest&&!saved&&<div role="alert" className="notice warning"><strong>A contract already exists for this shot.</strong><p>The first-create request conflicted with saved contract {latest.id} at revision {latest.revision}. Your entered content and exact pins are retained. Review the comparison, then explicitly choose this existing contract as the draft base or load its saved content.</p><DiffView title="Saved contract vs retained create draft" changes={contractBodyChanges(latest.contract,draft)} ariaLabel="Retained draft comparison"/><div className="button-row"><button type="button" onClick={()=>void refreshStatus()} disabled={refreshing||busy||ownerPending}>Refresh comparison</button><button type="button" onClick={loadLatestIntoDraft} disabled={busy||ownerPending}>Discard draft and load revision {latest.revision}</button><button type="button" className="primary" onClick={keepDraftOnExistingContract} disabled={!latestCanBeRecoveryBase||busy||ownerPending}>Use existing contract and keep my draft</button></div></div>}
  {saved&&<div className={`notice ${validationStatus==='consistent'?'':'warning'}`}><strong>{validationLabel}</strong><p>{validationScope}</p><p>{validation?.findings?.length?`${validation.findings.length} finding${validation.findings.length===1?'':'s'} · authored basis ${validation.basis_current?'current':'changed'}`:'Deterministic source, identity, and authored-basis checks.'}</p><div className="shot-intent-meta"><span>Contract ID <code>{saved.id}</code></span><span>Checked header revision <code>{validation?.revision??'Not checked'}</code></span><span>Checked version <code>{validation?.version_id||'Not checked'}</code></span><span>Editor CAS revision <code>{saved.revision}</code></span><span>Draft base version <code>{saved.current_version_id}</code></span></div></div>}
  {conflicted&&latest&&saved&&(latest.revision!==saved.revision||latest.current_version_id!==saved.current_version_id)&&<div role="alert" className="notice warning"><strong>A newer saved revision is available.</strong><p>The editor still uses header revision {saved.revision}; latest is revision {latest.revision}. Your local draft and exact pins are retained.</p><div className="button-row"><button type="button" onClick={()=>void refreshStatus()} disabled={refreshing||busy||ownerPending}>Refresh comparison</button><button type="button" onClick={loadLatestIntoDraft} disabled={busy||ownerPending}>Discard draft and load revision {latest.revision}</button></div></div>}
  {conflicted&&latest&&saved&&latest.revision===saved.revision&&latest.current_version_id===saved.current_version_id&&!validation&&<div role="alert" className="notice warning"><strong>The saved header could not be matched to validation.</strong><p>No validation status is shown. Your local draft, exact pins, and editor CAS revision {saved.revision} remain unchanged.</p><button type="button" onClick={()=>void refreshStatus()} disabled={refreshing||busy||ownerPending}>Retry status refresh</button></div>}
  {recoveryBaseline&&<DiffView title="Saved contract vs retained create draft" changes={contractBodyChanges(recoveryBaseline.contract,draft)} ariaLabel="Retained draft comparison"/>}
  {remoteDiff&&<DiffView title="Saved revision changes" changes={remoteDiff.changes.map(change=>({path:change.path,before:change.before,after:change.after}))}/>}
  {ready&&!loading&&<fieldset className="shot-intent-fields" disabled={busy||ownerPending}>
   <section className="shot-intent-section"><div className="shot-intent-section-heading"><div><h4>Exact screenplay links</h4><p>Select active links already connected to this shot or its scene. Refresh reports changes without replacing these pins.</p></div></div>
    {!sources.length?<p className="muted">No screenplay source links are connected to this shot yet. Add a link in the source-document workflow, then refresh.</p>:sources.map(row=>{
     const checked=draft.source_pins.some(pin=>pin.edge_id===row.edge_id);const detail=sourceDetails[row.edge_id];const validationPin=validation?.source_pins?.find(pin=>pin.edge_id===row.edge_id);const stale=row.stale||!!validationPin?.stale;
     const stalePins=draft.source_pins.filter(pin=>{const previous=sourceByEdge.get(pin.edge_id);const pinned=saved?.source_pins?.find(item=>item.edge_id===pin.edge_id);return pin.edge_id!==row.edge_id&&(!previous||previous.stale||!!validation?.source_pins?.find(item=>item.edge_id===pin.edge_id)?.stale||!!pinned&&pinned.source_version_id!==previous.version_id);});
     return <div className="shot-source-row" key={row.edge_id}><label className="shot-source-option"><input type="checkbox" checked={checked} onChange={(event:any)=>togglePin(row,event.target.checked)}/><span><strong>{sourceName(row,detail)}</strong><small>{detail?.documentTitle||'Screenplay'} · {detail?.versionLabel||row.version_label}{detail?.versionNumber?` (version ${detail.versionNumber})`:''}{stale?' · source version is stale':''}</small><small>Edge <code>{row.edge_id}</code></small><small>Version <code>{row.version_id}</code> · node <code>{row.node_id}</code></small><small>Source SHA-256 <code>{detail?.contentSha256||row.content_sha256||'Unavailable'}</code></small>{detail?.error&&<small className="warning-text">{detail.error}</small>}</span></label>
      {stalePins.length>0&&!checked&&!stale&&<div className="shot-retarget-shortcuts">{stalePins.map(pin=>{const oldRow=sourceByEdge.get(pin.edge_id);const oldName=oldRow?sourceName(oldRow,sourceDetails[pin.edge_id]):`Saved source ${pin.edge_id}`;return <button type="button" key={pin.edge_id} onClick={()=>previewRetarget(pin.edge_id,row.edge_id)}>Preview retarget from {oldName} to {sourceName(row,detail)}</button>;})}</div>}
     </div>;
    })}
    {!!draft.source_pins.length&&missingSourcePins.map(pin=><div className="shot-source-stale" key={pin.edge_id}><strong>Saved exact pin is unavailable or stale</strong><small>Edge <code>{pin.edge_id}</code> · scope {pin.source_scope==='scene-context'?'Scene context':'Direct shot link'}</small><small>This pin remains in the draft until you explicitly choose a new source during rebase.</small></div>)}
    {!!draft.source_pins.length&&<section className="shot-pin-comparison" aria-label="Saved and current exact pin details"><h5>Saved and current exact pins</h5>{draft.source_pins.map(pin=>{const current=sourceByEdge.get(pin.edge_id);const detail=sourceDetails[pin.edge_id];const previous=saved?.source_pins?.find(item=>item.edge_id===pin.edge_id);return <div className="shot-pin-comparison-row" key={pin.edge_id}><strong>{current?sourceName(current,detail):`Saved exact source ${pin.edge_id}`}</strong><dl><div><dt>Scope</dt><dd>{pin.source_scope==='scene-context'?'Scene context':'Direct shot link'}</dd></div><div><dt>Saved pin</dt><dd>{previous?<>Version <code>{previous.source_version_id}</code> · node <code>{previous.node_id}</code> · source SHA-256 <code>{previous.source_sha256||'Unavailable'}</code>{previous.scope_sha256&&<> · scope SHA-256 <code>{previous.scope_sha256}</code></>}</>:'Not saved yet'}</dd></div><div><dt>Current linked source</dt><dd>{current?<>Version <code>{current.version_id}</code> · node <code>{current.node_id}</code> · source SHA-256 <code>{detail?.contentSha256||current.content_sha256||'Unavailable'}</code>{(current.stale||previous&&previous.source_version_id!==current.version_id)&&' · differs from the saved pin'}</>:'Unavailable; saved pin retained in this draft'}</dd></div></dl></div>;})}</section>}
    {retargetPreview&&<RetargetReview preview={retargetPreview} body={draft} saved={saved} rows={sourceByEdge} details={sourceDetails} onCancel={()=>setRetargetPreview(null)} onConfirm={confirmRetarget} disabled={busy||ownerPending}/>}
   </section>
   <section className="shot-intent-section"><div className="shot-intent-section-heading"><div><h4>Purpose and communication</h4><p>Keep each purpose attached to one exact source edge.</p></div><button type="button" onClick={addIntent} disabled={!draft.source_pins.length}>Add purpose</button></div>
    {draft.script_intents.map(intent=><article className="shot-intent-card" key={intent.id} data-intent-id={intent.id}><div className="shot-intent-card-heading"><strong>Purpose <small>Stable ID <code>{intent.id}</code></small></strong><button type="button" className="text-button" aria-label={`Remove purpose ${intent.purpose||intent.id}`} onClick={()=>patchDraft(body=>({...body,script_intents:body.script_intents.filter(item=>item.id!==intent.id)}))}>Remove</button></div>
     <label className="field"><span>Exact source link</span><select aria-label={`Source for purpose ${intent.id}`} value={intent.source_edge_id} onChange={(event:any)=>{const row=sourceByEdge.get(event.target.value);if(row)patchIntent(intent.id,value=>({...value,source_edge_id:row.edge_id,source_scope:sourceScope(row)}));}}>{draft.source_pins.map(pin=>{const row=sourceByEdge.get(pin.edge_id);return <option key={pin.edge_id} value={pin.edge_id}>{row?sourceName(row,sourceDetails[row.edge_id]):`${pin.source_scope} · saved pin ${pin.edge_id}`}</option>;})}</select></label>
     <label className="field"><span>Purpose</span><input aria-label={`Purpose ${intent.id}`} value={intent.purpose} maxLength={120} onChange={(event:any)=>patchIntent(intent.id,value=>({...value,purpose:event.target.value}))} placeholder="e.g. establish the handoff"/></label>
     <label className="field"><span>Communication</span><textarea aria-label={`Communication ${intent.id}`} value={intent.communication} maxLength={4000} rows={3} onChange={(event:any)=>patchIntent(intent.id,value=>({...value,communication:event.target.value}))} placeholder="What should the audience understand from this source?"/></label>
     <label className="field"><span>Basis</span><select aria-label={`Purpose basis ${intent.id}`} value={intent.basis} onChange={(event:any)=>patchIntent(intent.id,value=>({...value,basis:event.target.value}))}><option value="direct">Direct</option><option value="interpreted">Interpreted</option><option value="unknown">Unknown</option></select></label>
    </article>)}
    {!draft.script_intents.length&&<p className="muted">No purpose statements yet.</p>}
   </section>
   <section className="shot-intent-section"><div className="shot-intent-section-heading"><div><h4>Source-specific requirements</h4><p>Requirements keep their stable IDs and point to one or more selected exact links.</p></div><button type="button" onClick={addRequirement}>Add requirement</button></div>
    {draft.requirements.map(item=><article className="shot-intent-card" key={item.id} data-requirement-id={item.id}><div className="shot-intent-card-heading"><strong>Requirement <small>Stable ID <code>{item.id}</code></small></strong><button type="button" className="text-button" aria-label={`Remove requirement ${item.id}`} onClick={()=>patchDraft(body=>({...body,requirements:body.requirements.filter(row=>row.id!==item.id)}))}>Remove</button></div>
     <div className="shot-intent-grid"><label className="field"><span>Priority</span><select aria-label={`Priority ${item.id}`} value={item.priority} onChange={(event:any)=>{const priority=event.target.value as Requirement['priority'];patchRequirement(item.id,value=>priority==='unknown'?{...value,priority,topic:value.statement||value.topic||'',statement:null}:{...value,priority,statement:value.topic||value.statement||'',topic:null});}}><option value="must">Must</option><option value="prefer">Prefer</option><option value="unknown">Unknown</option></select></label><label className="field"><span>Basis</span><select aria-label={`Requirement basis ${item.id}`} value={item.basis} onChange={(event:any)=>patchRequirement(item.id,value=>({...value,basis:event.target.value}))}><option value="direct">Direct</option><option value="interpreted">Interpreted</option><option value="unknown">Unknown</option></select></label></div>
     <label className="field"><span>{item.priority==='unknown'?'Topic':'Requirement statement'}</span><textarea aria-label={`${item.priority==='unknown'?'Topic':'Requirement statement'} ${item.id}`} rows={3} maxLength={4000} value={item.priority==='unknown'?item.topic||'':item.statement||''} onChange={(event:any)=>patchRequirement(item.id,value=>item.priority==='unknown'?{...value,topic:event.target.value,statement:null}:{...value,statement:event.target.value,topic:null})}/></label>
     <fieldset className="shot-edge-select"><legend>Exact source links</legend>{draft.source_pins.map(pin=>{const row=sourceByEdge.get(pin.edge_id);return <label key={pin.edge_id}><input type="checkbox" checked={item.source_edge_ids.includes(pin.edge_id)} onChange={(event:any)=>patchRequirement(item.id,value=>({...value,source_edge_ids:event.target.checked?[...value.source_edge_ids,pin.edge_id]:value.source_edge_ids.filter(edge=>edge!==pin.edge_id)}))}/><span>{row?sourceName(row,sourceDetails[row.edge_id]):`Saved exact pin · ${pin.edge_id}`}</span></label>;})}{!draft.source_pins.length&&<small>Select an exact screenplay link above.</small>}</fieldset>
    </article>)}
    {!draft.requirements.length&&<p className="muted">No source-specific requirements yet.</p>}
   </section>
   {saved&&<section className="shot-intent-section"><h4>Saved contract history</h4><p>Each revision is immutable. Comparing history does not change the editor.</p><div className="shot-history">{saved.history.map(version=><div className="shot-history-row" key={version.id}><span><strong>Revision {version.number}</strong><small>{version.operation} · {new Date(version.created_at).toLocaleString()}</small><small>Version <code>{version.id}</code></small></span><button type="button" onClick={()=>void compareVersion(version.id)} disabled={version.id===saved.current_version_id}>Compare</button></div>)}</div></section>}
  </fieldset>}
  {historyDiff&&<DiffView title="Contract version comparison" changes={historyDiff.changes.map(change=>({path:change.path,before:change.before,after:change.after}))}/>}
  {review&&<section className="shot-intent-review" aria-label="Rebase review"><h4>Reviewed basis changes</h4><p>Saved basis <code>{review.saved_basis_sha256}</code> · current basis <code>{review.current_basis_sha256}</code></p><DiffView title={review.basis_changed?'The saved authored basis changed':'The current basis matches the saved basis'} changes={review.changes.map(change=>({path:change.path,before:change.saved_value,after:change.current_value}))}/>{review.changes_truncated&&<p role="status">Additional basis differences were omitted by the service.</p>}<p>Review token <code>{review.expected_basis_sha256}</code> · contract revision {review.revision}</p><button type="button" className="primary" onClick={()=>void submit('rebase')} disabled={!canSubmit||reviewGeneration!==editGeneration.current}>Confirm reviewed rebase</button></section>}
  {ready&&!loading&&<div className="button-row shot-intent-actions">{!saved?<button type="button" className="primary" onClick={()=>void submit('create')} disabled={!canSubmit||conflicted}>Create observation contract</button>:<><button type="button" className="primary" onClick={()=>void submit('revise')} disabled={!canSubmit||!dirty||conflicted}>Save draft</button><button type="button" onClick={()=>void reviewRebase()} disabled={busy||ownerPending||loading}>Review rebase</button></>}</div>}
  {saved&&<div className="shot-intent-cas"><small>Shot revision used for contract creation: <code>{initialShotRevision.current}</code></small><small>Contract header CAS revision for edit: <code>{saved.revision}</code></small><small>Exact source pins in draft: {draft.source_pins.length} · linked sources now available: {sources.length}</small></div>}
 </section>;
}

function DiffView({title,changes,ariaLabel}:{title:string;changes:Array<{path:string;before:unknown;after:unknown}>;ariaLabel?:string}){
 return <section className="shot-intent-diff" role={ariaLabel?'region':undefined} aria-label={ariaLabel}><h4>{title}</h4>{!changes.length?<p>No field changes.</p>:changes.map((change,index)=><div className="shot-intent-diff-row" key={`${change.path}-${index}`}><strong>{readablePath(change.path)}</strong><dl><div><dt>Saved</dt><dd>{displayValue(change.before)}</dd></div><div><dt>Current or proposed</dt><dd>{displayValue(change.after)}</dd></div></dl></div>)}</section>;
}

function RetargetReview({preview,body,saved,rows,details,onCancel,onConfirm,disabled}:{preview:RetargetPreview;body:ContractBody;saved:ContractRecord|null;rows:Map<string,SourceRow>;details:Record<string,SourceDetails>;onCancel:()=>void;onConfirm:()=>void;disabled:boolean}){
 const oldPin=body.source_pins.find(pin=>pin.edge_id===preview.oldEdgeId),oldRow=rows.get(preview.oldEdgeId),nextRow=rows.get(preview.newEdgeId);
 if(!oldPin||!nextRow)return null;
 const oldSaved=saved?.source_pins.find(item=>item.edge_id===preview.oldEdgeId),oldDetail=details[preview.oldEdgeId],nextDetail=details[nextRow.edge_id];
 return <section className="shot-retarget-preview" aria-label="Retarget preview" role="group"><h5>Retarget preview</h5><p>This explicit draft edit changes the source edge used by linked purposes and requirements. Nothing changes until you choose Retarget draft pin.</p><div><strong>Saved/local source</strong><small>{oldRow?sourceName(oldRow,oldDetail):`Saved source ${preview.oldEdgeId}`} · {oldPin.source_scope==='scene-context'?'Scene context':'Direct shot link'}</small><small>Version <code>{oldSaved?.source_version_id||oldRow?.version_id||'Unavailable'}</code> · node <code>{oldSaved?.node_id||oldRow?.node_id||'Unavailable'}</code> · source SHA-256 <code>{oldSaved?.source_sha256||oldDetail?.contentSha256||'Unavailable'}</code></small></div><div><strong>Proposed current source</strong><small>{sourceName(nextRow,nextDetail)} · {sourceScope(nextRow)==='scene-context'?'Scene context':'Direct shot link'}</small><small>Version <code>{nextRow.version_id}</code> · node <code>{nextRow.node_id}</code> · source SHA-256 <code>{nextDetail?.contentSha256||nextRow.content_sha256||'Unavailable'}</code></small></div><div className="button-row"><button type="button" onClick={onCancel}>Cancel</button><button type="button" className="primary" onClick={onConfirm} disabled={disabled}>Retarget draft pin</button></div></section>;
}

function messageOf(reason:unknown){const value=reason as any;return value?.message||'The request could not be completed. Your draft remains in the editor.';}
