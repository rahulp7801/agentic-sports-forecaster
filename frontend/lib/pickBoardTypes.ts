import type {EVSignal} from './types';

/** Recorded output declarations only; qualification and settlement stay in the producer. */
export type PickBoardRecord=EVSignal&{
  prediction_id:string;captured_at:string;lock_at:string;
  board_state:'recorded'|'locked'|'final';selection_policy_version:'pregame-t60-v1';
  result?:'win'|'loss'|'push'|'void'|'pending';result_verified?:boolean;
  actual_value?:number|null;settled_at?:string|null;
};
export type PickBoard={generated_at:string;lock_minutes:60;selection_policy_version:'pregame-t60-v1';
  current:PickBoardRecord[];history:PickBoardRecord[];
  summary:{current:number;settled:number;pending:number;wins:number;losses:number;pushes:number;verified_win_rate:number|null}};
