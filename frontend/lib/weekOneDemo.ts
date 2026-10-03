import display from '../data/week-one-demo-display.json' with {type:'json'};

/** Reviewed, fixed retrospective display outputs; never live offers or accepted picks. */
export const WEEK_ONE_DEMO=display.records;
export const DEMO_HISTORY_CAPTURED_AT=display.history_captured_at;
export const DEFAULT_DEMO_INDEX=1;
/** Grade the three retained over forecasts against their final values. */
export function demoResult(record:typeof WEEK_ONE_DEMO[number]) {
  return {outcome:record.actual>record.threshold ? 'Above threshold' : 'Below threshold',
    correct:record.actual>record.threshold,
    recommendation:'Research only',historical_price:null,profit:null,execution_ready:false};
}

/** Select a retained descriptive summary without reconstructing a model. */
export function demoHistory(record:typeof WEEK_ONE_DEMO[number]) {
  return record.history;
}
