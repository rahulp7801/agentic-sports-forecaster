/** Validate display metrics without inventing uncertainty or execution eligibility. */
export function expectedProfit(expectedReturn: unknown, stake: number): number | null {
  return typeof expectedReturn === 'number' && Number.isFinite(expectedReturn) && Number.isFinite(stake) && stake >= 0
    ? expectedReturn * stake : null;
}

export function parlayScenario(probabilities: number[], grossPayout: number) {
  if (probabilities.length < 2 || !Number.isFinite(grossPayout) || grossPayout <= 1
      || probabilities.some(p => !Number.isFinite(p) || p < 0 || p > 1)) return null;
  const independent = probabilities.reduce((a, p) => a * p, 1);
  const lower = Math.max(0, probabilities.reduce((a, p) => a + p, 0) - probabilities.length + 1);
  const upper = Math.min(...probabilities);
  return {independent, lower, upper, expectedReturn: independent * grossPayout - 1};
}
