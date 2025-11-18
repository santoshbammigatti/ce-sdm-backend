import json
from pathlib import Path
from typing import Dict, Any

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

def append_jsonl(path_name: str, record: Dict[str, Any]) -> None:
    file_path = OUTPUT_DIR / path_name
    with file_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def truncate_output_files(files=("approved_summaries.jsonl", "crm_notes.jsonl")) -> None:
    for name in files:
        file_path = OUTPUT_DIR / name
        # Create file if it doesn't exist; truncate if it does
        with file_path.open("w", encoding="utf-8") as f:
            f.write("")
