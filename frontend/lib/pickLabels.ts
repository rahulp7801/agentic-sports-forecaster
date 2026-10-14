import type {PropType} from './types';

/** Display labels only; this module does not admit, qualify or rank a record. */
export const PROP_LABELS:Record<PropType,string>={points:'points',rebounds:'rebounds',assists:'assists',threes:'three-pointers',pra:'points + rebounds + assists',steals:'steals',blocks:'blocks',pass_yds:'passing yards',pass_tds:'passing touchdowns',rush_yds:'rushing yards',rec_yds:'receiving yards',receptions:'receptions'};
const SPORTSBOOK_LABELS:Record<string,string>={betonlineag:'BetOnline',draftkings:'DraftKings',fanduel:'FanDuel',
  betmgm:'BetMGM',caesars:'Caesars',betrivers:'BetRivers',fanatics:'Fanatics'};
export function sportsbookLabel(value:string){return SPORTSBOOK_LABELS[value.toLowerCase()] ?? value;}
