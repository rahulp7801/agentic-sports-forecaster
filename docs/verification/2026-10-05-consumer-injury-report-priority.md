# Surface acute teammate risk in captured consumer context

The compact consumer pick card displayed the first two flagged injury reports
in provider order. A season-long injury or opponent report could therefore
occupy both slots while an Out, Inactive or Doubtful teammate appeared only
inside the hidden remainder. That obscured the same reported absence that
already blocks qualification under the existing availability policy.

The derived display now puts those acute teammate reports first, retains the
source order among equal priorities, then other flagged reports and Active
reports. The detailed explanation uses the same ordering. Compact labels
explicitly say teammate or opponent when that relationship was retained;
legacy reports retain their existing labels and conservative teammate
interpretation. All reports remain available in the detailed panel, and the
compact card retains its omitted-report count.

Sorting copies the array and never changes the captured evidence. The model
probability, qualification rule, sample/price/source gates, forecast cutoff and
historical participation values are unchanged. A reported opponent absence
remains descriptive evidence and does not become a teammate blocker. Source
time and stale-context labels continue to apply; this display does not prove
game-day participation or add a probability adjustment.

Regression cases place an acute quarterback and running back after a chronic
teammate injury, an Out opponent and a Questionable teammate. The card shows
the two existing blockers first, the original source array remains identical,
and qualification still returns the original teammate gate with the same
probability. A separate opponent-only case retains its relationship label
without creating that gate. The complete frontend suite passes **329 tests**;
TypeScript, changed-file lint and the local production Webpack build pass.
The staged redacted secret scan found no leaks.

This is a consumer context explanation repair. It neither establishes a
betting edge nor creates a pick from missing source, price or availability
evidence. Production still requires the existing protected release gates.
