import type {Session} from './types';
let launchToken = '';
export class ApiError extends Error {
  constructor(public code:string,message:string,public details:any={},public status=0){super(message);}
}
export async function api<T>(path:string,method='GET',data?:unknown,signal?:AbortSignal):Promise<T>{
  if(!path.startsWith('/')||path.startsWith('//')||path.includes('\\')||path.includes('://'))throw new ApiError('invalid_request','Invalid local API path.');
  method=method.toUpperCase();if(!['GET','POST','PUT','PATCH','DELETE'].includes(method))throw new ApiError('invalid_request','Unsupported HTTP method.');
  const headers:Record<string,string>={'Accept':'application/json'};
  if(method!=='GET')headers['X-Storyboarder-Token']=launchToken;
  const multipart=data instanceof FormData;
  if(data!==undefined&&!multipart)headers['Content-Type']='application/json';
  const controller=new AbortController();let timedOut=false;
  const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)controller.abort();
  const timeout=setTimeout(()=>{timedOut=true;controller.abort();},90000);
  try{
    const response=await fetch('/api/v1'+path,{method,headers,body:data===undefined?undefined:multipart?data as FormData:JSON.stringify(data),credentials:'same-origin',cache:'no-store',signal:controller.signal});
    let result:any;
    try{result=await response.json();}catch(e){if(controller.signal.aborted)throw e;throw new ApiError('connection','Storyboarder returned an unreadable response. A write may have completed; retry only with the same operation ID.',{},response.status);}
    if(!response.ok){const code=result?.error?.code||'request';const messages:Record<string,string>={revision_conflict:'This item changed elsewhere. Your edits are still here; refresh the project before saving again.',not_found:'This item is no longer available. Refresh the project and try again.',unsafe_path:'Choose a file inside the project folder.',in_use:'This item is still connected to other records. Review its dependencies or archive it instead.',invalid_request:'Some details need attention. Review the form and try again.',internal:'Storyboarder could not finish that action. Check Project care if the problem continues.'};throw new ApiError(code,messages[code]||result?.error?.message||'The request could not be completed.',result?.error?.details||{},response.status);}
    return result as T;
  }catch(error){
    if(timedOut)throw new ApiError('timeout','The request timed out. A write may already have completed. Retry the same operation ID to retrieve its receipt, rather than create a duplicate.');
    if(error instanceof ApiError)throw error;if(signal?.aborted||(error instanceof Error&&error.name==='AbortError'))throw error;
    throw new ApiError('connection','Could not reach Storyboarder on this computer. A write may already have completed; retry with the same operation ID.');
  }finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
}
export async function openSession():Promise<Session>{const session=await api<Session>('/session');launchToken=session.token;return session;}
export const projectPath=(id:string,path='')=>`/projects/${encodeURIComponent(id)}${path}`;
export const mediaUrl=(project:string,media:string,size=480)=>`/api/v1/projects/${encodeURIComponent(project)}/media/${encodeURIComponent(media)}?size=${size}`;
export const originalUrl=(project:string,media:string)=>`/api/v1/projects/${encodeURIComponent(project)}/media/${encodeURIComponent(media)}`;
export const exportUrl=(project:string,path:string,download=false)=>`/api/v1/projects/${encodeURIComponent(project)}/files/${path.split('/').map(encodeURIComponent).join('/')}${download?'?download=true':''}`;
export const jobImageUrl=(project:string,job:string,key:string)=>`/api/v1/projects/${encodeURIComponent(project)}/jobs/${encodeURIComponent(job)}/outputs/${encodeURIComponent(key)}`;
export const runCommand=<T=any>(project:string,name:string,payload:Record<string,any>={},signal?:AbortSignal)=>api<T>(projectPath(project,`/commands/${encodeURIComponent(name)}`),'POST',payload,signal);
