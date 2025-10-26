from backend.codex_client import CodexExecConfig, build_exec_command


def test_basic_command_structure():
    config = CodexExecConfig()
    command = build_exec_command(config)

    assert command[:4] == ("codex", "exec", "--json", "--color")
    assert "--skip-git-repo-check" in command
    assert "resume" not in command


def test_command_with_overrides_and_resume():
    config = CodexExecConfig(
        command="/usr/local/bin/codex",
        args=("foo", "--verbose"),
        workspace="/tmp/project",
        model="gpt-5-codex",
        reasoning_effort="high",
        summary_style="concise",
        approval_policy="never",
        sandbox="workspace-write",
        output_schema="schemas/result.json",
        images=("snap.png", "diagram.jpg"),
        extra_args=("--log-level", "debug"),
        extra_configs={"custom_flag": "value"},
    )

    command = build_exec_command(config, resume_session="abc-123")

    assert command[0] == "/usr/local/bin/codex"
    assert command[1:3] == ("foo", "--verbose")
    assert "--model" in command
    assert "--sandbox" in command
    assert "--output-schema" in command
    assert "--image" in command
    assert "resume" in command
    resume_index = command.index("resume")
    assert command[resume_index + 1] == "abc-123"

    # The approval policy and reasoning config should be embedded via --config.
    config_flags = [
        part for idx, part in enumerate(command)
        if part == "--config"
    ]
    assert len(config_flags) >= 2  # approval + reasoning + possible extras


def test_extra_configs_sorted_for_deterministic_output():
    config = CodexExecConfig(extra_configs={"beta": "2", "alpha": "1"})
    command = build_exec_command(config)

    configs = [
        command[i + 1]
        for i, value in enumerate(command)
        if value == "--config"
    ]

    assert configs == ['alpha="1"', 'beta="2"']

