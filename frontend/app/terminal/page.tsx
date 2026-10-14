import {headers} from 'next/headers';
import {redirect} from 'next/navigation';
import {isOwner} from '@/lib/ownerAccess';
import { connection } from 'next/server';
import TerminalApp from '@/components/TerminalApp';

export default async function TerminalPage() {
  await connection();
  if(!await isOwner(await headers())) redirect('/login');
  return <TerminalApp />;
}
