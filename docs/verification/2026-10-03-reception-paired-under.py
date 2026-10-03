"""Descriptive paired game bootstrap for the published fixed NFL reception test.

This report never estimates sportsbook returns or tunes a forecast rule.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from random import Random

DATA = Path(__file__).resolve().parents[2] / "frontend" / "data"
COHORTS = {
    "2025_weeks_1_2": (
        "nfl-week1-2025-receptions.json",
        "nfl-week2-2025-receptions.json",
    ),
    "2026_week_1": ("nfl-week1-2026.json",),
}
EXPECTED = {
    "2025_weeks_1_2": (26, 213, 180, 181),
    "2026_week_1": (15, 122, 100, 94),
}
RESAMPLES = 50_000
SEED = 20261003


def cohort(name: str, files: tuple[str, ...]) -> dict:
    games: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    over_calls: list[dict] = []
    for filename in files:
        bundle = json.loads((DATA / filename).read_text(encoding="utf-8"))
        for row in bundle["records"]:
            probability = row["model_probability"]
            if row["prop_type"] != "receptions" or abs(probability - 0.5) < 0.1 - 1e-15:
                continue
            if row["research_threshold"] != 4.5 or type(row["outcome"]) is not bool:
                raise ValueError("Published fixed-threshold row is invalid")
            if probability >= 0.5:
                over_calls.append(row)
            result = games[row["event_id"]]
            result[0] += (probability >= 0.5) == row["outcome"]
            result[1] += row["outcome"] is False
            result[2] += 1
    values = list(games.values())
    game_count, sample, model, under = (
        len(values),
        sum(value[2] for value in values),
        sum(value[0] for value in values),
        sum(value[1] for value in values),
    )
    if (game_count, sample, model, under) != EXPECTED[name]:
        raise ValueError("Published benchmark denominator changed")
    rng = Random(SEED)
    paired = []
    for _ in range(RESAMPLES):
        draw = [values[rng.randrange(game_count)] for _ in range(game_count)]
        paired.append(sum(value[0] - value[1] for value in draw) / sum(value[2] for value in draw))
    paired.sort()
    return {
        "cohort": name,
        "games": game_count,
        "selected_rows": sample,
        "model_correct": model,
        "over_calls": len(over_calls),
        "over_correct": sum(row["outcome"] for row in over_calls),
        "over_games": len({row["event_id"] for row in over_calls}),
        "always_under_correct": under,
        "model_minus_under_percentage_points": 100 * (model - under) / sample,
        "games_model_better": sum(value[0] > value[1] for value in values),
        "games_tied": sum(value[0] == value[1] for value in values),
        "games_model_worse": sum(value[0] < value[1] for value in values),
        "paired_game_bootstrap_95_percentage_points": [
            100 * paired[int(0.025 * RESAMPLES)],
            100 * paired[int(0.975 * RESAMPLES) - 1],
        ],
    }


if __name__ == "__main__":
    print(json.dumps(
        [cohort(name, files) for name, files in COHORTS.items()],
        indent=2,
        sort_keys=True,
    ))

