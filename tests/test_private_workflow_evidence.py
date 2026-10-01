from pathlib import Path

import yaml


def test_daily_edge_evaluation_does_not_publish_private_reports():
    workflow = yaml.safe_load(Path('.github/workflows/data.yml').read_text(encoding='utf8'))
    steps = workflow['jobs']['update']['steps']
    edge = next(step for step in steps if step.get('name') == 'Evaluate prospective NFL market edge privately')
    assert 'sportsbet.quant.priced_market_audit' in edge['run']
    assert 'assess_prospective_edge' in edge['run']
    assert 'GITHUB_STEP_SUMMARY' not in edge['run']
    assert 'upload-artifact' not in edge['run']
    uploads = [step for step in steps if 'upload-artifact' in step.get('uses', '')]
    assert uploads
    assert all(step['with']['path'].endswith('/public-evidence/') for step in uploads)
    assert 'edge-checkpoint' not in Path('.github/workflows/data.yml').read_text(encoding='utf8')
