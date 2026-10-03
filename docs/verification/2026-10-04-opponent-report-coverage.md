# Opponent injury-report coverage in consumer evidence

The captured availability envelope can be partial: the subject's current
roster/injury report is verified while the opposing team's report is unavailable.
The player may pass the existing subject/teammate gates in that state. Previously,
both consumer views could say that no opposing defender risk was found when no
opponent report had actually been checked.

Future availability evidence now carries the exact opposing abbreviation and
an observed or unavailable injury-coverage status when the two-team capture
establishes one. The public projection validates the paired fields. Older
forecasts with no retained opponent status are explicitly described as unknown;
they cannot acquire a clean opponent report retrospectively. The detailed
panel and compact pick context distinguish complete coverage from an unavailable
opponent report. A provider injury report still does not prove a final game-day
lineup.

This is an evidence/presentation repair. It does not adjust the baseline
probability, injury eligibility, quote identity or freshness, confidence floor,
portfolio limits, model version, collection frequency, or frozen prospective
evaluation. No API call or credit was used for this repair.

Local verification: 2,028 backend tests passed, 72 skipped (including optional
disposable PostgreSQL tests); 296 frontend tests passed; TypeScript, changed-file
ESLint, and the production Next.js build passed. Focused availability and
scheduled-scan tests passed 128. Protected CI/deployment and a new live
two-team capture remain required before this is visible on the consumer site.
