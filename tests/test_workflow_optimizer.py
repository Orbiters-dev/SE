import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

def test_import():
    import run_workflow_optimizer  # must not crash
    assert hasattr(run_workflow_optimizer, "collect_issues")

def test_collect_issues_returns_list():
    from run_workflow_optimizer import collect_issues
    issues = collect_issues(days=7)
    assert isinstance(issues, list)
    # each item has .type, .severity, .source, .detail
    for issue in issues:
        assert hasattr(issue, "type")
        assert hasattr(issue, "severity")
        assert hasattr(issue, "source")
        assert hasattr(issue, "detail")
