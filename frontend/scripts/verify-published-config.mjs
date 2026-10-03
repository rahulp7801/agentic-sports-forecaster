export function hosted_read_dsn(value,ca) {
  if(!value)throw Error('Restricted database credential is required');
  const url=new URL(value.replace('postgresql+psycopg://','postgresql://'));
  if(!['postgres:','postgresql:'].includes(url.protocol) || url.searchParams.getAll('sslmode').length!==1 || url.searchParams.get('sslmode')!=='verify-full')throw Error('Published snapshot reader requires verified TLS');
  if(url.hostname.endsWith('.pooler.supabase.com') && url.port==='5432')url.port='6543';
  if(!ca)return {connectionString:url.toString()};
  for(const key of ['sslmode','sslrootcert','sslcert','sslkey','ssl'])url.searchParams.delete(key);
  return {connectionString:url.toString(),ssl:{ca,rejectUnauthorized:true}};
}
