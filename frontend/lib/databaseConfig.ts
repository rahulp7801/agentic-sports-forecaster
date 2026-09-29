export function databaseConfig(value: string | undefined, ca?: string, hosted=false) {
  if (!value) throw new Error('Service unavailable');
  const url = new URL(value.replace('postgresql+psycopg://', 'postgresql://'));
  // URLSearchParams.get reads the first value; pg uses the last. Reject
  // ambiguity before handing the URL to the driver or stripping CA options.
  const modes=url.searchParams.getAll('sslmode');
  const verifiedMode=modes.length===1 && modes[0]==='verify-full';
  if(hosted && !verifiedMode) {
    throw new Error('Hosted database requires certificate and hostname verification with one sslmode=verify-full');
  }
  if (!ca) return {connectionString: url.toString()};
  if (!verifiedMode) {
    throw new Error('Custom database CA requires one sslmode=verify-full');
  }
  // pg reparses URL SSL options after Pool options; avoid replacing the explicit CA.
  for (const key of ['sslmode', 'sslrootcert', 'sslcert', 'sslkey', 'ssl']) url.searchParams.delete(key);
  return {connectionString: url.toString(), ssl: {ca, rejectUnauthorized: true}};
}
