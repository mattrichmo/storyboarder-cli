export type EntityKind = 'project'|'asset'|'sequence'|'scene'|'shot';
export type AssetType = 'character'|'location'|'prop'|'reference';
export type FrameState = 'draft'|'selected'|'approved'|'archived';
export type Fields = {[key:string]:string|number|null};
export interface Entity {id:string;kind:EntityKind;title:string;description:string;parent_id:string|null;position:number;fields:Fields;tags:string[];aliases:string[];revision:number;archived:number;created_at:string;updated_at:string;thumbnail_media_id?:string|null;reference_media_ids?:string[];frame_state?:FrameState|null;child_count?:number;media_count?:number;reference_count?:number;link_count?:number}
export interface Media {id:string;path:string;sha256:string;original_name:string;format:string;width:number;height:number;size:number;tags:string[];revision:number;created_at:string;bundle_path?:string}
export interface Intake {id:string;media_id:string;original_name:string;original_path:string;duplicate:number;state:'pending'|'accepted'|'discarded';revision:number;created_at:string}
export interface Membership {id:string;asset_id:string;media_id:string;is_primary:number;revision:number}
export interface Link {id:string;source_id:string;target_id:string;relation:string;revision:number}
export interface Assignment {id:string;shot_id:string;asset_id:string;role:string;media_id:string|null;revision:number;asset?:Entity;media?:Media|null}
export interface Frame {id:string;shot_id:string;media_id:string;version:number;state:FrameState;notes:string;provenance:Record<string,unknown>;revision:number;created_at:string;media?:Media}
export interface ContextBlock {id:string;owner_id:string;key:string;operation:'append'|'replace'|'exclude';text:string;revision:number}
export interface Point {x:number;y:number}
export interface Viewport extends Point {scale:number}
export type CanvasMode = 'story'|'assets'|'scene';
export interface Layout {id:string;name:string;mode:CanvasMode;positions:Record<string,Point>;settings:{hidden?:string[];collapsed?:string[];viewport?:Viewport;filters?:Record<string,string>;scene_id?:string;sequence_id?:string};revision:number;updated_at:string}
export interface JobOutput {key:string;path:string;stored_path:string;sha256:string;width:number;height:number;title:string;notes:string}
export interface Job {id:string;title:string;status:'queued'|'running'|'succeeded'|'failed'|'cancelled';script:string;target:'asset'|'frame';shot_id:string|null;approved:number;revision:number;attempt:number;request:Record<string,any>;result:Record<string,any>;created_at:string;updated_at:string;outputs?:JobOutput[];logs?:Record<string,string>}
export interface ProjectSummary extends Entity {path:string;available?:boolean;browser_accessible?:boolean;recent?:boolean;error?:string;counts:Record<string,number>}
export interface EventRecord {id:number;entity_id:string|null;action:string;details:Record<string,unknown>;created_at:string}
export interface State {project:ProjectSummary;entities:Entity[];media:Media[];intake:Intake[];asset_media:Membership[];links:Link[];assignments:Assignment[];frames:Frame[];context_blocks:ContextBlock[];layouts:Layout[];jobs:Job[];events:EventRecord[]}
export interface InputField {name:string;label:string;type:'text'|'textarea'|'integer'|'number'|'boolean'|'json'|'select'|'tags';required:boolean;options:string[];source:string;help:string;default:any}
export interface Command {name:string;label:string;fields:InputField[];page:string;destructive:boolean;browser:boolean;read_only:boolean}
export interface Script {name:string;description:string;timeout:number;env_keys:string[]}
export interface Meta {commands:Command[];entity_fields:Record<string,any>;scripts:Script[];formats:string[];max_file_bytes:number}
export interface Session {version:string;schema_version:number;token:string;workspace:string|null;can_create:boolean;active_project_id:string|null;projects:ProjectSummary[]}
export interface Edge {id:string;source:string;target:string;kind:'order'|'relationship'|'assignment'|'location_default';label:string;position?:number;revision?:number;media_id?:string|null;source_scope?:Provenance}
export interface Graph {nodes:Entity[];edges:Edge[];total:number;truncated:boolean;mode:CanvasMode}
export interface Provenance {id:string;kind:string;title:string;revision:number}
export interface ResolvedContext {scalars:Record<string,{value:string;label?:string;source:Provenance}>;blocks:Record<string,{text:string;source:Provenance;block_id?:string}[]>;history:{key:string;operation:string;source:Provenance;removed_sources:Provenance[]}[];chain:Provenance[]}
export interface ComposedShot extends Entity {context:ResolvedContext;assignments:Assignment[];frames:Frame[]}
export interface ComposedScene extends Entity {sequence:{id:string;title:string;position:number};context:ResolvedContext;shots:ComposedShot[]}
export interface Issue {severity:string;code:string;message:string;path?:string;shot_id?:string;media_id?:string}
export interface Composition {schema:string;project:Entity;owner:Entity;context:ResolvedContext;scenes:ComposedScene[];media:Media[];validation:Issue[];valid:boolean}
export interface Health {healthy:boolean;schema_version:number;journal_mode:string;project:string;database:string;hashes_checked:boolean;media_checked:number;migrations:{version:number;name:string;checksum:string;applied_at:string}[];issues:Issue[]}
export interface ExportResult {path:string;archive?:string;view?:string;files?:string[];validation?:Issue[];manifest?:Record<string,any>}
export type ActionFn = (name:string, defaults?:Record<string,any>)=>void;
