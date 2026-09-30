import type {State,Meta,Entity,InputField} from './types';
const labels:Record<string,string>={
  asset:'Library item',context:'Story direction',scene:'Scene',location_id:'Location',visual_style:'Visual style',premise:'Story premise',
  arc:'Sequence direction',tone:'Tone',framing:'Framing',camera:'Camera plan',time:'Time of day',
  constraints:'Production notes',owner_id:'Apply direction to',key:'Topic',content:'Direction notes',
  operation:'How this changes earlier direction',revision:'Version check',target_revision:'Version check',
  parent_id:'Place under',position:'Order',shot_id:'Shot',asset_id:'Library item',media_id:'Image',
  accepted:'Added',discarded:'Removed from intake',pending:'Needs review',running:'In progress',succeeded:'Complete',failed:'Needs attention',cancelled:'Stopped',
  selected:'Selected',approved:'Approved',archived:'Archived',queued:'Ready to run',draft:'Draft',
  append:'Add to earlier notes',replace:'Replace earlier notes',exclude:'Hide earlier notes here',
  order:'Story order',relationship:'Library connection',assignment:'Shot reference',location_default:'Default location',
  story:'Story flow',assets:'Reference map',frame:'Storyboard image',record:'Item',
  character:'Character',location:'Location',prop:'Prop',reference:'General reference',
  'same-person-as':'Same person as','appears-at':'Appears at','alternate-view-of':'Alternate view of',
  'setting-reference':'Location reference','part-of':'Part of','inspired-by':'Inspired by','related-to':'Related to','wears':'Wears',
  create_title:'New item name',create_type:'Item type',include_media:'Include images in package',
  approved_only:'Use approved frames only',recursive:'Include images in subfolders',
};
export const human=(value:string)=>labels[value]||value.replaceAll('_',' ').replaceAll('-',' ').replace(/\b\w/g,c=>c.toUpperCase());
export const displayTitle=(value:string)=>/^[A-Z0-9]+(?:_[A-Z0-9]+)+$/.test(value)?value.split('_').map(part=>/^\d+$/.test(part)?part:part.charAt(0)+part.slice(1).toLowerCase()).join(' '):value;
export const fieldLabel=(name:string,fallback?:string)=>labels[name]||fallback||human(name);
export const emptySourceMessage=(source:string)=>({
  assets:'No library items to choose from yet. Create one first.',
  sequences:'No sequences to choose from yet. Create one first.',
  scenes:'No scenes to choose from yet. Create one first.',
  shots:'No shots to choose from yet. Create one first.',
  locations:'No locations to choose from yet. Add one to the reference library first.',
  media:'No project images yet. Import an image first.',
  asset_images:'No images in this library item yet. Add one first.',
  story:'No story levels to choose from yet. Create a sequence, scene, or shot first.',
  parents:'No suitable place to add this yet. Create a sequence or scene first.',
  scripts:'No image tools are connected yet. Use the Storyboarder CLI to add a trusted tool.',
} as Record<string,string>)[source]||'Nothing to choose from yet. Add the item first.';
export const statusLabel=(value:string)=>human(value);
export const roleLabel=(value:string)=>({subject:'Subject', 'setting-reference':'Location',costume:'Wardrobe',prop:'Prop',reference:'General reference'} as Record<string,string>)[value]||human(value);
export const operationLabel=(value:string)=>({append:'Added here',replace:'Earlier direction replaced here',exclude:'Earlier direction hidden here'} as Record<string,string>)[value]||human(value);
export const sourceLabel=(kind:string)=>({project:'Project',sequence:'Sequence',scene:'Scene',shot:'Shot',asset:'Library item'} as Record<string,string>)[kind]||human(kind);
export const shortId=(id:string)=>id.slice(0,8);
export const fieldText=(value:unknown)=>value==null?'':String(value);
export const niceDate=(value:string)=>new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',year:'numeric'}).format(new Date(value));
export const kindLabel=(e:Entity)=>e.kind==='asset'?human(fieldText(e.fields.type)):sourceLabel(e.kind);
export const activeEntities=(state:State,kind?:string)=>state.entities.filter(e=>!e.archived&&(!kind||e.kind===kind));
export function allRecords(state:State):any[]{return [...state.entities,...state.media,...state.intake,...state.asset_media,...state.links,...state.assignments,...state.context_blocks,...state.frames,...state.layouts,...state.jobs];}
export function commandDefaults(entity:any):Record<string,any>{
  if(!entity)return {};
  return {...entity,...(entity.fields||{}),id:entity.id,revision:entity.revision,...(entity.kind&&entity.kind!=='asset'?{owner_id:entity.id}:{}),...(entity.kind==='shot'?{shot_id:entity.id}:{}),...(entity.kind==='asset'?{asset_id:entity.id,source_id:entity.id}:{}),...(entity.key?{content:entity.text}:{}),tags:entity.tags||[],aliases:entity.aliases||[]};
}
export function selectOptions(field:InputField,state:State,meta:Meta,values:Record<string,any>):{value:string;label:string}[]{
  if(field.options.length)return field.options.map(o=>({value:o,label:human(o)}));
  const source=field.source;
  if(source==='scripts')return meta.scripts.map(s=>({value:s.name,label:s.name+(s.description?' — '+s.description:'')}));
  const kinds:Record<string,string>={assets:'asset',sequences:'sequence',scenes:'scene',shots:'shot',projects:'project'};
  let records:any[]=[];
  const byId=Object.fromEntries(state.entities.map(e=>[e.id,e]));
  if(kinds[source])records=activeEntities(state,kinds[source]);
  else if(source==='locations')records=activeEntities(state,'asset').filter(e=>e.fields.type==='location');
  else if(source==='story'||source==='parents')records=activeEntities(state).filter(e=>e.kind!=='asset'&&(source!=='parents'||e.kind!=='shot'));
  else records=(state as any)[source]||[];
  if(source==='asset_images')records=state.media;
  if(source==='asset_images'&&values.asset_id){const allowed=new Set(state.asset_media.filter(m=>m.asset_id===values.asset_id).map(m=>m.media_id));records=records.filter(r=>allowed.has(r.id));}
  if(source==='asset_media'&&values.asset_id)records=records.filter(r=>r.asset_id===values.asset_id);
  return records.map(r=>{
    let label=displayTitle(r.title||r.original_name||r.name||r.key||'Untitled item');
    if(source==='frames')label=`${displayTitle(byId[r.shot_id]?.title||'Shot')} · image ${r.version} · ${statusLabel(r.state)}`;
    if(source==='asset_media')label=`${displayTitle(byId[r.asset_id]?.title||'Library item')} / ${state.media.find(m=>m.id===r.media_id)?.original_name||'Image'}${r.is_primary?' · cover image':''}`;
    if(source==='links')label=`${displayTitle(byId[r.source_id]?.title||'Item')} → ${human(r.relation)} → ${displayTitle(byId[r.target_id]?.title||'Item')}`;
    if(source==='assignments')label=`${displayTitle(byId[r.shot_id]?.title||'Shot')} → ${roleLabel(r.role)} → ${displayTitle(byId[r.asset_id]?.title||'Library item')}`;
    if(source==='intake')label=`${r.original_name} · ${statusLabel(r.state)}${r.duplicate?' · identical image':''}`;
    return {value:r.id,label};
  });
}
