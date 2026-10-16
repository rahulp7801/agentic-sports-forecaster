"""Keep the credentialed readiness probe manual, bounded and separate from collection."""
from pathlib import Path
import re


def test_readiness_workflow_cannot_schedule_or_activate_collection():
    workflow = (Path(__file__).parents[1] / '.github/workflows/provider-readiness.yml').read_text()
    assert '  workflow_dispatch:' in workflow
    assert not re.search(r'^  (schedule|push|pull_request|workflow_call):', workflow, re.MULTILINE)
    assert "github.ref == 'refs/heads/master'" in workflow
    assert "github.repository == 'rahulp7801/agentic-sports-forecaster'" in workflow
    assert 'environment: production' in workflow
    assert 'contents: read' in workflow and 'write' not in workflow
    assert 'runs-on: ubuntu-latest' in workflow and 'timeout-minutes: 5' in workflow
    assert 'group: market-data' in workflow and 'cancel-in-progress: false' in workflow
    assert 'persist-credentials: false' in workflow
    assert all(len(action) == 40 for action in re.findall(r'uses: [^@\s]+@(\S+)', workflow))
    assert re.findall(r'secrets\.(\w+)', workflow) == ['DATABASE_URL', 'ODDS_API_KEY']
    assert 'ANALYTICS_DATABASE_URL: ${{ secrets.DATABASE_URL }}' in workflow
    assert 'sportsbet.provider_readiness --daily-credit-limit "$DAILY_CREDIT_LIMIT"' in workflow
    assert not re.search(r'upload-artifact|gh |curl |sportsbet\.(daily|scan|refresh|market_watch)|DATA_PIPELINE_ENABLED|VERCEL_TOKEN|DATABASE_MIGRATION_URL', workflow)
