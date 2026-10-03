from pathlib import Path

import pytest
import yaml


WORKFLOWS = Path(__file__).resolve().parents[1] / '.github' / 'workflows'


@pytest.mark.parametrize('name', ['data.yml', 'public-data.yml'])
def test_scheduled_raw_evidence_stays_on_the_runner_without_remote_backup(name):
    source = (WORKFLOWS / name).read_text(encoding='utf8')
    document = yaml.load(source, Loader=yaml.BaseLoader)
    steps = document['jobs']['update']['steps']
    assert not any('actions/upload-artifact' in step.get('uses', '') for step in steps)
    assert 'artifact_storage_gate.py' not in source
    assert 'retain_evidence' not in document['on']['workflow_dispatch'].get('inputs', {})
    scan = next(step for step in steps if step.get('name') == 'Scan public evidence')
    assert 'gitleaks dir "$RUNNER_TEMP/public-evidence"' in scan['run']
    assert '--redact=100' in scan['run']
    summary = next(step for step in steps if step.get('name') == 'Report local-only raw evidence')
    assert steps.index(scan) < steps.index(summary)
    assert 'ephemeral' in summary['run']
    assert 'No durable raw backup' in summary['run']
    assert '$GITHUB_STEP_SUMMARY' in summary['run']
    assert 'secrets.' not in str(summary)


def test_no_workflow_reintroduces_a_raw_artifact_uploader():
    for path in WORKFLOWS.glob('*.yml'):
        document = yaml.load(path.read_text(encoding='utf8'), Loader=yaml.BaseLoader)
        for job in document['jobs'].values():
            for step in job.get('steps', []):
                assert 'actions/upload-artifact' not in step.get('uses', ''), path.name
                assert 'gh release upload' not in step.get('run', ''), path.name
