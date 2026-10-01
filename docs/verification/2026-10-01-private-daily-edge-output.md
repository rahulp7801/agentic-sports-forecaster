# Private daily NFL edge output

The daily worker still runs the unchanged `priced_market_audit` on all forecasts and original recommendations, then applies the unchanged prospective evidence assessor. The JSON is held in a temporary runner directory and removed when the step ends. The public Actions log prints only a generic completion status. Detailed model-versus-market metrics, individual forecasts, selections and reports are no longer copied to a GitHub Actions artifact or step summary. Public market evidence remains a separate sanitized artifact.

The frozen receiving-pick audit continues to retain its full report privately in `analytics.prospective_audit_reports`. The older priced-market audit remains available for an authorized private read-only analysis; this change does not alter its model, qualification, cohort, provider calls, credit limits, reserve, or betting behavior. A generic workflow success is not evidence of edge or a 75% win rate.
