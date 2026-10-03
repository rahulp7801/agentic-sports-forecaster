import Link from 'next/link';
import {headers} from 'next/headers';
import {redirect} from 'next/navigation';
import {authConfigured} from '@/lib/ownerPolicy';
import {isOwner} from '@/lib/ownerAccess';
import OwnerLogin from '@/components/OwnerLogin';
export const dynamic='force-dynamic';
export default async function LoginPage() {
  if(await isOwner(await headers())) redirect('/terminal');
  return <main style={{maxWidth:520,margin:'12vh auto',padding:28}}><Link href="/">← Linework</Link>
    <p style={{marginTop:40}}>PRIVATE PREVIEW</p><h1>Owner access</h1>
    <p>The live dashboard is currently reserved for the owner. GitHub verifies your identity; signing in with another account does not grant access.</p>
    <OwnerLogin configured={authConfigured()} />
    <p>If access was denied, use the owner account or <Link href="/#waitlist">join the waitlist</Link>.</p>
    <Link href="/#backtest-demo">Explore the public demo →</Link></main>;
}
