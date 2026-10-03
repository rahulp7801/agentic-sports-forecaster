# Forecast-time team and profile presentation

The public forecast and retained pick board can attach a player-profile
snapshot refreshed after the original forecast. Several consumer headers
previously preferred that profile's current team over the roster team
captured with the forecast. A later transfer could therefore relabel an old
pick. Profile jersey, position, and portrait could also appear in a
forecast-time card despite a later profile capture.

The pick card, research preview, forecast library, and read-only slip now
display the team from observed roster evidence only when its capture precedes
the forecast. Otherwise they show the league rather than implying a team.
Profile presentation details require that same captured roster, the exact
ESPN athlete ID, the matching team, and a profile capture no later than the
forecast. The evidence panel still exposes a later profile with its explicit
capture time as presentational metadata, separate from forecast evidence.

This changes display only. It does not alter the original forecast,
availability gate, historical model, current quote, qualification threshold,
source collection, or prospective audit. Regression coverage includes a
transferred player, later profile capture, missing forecast capture, and
mismatched athlete ID. Production rendering must be checked after the
protected release can deploy.
