import styles from './ForecastBaselines.module.css';

/** Descriptive direction counts on one unchanged cohort; never a priced-bet result. */
export default function ForecastBaselines({sample,correct,always_under_correct,always_over_correct}:{
  sample:number;correct:number;always_under_correct:number;always_over_correct:number;
}) {
  const rows=[['Model',correct],['Always Under',always_under_correct],['Always Over',always_over_correct]] as const;
  return <table className={styles.baselines} aria-label="Same-record direction comparison">
    <caption>Same recorded forecasts</caption>
    <thead><tr><th scope="col">Direction rule</th><th scope="col">Accuracy</th><th scope="col">Correct</th></tr></thead>
    <tbody>{rows.map(([label,count])=><tr key={label}><th scope="row">{label}</th><td>{sample ? `${(count/sample*100).toFixed(1)}%` : 'Unavailable'}</td><td>{count}/{sample}</td></tr>)}</tbody>
  </table>;
}
