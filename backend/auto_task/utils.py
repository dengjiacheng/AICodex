import json
from pathlib import Path
from typing import Any, Dict


def render_prompt(template: str, context: Dict[str, Any]) -> str:
    result = template
    for key, value in context.items():
        placeholder = f"{{{{{key}}}}}"
        if isinstance(value, (dict, list)):
            replacement = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            replacement = str(value)
        result = result.replace(placeholder, replacement)
    return result


def load_prompt_template(base_dir: Path, name: str) -> str:
    path = base_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")
