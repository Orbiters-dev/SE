import json
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

def test_read_file_contents_returns_dict():
    from run_workflow_optimizer import read_file_contents, collect_issues
    issues = collect_issues(days=7)
    contents = read_file_contents(issues)
    assert isinstance(contents, dict)
    # keys are relative path strings (e.g. "workflows/foo.md")
    for k, v in contents.items():
        assert isinstance(k, str)
        assert isinstance(v, str)

def test_read_file_contents_skips_large_files(tmp_path, monkeypatch):
    from run_workflow_optimizer import read_file_contents, Issue, MAX_FILE_BYTES
    # Create a large fake file
    big = tmp_path / "tools" / "big.py"
    big.parent.mkdir(parents=True)
    big.write_text("x" * (MAX_FILE_BYTES + 1))
    issue = Issue(type="ORPHAN_TOOL", severity="medium", source="big.py", detail="orphan")
    monkeypatch.setattr("run_workflow_optimizer.PROJECT_ROOT", tmp_path)
    contents = read_file_contents([issue])
    assert "tools/big.py" in contents
    assert "[SKIPPED" in contents["tools/big.py"]

def test_read_file_contents_cap_tool_code(tmp_path, monkeypatch):
    from run_workflow_optimizer import read_file_contents, Issue, MAX_TOOL_CODE_PROPOSALS
    # Create MAX_TOOL_CODE_PROPOSALS + 1 small .py files
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir(parents=True)
    issues = []
    for i in range(MAX_TOOL_CODE_PROPOSALS + 1):
        fname = f"tool_{i}.py"
        (tools_dir / fname).write_text("# small")
        issues.append(Issue(type="ORPHAN_TOOL", severity="medium", source=fname, detail="orphan"))
    monkeypatch.setattr("run_workflow_optimizer.PROJECT_ROOT", tmp_path)
    contents = read_file_contents(issues)
    # Exactly MAX_TOOL_CODE_PROPOSALS files should be read, 1 should be capped
    skipped = [v for v in contents.values() if "[SKIPPED" in v]
    assert len(skipped) == 1
    assert "tool_code cap" in skipped[0]


def test_generate_proposals_structure(monkeypatch):
    """Test with a mock anthropic client to avoid real API calls."""
    import unittest.mock as mock
    import run_workflow_optimizer as opt
    from run_workflow_optimizer import generate_proposals, Issue

    monkeypatch.setattr(opt, "ANTHROPIC_KEY", "fake-key")

    fake_proposals = [
        {
            "id": 1,
            "issue_type": "BROKEN_REF",
            "source": "test_workflow",
            "rationale": "foo.py is the correct name",
            "change_type": "workflow_md",
            "file": "workflows/test_workflow.md",
            "original": "`tools/bar.py`",
            "replacement": "`tools/foo.py`"
        }
    ]
    fake_response_text = json.dumps(fake_proposals)

    with mock.patch("anthropic.Anthropic") as MockClient:
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value.content = [
            mock.MagicMock(text=fake_response_text)
        ]
        issues = [Issue("BROKEN_REF", "high", "test_workflow", "references bar.py")]
        contents = {"workflows/test_workflow.md": "| `tools/bar.py` | ..."}
        proposals = generate_proposals(issues, contents, model="haiku")

    assert len(proposals) == 1
    assert proposals[0]["id"] == 1
    assert proposals[0]["change_type"] == "workflow_md"


def test_generate_proposals_invalid_json_returns_empty(monkeypatch):
    import unittest.mock as mock
    import run_workflow_optimizer as opt
    from run_workflow_optimizer import generate_proposals, Issue

    monkeypatch.setattr(opt, "ANTHROPIC_KEY", "fake-key")

    with mock.patch("anthropic.Anthropic") as MockClient:
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value.content = [
            mock.MagicMock(text="not json at all")
        ]
        issues = [Issue("BROKEN_REF", "high", "wf", "detail")]
        proposals = generate_proposals(issues, {}, model="haiku")

    assert proposals == []
