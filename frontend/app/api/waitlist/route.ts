import {acceptWaitlist} from '@/lib/waitlist';
import {writeWaitlist} from '@/lib/waitlistDatabase';
export const dynamic='force-dynamic';
export async function POST(request:Request) {return acceptWaitlist(request,writeWaitlist);}
