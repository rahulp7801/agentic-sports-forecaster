import type {NextAuthOptions} from 'next-auth';
import GitHub from 'next-auth/providers/github';
import {authConfigured,ownerAccount,ownerToken,ownerRedirect,OWNER_GITHUB_ID,OWNER_GITHUB_LOGIN,SESSION_SECONDS} from './ownerPolicy';

export const authOptions:NextAuthOptions={
  secret:process.env.NEXTAUTH_SECRET,
  session:{strategy:'jwt',maxAge:SESSION_SECONDS},
  jwt:{maxAge:SESSION_SECONDS},
  useSecureCookies:process.env.NEXTAUTH_URL?.startsWith('https://') ?? true,
  providers:[GitHub({clientId:process.env.GITHUB_CLIENT_ID ?? '',clientSecret:process.env.GITHUB_CLIENT_SECRET ?? '',
    authorization:{params:{scope:'read:user'}},checks:['pkce','state']})],
  pages:{signIn:'/login',error:'/login'},
  callbacks:{
    async signIn({account}) {return authConfigured() && ownerAccount(account);},
    async jwt({token,account}) {
      if(account) {
        if(!ownerAccount(account)) return {};
        // Persist identity from the authenticated provider, never session-update input.
        token={sub:OWNER_GITHUB_ID,ownerId:OWNER_GITHUB_ID,ownerIssuedAt:Date.now()};
      }
      return ownerToken(token) ? token : {};
    },
    async session({session,token}) {
      // Neither GitHub tokens, email addresses nor provider payloads reach the browser.
      return {expires:session.expires,user:ownerToken(token) ? {name:OWNER_GITHUB_LOGIN} : undefined};
    },
    async redirect({url,baseUrl}) {return ownerRedirect(url,baseUrl);},
  },
  logger:{error(){console.error('Owner authentication failed.');},warn(){console.warn('Owner authentication warning.');},debug(){}},
};
