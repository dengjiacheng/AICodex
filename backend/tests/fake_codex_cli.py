#!/usr/bin/env python3
"""
Lightweight stand-in for `codex exec --json` used in tests.

The script accepts arbitrary arguments, reads the prompt from stdin,
emits a sequence of JSONL events and optional stderr output, then exits.
"""

import json
import sys
import time


def main() -> int:
    # Consume stdin to simulate prompt reception.
    prompt = sys.stdin.read().strip()

    # Echo a runner-style stdout line that isn't JSON.
    print("non-json banner: {}".format(prompt))
    sys.stdout.flush()

    events = [
        {"type": "thread.started", "thread_id": "fake-thread-1"},
        {"type": "turn.started"},
        {
            "type": "item.started",
            "item": {"id": "item-1", "type": "command_execution", "status": "in_progress"},
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item-1",
                "type": "command_execution",
                "command": "echo hello",
                "aggregated_output": "hello\n",
                "exit_code": 0,
                "status": "completed",
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 2,
                "output_tokens": 5,
                "reasoning_output_tokens": 1,
                "total_tokens": 15,
            },
        },
    ]

    for event in events:
        print(json.dumps(event, ensure_ascii=False))
        sys.stdout.flush()
        time.sleep(0.01)  # make async reading deterministic

    if "--fail" in sys.argv:
        print(json.dumps({"type": "turn.failed", "error": {"message": "forced failure"}}))
        sys.stdout.flush()
        print("forced failure", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
