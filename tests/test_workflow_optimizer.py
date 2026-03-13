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
