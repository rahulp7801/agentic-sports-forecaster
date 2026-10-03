export const OWNER_GITHUB_ID = '76501505';
export const OWNER_GITHUB_LOGIN = 'rahulp7801';
export const SESSION_SECONDS = 8 * 60 * 60;
export const PRODUCTION_ORIGIN = 'https://agentic-ev-analytics-platform.vercel.app';

export function authConfigured(env: Record<string,string|undefined> = process.env) {
  const url=env.NEXTAUTH_URL;
  const local=env.NODE_ENV==='development' && /^http:\/\/localhost:\d+$/.test(url ?? '');
  return Boolean((url===PRODUCTION_ORIGIN || local) &&
    env.NEXTAUTH_SECRET && env.NEXTAUTH_SECRET.length>=32 && env.GITHUB_CLIENT_ID && env.GITHUB_CLIENT_SECRET);
}

export function ownerAccount(account: {provider?:string;providerAccountId?:string}|null|undefined) {
  return account?.provider==='github' && account.providerAccountId===OWNER_GITHUB_ID;
}

export function ownerToken(token: Record<string,unknown>|null, now=Date.now()) {
  return Boolean(token && token.sub===OWNER_GITHUB_ID && token.ownerId===OWNER_GITHUB_ID &&
    typeof token.ownerIssuedAt==='number' && Number.isFinite(token.ownerIssuedAt) &&
    token.ownerIssuedAt<=now && now-token.ownerIssuedAt<SESSION_SECONDS*1000);
}

/** Limit both login and logout redirects to this application's fixed destinations. */
export function ownerRedirect(url:string,baseUrl:string) {
  try {
    const target=new URL(url,baseUrl);
    if(target.origin===new URL(baseUrl).origin && ['/', '/terminal', '/login'].includes(target.pathname)) return baseUrl+target.pathname;
  } catch { /* Invalid URLs never become external redirects. */ }
  return baseUrl+'/terminal';
}
