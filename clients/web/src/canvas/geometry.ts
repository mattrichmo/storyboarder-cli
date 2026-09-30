import type {Entity,Edge,Point,Viewport,CanvasMode} from '../types';
export const NODE_W=238,NODE_H=222;
export const clamp=(value:number,min:number,max:number)=>Math.min(max,Math.max(min,value));
export function screenToWorld(point:Point,view:Viewport):Point{return {x:(point.x-view.x)/view.scale,y:(point.y-view.y)/view.scale};}
export function zoomAt(view:Viewport,point:Point,factor:number):Viewport{const scale=clamp(view.scale*factor,.15,3);const world=screenToWorld(point,view);return {scale,x:point.x-world.x*scale,y:point.y-world.y*scale};}
export function hitTest(point:Point,positions:Record<string,Point>):string|null {return Object.keys(positions).reverse().find(id=>{const p=positions[id];return point.x>=p.x&&point.x<=p.x+NODE_W&&point.y>=p.y&&point.y<=p.y+NODE_H;})||null;}
export function tidy(nodes:Entity[],edges:Edge[],mode:CanvasMode):Record<string,Point>{
 const result:Record<string,Point>={};const sorted=[...nodes].sort((a,b)=>a.position-b.position||a.title.localeCompare(b.title)||a.id.localeCompare(b.id));
 if(mode==='assets'){const types=['character','location','prop','reference'];types.forEach((type,column)=>sorted.filter(n=>n.fields.type===type).forEach((n,row)=>{result[n.id]={x:column*320,y:row*280};}));return result;}
 if(mode==='scene'){let row=0;sorted.filter(n=>n.kind==='scene').forEach(n=>{result[n.id]={x:0,y:-300};});sorted.filter(n=>n.kind==='shot').forEach((n,i)=>{result[n.id]={x:i*310,y:0};});sorted.filter(n=>n.kind==='asset').forEach((n,i)=>{result[n.id]={x:(i%5)*310,y:330+Math.floor(i/5)*280};});return result;}
 const children=(id:string)=>sorted.filter(n=>n.parent_id===id);
 const visit=(node:Entity,depth:number,top:number):number=>{const kids=children(node.id);let cursor=top;for(const child of kids)cursor=visit(child,depth+1,cursor);const height=Math.max(280,cursor-top);result[node.id]={x:depth*340,y:top+(height-280)/2};return top+height;};
 const ids=new Set(nodes.map(n=>n.id));let cursor=0;for(const root of sorted.filter(n=>!n.parent_id||!ids.has(n.parent_id))){cursor=visit(root,root.kind==='sequence'?0:root.kind==='scene'?1:2,cursor)+60;}return result;
}
export function fit(positions:Record<string,Point>,width:number,height:number):Viewport{const points=Object.values(positions);if(!points.length)return {x:60,y:60,scale:1};const x=Math.min(...points.map(p=>p.x)),y=Math.min(...points.map(p=>p.y));const w=Math.max(...points.map(p=>p.x))+NODE_W-x,h=Math.max(...points.map(p=>p.y))+NODE_H-y;const scale=clamp(Math.min((width-100)/w,(height-100)/h),.15,1.2);return {scale,x:(width-w*scale)/2-x*scale,y:(height-h*scale)/2-y*scale};}
export function edgePath(a:Point,b:Point):{path:string;label:Point}{const start={x:a.x+NODE_W,y:a.y+NODE_H/2},end={x:b.x,y:b.y+NODE_H/2};const bend=Math.max(65,Math.abs(end.x-start.x)*.5);return {path:`M ${start.x} ${start.y} C ${start.x+bend} ${start.y}, ${end.x-bend} ${end.y}, ${end.x} ${end.y}`,label:{x:(start.x+end.x)/2,y:(start.y+end.y)/2}};}
export function descendants(nodes:Entity[],collapsed:string[]):Set<string>{const result=new Set<string>();const visit=(id:string)=>nodes.filter(n=>n.parent_id===id).forEach(n=>{result.add(n.id);visit(n.id);});collapsed.forEach(visit);return result;}
