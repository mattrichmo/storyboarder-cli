import type {Session} from './types';
let launchToken = '';
export class ApiError extends Error {
  constructor(public code:string,message:string,public details:any={},public status=0){super(message);}
}
export async function api<T>(path:string,method='GET',data?:unknown,signal?:AbortSignal):Promise<T>{
  const headers:Record<string,string>={};
  if(method!=='GET')headers['X-Storyboarder-Token']=launchToken;
  const multipart=data instanceof FormData;
  if(data!==undefined&&!multipart)headers['Content-Type']='application/json';
  let response:Response;
  try{response=await fetch('/api/v1'+path,{method,headers,body:data===undefined?undefined:multipart?data as FormData:JSON.stringify(data),credentials:'same-origin',signal});}
  catch(error){if(error instanceof Error&&error.name==='AbortError')throw error;throw new ApiError('connection','Couldn’t reach Storyboarder on this computer. Check that the app is still running, then try again.');}
  let result:any;
  try{result=await response.json();}catch{throw new ApiError('connection','Storyboarder returned an unreadable response. Refresh the page and try again.',{},response.status);}
  if(!response.ok){const code=result.error?.code||'request';const messages:Record<string,string>={revision_conflict:'This item changed elsewhere. Your edits are still here; refresh the project before saving again.',not_found:'This item is no longer available. Refresh the project and try again.',unsafe_path:'Choose a file inside the project folder.',in_use:'This item is still connected to the story. Remove or change those connections first, or archive the item instead.',invalid_request:'Some details need attention. Review the form and try again.',internal:'Storyboarder couldn’t finish that action. Try again, then check Project care if the problem continues.'};throw new ApiError(code,messages[code]||result.error?.message||'The request could not be completed.',result.error?.details,response.status);}
  return result as T;
}
export async function openSession():Promise<Session>{const session=await api<Session>('/session');launchToken=session.token;return session;}
export const projectPath=(id:string,path='')=>`/projects/${encodeURIComponent(id)}${path}`;
export const mediaUrl=(project:string,media:string,size=480)=>`/api/v1/projects/${encodeURIComponent(project)}/media/${encodeURIComponent(media)}?size=${size}`;
export const originalUrl=(project:string,media:string)=>`/api/v1/projects/${encodeURIComponent(project)}/media/${encodeURIComponent(media)}`;
export const exportUrl=(project:string,path:string,download=false)=>`/api/v1/projects/${encodeURIComponent(project)}/files/${path.split('/').map(encodeURIComponent).join('/')}${download?'?download=true':''}`;
export const jobImageUrl=(project:string,job:string,key:string)=>`/api/v1/projects/${encodeURIComponent(project)}/jobs/${encodeURIComponent(job)}/outputs/${encodeURIComponent(key)}`;
export const runCommand=<T=any>(project:string,name:string,payload:Record<string,any>={})=>api<T>(projectPath(project,`/commands/${encodeURIComponent(name)}`),'POST',payload);
