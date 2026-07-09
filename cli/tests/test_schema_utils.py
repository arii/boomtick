import click
import pytest
from dev_tools.schema_utils import collect_commands, get_command_by_path

@click.group()
def mock_root_cli():
    pass

@mock_root_cli.command(name="test")
@click.option("--flag", help="A test flag")
@click.argument("arg")
def mock_test_cmd(flag, arg):
    pass

@mock_root_cli.group()
def sub():
    pass

@sub.command(name="nested")
def mock_nested_cmd():
    pass

def test_get_command_by_path():
    assert get_command_by_path(mock_root_cli, "test") == mock_test_cmd
    assert get_command_by_path(mock_root_cli, "sub") == sub
    assert get_command_by_path(mock_root_cli, "sub nested") == mock_nested_cmd
    assert get_command_by_path(mock_root_cli, "invalid") is None
    assert get_command_by_path(mock_root_cli, "") == mock_root_cli

def test_collect_commands_flat():
    schema = collect_commands(mock_test_cmd, prefix="test")
    assert "test" in schema
    cmd = schema["test"]
    assert cmd["exact_usage"].startswith("td-cli test")
    assert any(f["flag"] == "--flag" for f in cmd["optional_flags"])
    assert any(a["name"] == "arg" for a in cmd["required_arguments"])

def test_collect_commands_group():
    schema = collect_commands(mock_root_cli)
    assert "test" in schema
    assert "sub nested" in schema
    assert "sub" not in schema # It should collect leaf commands

def test_max_depth():
    # Test max_depth by limiting it to 0
    schema = collect_commands(mock_root_cli, max_depth=0)
    assert schema == {}

    # Test depth 1 (should get 'test' but not 'sub nested' if 'sub' was a command, but here 'sub' is a group)
    schema = collect_commands(mock_root_cli, max_depth=1)
    assert "test" in schema
    assert "sub nested" not in schema

def test_schema_command_integration():
    from click.testing import CliRunner
    from dev_tools.cli import cli

    runner = CliRunner()
    # Test valid path
    result = runner.invoke(cli, ["schema", "config view"])
    assert result.exit_code == 0
    assert '"status": "success"' in result.output
    assert "config view" in result.output

    # Test invalid path
    result = runner.invoke(cli, ["schema", "nonexistent"])
    assert result.exit_code == 1
    assert "Command path not found" in result.output

    # Test path that is a group (should succeed and return all subcommands)
    result = runner.invoke(cli, ["schema", "config"])
    assert result.exit_code == 0
    assert "config view" in result.output

    # Test injection attempt (semicolon)
    result = runner.invoke(cli, ["schema", "gh; rm -rf /"])
    assert result.exit_code == 1
    assert "Invalid command path" in result.output

    # Test injection attempt (double space)
    result = runner.invoke(cli, ["schema", "gh  view"])
    assert result.exit_code == 1
    assert "Invalid command path" in result.output
