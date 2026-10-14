import {requireOwner} from '../../../lib/ownerAccess.ts';
import {NextResponse} from 'next/server';
import priorWeekOne from '@/data/nfl-week1-2025-receptions.json';
import priorWeekTwo from '@/data/nfl-week2-2025-receptions.json';
import weekOne from '@/data/nfl-week1-2026.json';
import {publicForecastBenchmark} from '@/lib/publicBenchmarks';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const denied=await requireOwner(request); if(denied) return denied;
  const sport = new URL(request.url).searchParams.get('sport') ?? 'nfl';
  if (sport !== 'nfl' && sport !== 'nba' && sport !== 'cfb') {
    return NextResponse.json({error:'Invalid benchmark request.'}, {status:400,headers:{'Cache-Control':'no-store'}});
  }
  return NextResponse.json({benchmarks:sport === 'nfl' ? [
    publicForecastBenchmark(weekOne),
    publicForecastBenchmark(priorWeekOne),
    publicForecastBenchmark(priorWeekTwo),
  ] : []},
    {headers:{'Cache-Control':'no-store','CDN-Cache-Control':'no-store','Vercel-CDN-Cache-Control':'no-store'}});
}
