import {requireOwner} from '../../../lib/ownerAccess.ts';
export const dynamic = 'force-dynamic';

// Scans consume paid provider credits and write audit data; only the worker may run them.
export async function POST() {
  return Response.json({error:'Market updates are managed automatically.'}, {status:403,headers:{'Cache-Control':'no-store'}});
}

export async function GET(request:Request) {
  const denied=await requireOwner(request); if(denied) return denied;
  return Response.json({scanning:false, managed:true, progress:null},{headers:{'Cache-Control':'no-store'}});
}
