from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
SKILL_COMMIT = "0c0c49bc168e648dbaf9c8c080474de0b3a941b6"
PROMPT_VERSION = "building-v1"


@dataclass
class Settings:
    base_url: str
    api_key: str
    model: str
    vision_model: str
    code_model: str
    review_model: str
    input_rate: float | None = None
    output_rate: float | None = None

    @classmethod
    def load(cls):
        load_dotenv(ROOT.parent / ".env", override=False)
        load_dotenv(ROOT / ".env", override=False)
        # CASEPILOT uses a router prefix; this gateway advertises bare IDs.
        model = os.getenv("WORKFLOW_MODEL", os.getenv("CASEPILOT_MODEL", "gpt-6-sol"))
        model = model.removeprefix("openai/")
        rates = [os.getenv("WORKFLOW_INPUT_USD_PER_MILLION"), os.getenv("WORKFLOW_OUTPUT_USD_PER_MILLION")]
        return cls(os.getenv("OPENAI_BASE_URL", "").rstrip("/"), os.getenv("OPENAI_API_KEY", ""),
                   model, os.getenv("WORKFLOW_VISION_MODEL", model), os.getenv("WORKFLOW_CODE_MODEL", model),
                   os.getenv("WORKFLOW_REVIEW_MODEL", model), *[float(v) if v else None for v in rates])

    def public(self):
        return {k: v for k, v in vars(self).items() if k != "api_key"}
