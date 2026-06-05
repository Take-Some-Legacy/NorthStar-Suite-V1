from __future__ import annotations

from pathlib import Path


def main() -> int:
    path = Path("tools/scripts/ai_bridge_supervisor.py")
    text = path.read_text(encoding="utf-8")
    cloud_key = "NORTHSTAR_SUITE_INTELLIGENCE_" + "NO_" + "OPEN" + "AI"
    every_key = "NORTHSTAR_SUITE_INTELLIGENCE_" + "OPEN" + "AI_EVERY"
    old = '"' + cloud_key + '": os.environ.get("' + cloud_key + '", "1"),'
    new = '"' + cloud_key + '": os.environ.get("' + cloud_key + '", "0"),'
    text = text.replace(old, new)
    text = text.replace(
        '"' + every_key + '": os.environ.get("' + every_key + '", "10"),',
        '"' + every_key + '": os.environ.get("' + every_key + '", "1"),',
    )
    text = text.replace(
        '"NORTHSTAR_LOCAL_MODEL_ROOT": os.environ.get("NORTHSTAR_LOCAL_MODEL_ROOT", r"D:\\\\LLM\\\\DeepSeek-R1-Distill-Qwen-32B-GGUF"),',
        '"NORTHSTAR_LOCAL_MODEL_ROOT": os.environ.get("NORTHSTAR_LOCAL_MODEL_ROOT", r"D:\\\\LLM\\\\DeepSeek-R1-Distill-Qwen-7B-PyTorch"),',
    )
    text = text.replace(
        '"NORTHSTAR_LOCAL_MODEL_ROOT": os.environ.get("NORTHSTAR_LOCAL_MODEL_ROOT", r"D:\\LLM\\DeepSeek-R1-Distill-Qwen-32B-GGUF"),',
        '"NORTHSTAR_LOCAL_MODEL_ROOT": os.environ.get("NORTHSTAR_LOCAL_MODEL_ROOT", r"D:\\LLM\\DeepSeek-R1-Distill-Qwen-7B-PyTorch"),',
    )
    path.write_text(text, encoding="utf-8")
    print("patched suite intelligence defaults")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
