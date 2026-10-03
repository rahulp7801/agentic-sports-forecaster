import {createHash} from 'node:crypto';
import {canonicalForecastDisplayJson,FORECAST_RECORD_BINDING_PROTOCOL,validForecastDisplayRequest,
  type ForecastDisplayRequest,type ForecastRecordBinding} from './forecastDisplayPacket.ts';

/** Private producer commits the serialized output and exact request as one packet. */
export function bindForecastDisplayPacket<T extends object>(page:T,request:ForecastDisplayRequest):T&{binding:ForecastRecordBinding} {
  if(!validForecastDisplayRequest(request)) throw Error('Invalid forecast display request');
  // Match the JSON transport's omission of undefined optional output fields.
  const payload=JSON.parse(JSON.stringify(page)) as T;
  const requestCopy={sport:request.sport,view:request.view,offset:request.offset,limit:request.limit,revision:request.revision,player:request.player};
  const payload_sha256=createHash('sha256').update(canonicalForecastDisplayJson({protocol:FORECAST_RECORD_BINDING_PROTOCOL,
    resource:'signals',request:requestCopy,payload})).digest('hex');
  return {...payload,binding:{protocol:FORECAST_RECORD_BINDING_PROTOCOL,resource:'signals',request:requestCopy,payload_sha256}};
}
