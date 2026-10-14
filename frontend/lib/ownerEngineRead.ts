import 'server-only';
import {requireOwner} from './ownerAccess.ts';
import {engineDisplayReply,type EngineDisplayResource} from './engineTransport.ts';

/** Public platform integration: never import forecast, qualification or collection implementations. */
export async function ownerEngineRead<T>(request:Request,resource:EngineDisplayResource,
  project:(data:unknown)=>T|null) {
  return engineDisplayReply(request,resource,project,{authorize:requireOwner,
    config:()=>({origin:process.env.PRIVATE_ENGINE_ORIGIN,token:process.env.PRIVATE_ENGINE_READ_TOKEN}),
    transport:fetch});
}
