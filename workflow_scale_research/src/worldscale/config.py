import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str = "gpt-6-sol"
    input_rate: float | None = None
    output_rate: float | None = None

    @classmethod
    def load(cls):
        load_dotenv(ROOT.parent / ".env", override=False)
        load_dotenv(ROOT / ".env", override=False)
        rates = [
            os.getenv("WORKFLOW_INPUT_USD_PER_MILLION"),
            os.getenv("WORKFLOW_OUTPUT_USD_PER_MILLION"),
        ]
        return cls(
            os.getenv("OPENAI_BASE_URL", "").rstrip("/"),
            os.getenv("OPENAI_API_KEY", ""),
            os.getenv("WORLD_SCALE_MODEL", "gpt-6-sol"),
            *[float(r) if r else None for r in rates],
        )
