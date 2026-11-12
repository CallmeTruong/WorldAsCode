"""Application configuration: portable paths, provider/model routing and profiles.

Editable settings live in worldascode.toml; credentials stay in environment
variables. Relative TOML paths are resolved from that file, never a repo parent.
"""

import json
import os
import tomllib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

RESOURCE_ROOT = Path(__file__).resolve().parent / "resources"
ROOT = RESOURCE_ROOT  # Readonly alias retained for archived fixtures.
ROLES = {"default", "observer", "style", "author", "critic", "kit_developer", "planner"}
SECTIONS = {"paths", "llm", "models", "model_providers", "budgets", "capture"}


def configuration(environment=None):
    env = os.environ if environment is None else environment
    path = (
        Path(env.get("WORLDASCODE_CONFIG", str(Path.cwd() / "worldascode.toml")))
        .expanduser()
        .resolve()
    )
    if not path.is_file():
        if env.get("WORLDASCODE_CONFIG"):
            raise ValueError(f"CONFIG_NOT_FOUND: {path}")
        return {}, path.parent
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"CONFIG_INVALID: {path}: {error}") from error
    checks = [
        (data, SECTIONS, "root"),
        (data.get("paths", {}), {"data_dir", "node_modules"}, "paths"),
        (
            data.get("llm", {}),
            {"default_provider", "timeout_seconds", "providers"},
            "llm",
        ),
        (data.get("models", {}), ROLES, "models"),
        (data.get("model_providers", {}), ROLES - {"default"}, "model_providers"),
        (
            data.get("budgets", {}),
            {"max_tokens", "max_revisions", "max_kit_cycles"},
            "budgets",
        ),
    ]
    for values, allowed, section in checks:
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError(f"CONFIG_UNKNOWN_KEY_OR_SECTION: {section}")
    for section in ("paths", "models", "model_providers"):
        if any(not isinstance(value, str) for value in data.get(section, {}).values()):
            raise ValueError(f"CONFIG_EXPECTED_STRING: {section}")
    for name, value in data.get("budgets", {}).items():
        minimum = 1 if name == "max_tokens" else 0
        if type(value) is not int or value < minimum:
            raise ValueError(f"CONFIG_INVALID_BUDGET: {name}")
    llm = data.get("llm", {})
    providers = llm.get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("CONFIG_INVALID_PROVIDERS")
    default = llm.get("default_provider", "primary")
    if not isinstance(default, str) or (
        ("default_provider" in llm or providers) and default not in providers
    ):
        raise ValueError("CONFIG_UNKNOWN_DEFAULT_PROVIDER")
    for name, provider in providers.items():
        if not isinstance(provider, dict) or set(provider) - {
            "base_url",
            "api_key_env",
            "input_rate",
            "output_rate",
        }:
            raise ValueError(f"CONFIG_INVALID_PROVIDER: {name}")
        if any(
            not isinstance(provider.get(key, ""), str)
            for key in ("base_url", "api_key_env")
        ):
            raise ValueError(f"CONFIG_INVALID_PROVIDER_STRING: {name}")
        for key in ("input_rate", "output_rate"):
            if key in provider and (
                type(provider[key]) not in (float, int) or provider[key] < 0
            ):
                raise ValueError(f"CONFIG_INVALID_RATE: {name}.{key}")
    if any(name not in providers for name in data.get("model_providers", {}).values()):
        raise ValueError("CONFIG_UNKNOWN_ROLE_PROVIDER")
    capture = data.get("capture", {})
    if not isinstance(capture, dict) or set(capture) - set(
        CaptureProfile.__dataclass_fields__
    ):
        raise ValueError("CONFIG_INVALID_CAPTURE")
    defaults = CaptureProfile()
    for name, value in capture.items():
        expected = getattr(defaults, name)
        if isinstance(expected, str):
            valid = isinstance(value, str) and bool(value)
        elif type(expected) is int:
            valid = type(value) is int and value > 0
        else:
            valid = type(value) in (int, float)
        if not valid or (
            name in {"ready_timeout_s", "poll_interval_ms"} and value <= 0
        ):
            raise ValueError(f"CONFIG_INVALID_CAPTURE_VALUE: {name}")
    return data, path.parent


@dataclass(frozen=True)
class WorkspacePaths:
    data_dir: Path
    node_modules: Path
    resource_dir: Path = RESOURCE_ROOT

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None):
        env = os.environ if environment is None else environment
        document, base = configuration(env)
        section = document.get("paths", {})

        def resolve(key, variable, default):
            value = Path(env.get(variable, section.get(key, default))).expanduser()
            # Environment paths follow cwd; TOML paths follow the config file.
            anchor = Path.cwd() if variable in env else base
            return (anchor / value).resolve()

        return cls(
            resolve("data_dir", "WORLDASCODE_DATA_DIR", ".worldascode"),
            resolve("node_modules", "WORLDASCODE_NODE_MODULES", "node_modules"),
        )

    @property
    def cache_dir(self):
        return self.data_dir / "cache"

    @property
    def runs_dir(self):
        return self.data_dir / "runs"

    @property
    def library_dir(self):
        return self.data_dir / "kit-library"

    @property
    def runtime_dir(self):
        return self.resource_dir / "runtime"


def paths():
    return WorkspacePaths.from_environment()


def node_role(node):
    if "critic" in node or "review" in node:
        return "critic"
    if "kit-developer" in node:
        return "kit_developer"
    if "kit-gap" in node:
        return "planner"
    if "observer" in node or node == "program-detail":
        return "observer"
    if "style" in node:
        return "style"
    return "author"


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str = field(repr=False)
    model: str = "gpt-6-sol"
    input_rate: float | None = None
    output_rate: float | None = None
    role_models: dict = field(default_factory=dict)
    providers: dict = field(default_factory=dict, repr=False)
    role_providers: dict = field(default_factory=dict)
    timeout_seconds: float = 240

    @classmethod
    def load(cls):
        document, base = configuration()
        load_dotenv(
            Path(os.getenv("WORLDASCODE_ENV_FILE", str(base / ".env"))), override=False
        )
        llm, models = document.get("llm", {}), document.get("models", {})
        providers = llm.get("providers", {})
        provider = providers.get(llm.get("default_provider", "primary"), {})
        for entry in providers.values():
            if not isinstance(entry, dict) or set(entry) - {
                "base_url",
                "api_key_env",
                "input_rate",
                "output_rate",
            }:
                raise ValueError("CONFIG_INVALID_PROVIDER")
        rate_in = os.getenv(
            "WORKFLOW_INPUT_USD_PER_MILLION", provider.get("input_rate")
        )
        rate_out = os.getenv(
            "WORKFLOW_OUTPUT_USD_PER_MILLION", provider.get("output_rate")
        )
        timeout = llm.get("timeout_seconds", 240)
        if not isinstance(timeout, (float, int)) or timeout <= 0:
            raise ValueError("CONFIG_INVALID_TIMEOUT")
        return cls(
            os.getenv("OPENAI_BASE_URL", provider.get("base_url", "")).rstrip("/"),
            os.getenv(provider.get("api_key_env", "OPENAI_API_KEY"), ""),
            os.getenv(
                "WORLDASCODE_MODEL",
                os.getenv("WORLD_SCALE_MODEL", models.get("default", "gpt-6-sol")),
            ),
            float(rate_in) if rate_in is not None else None,
            float(rate_out) if rate_out is not None else None,
            models,
            providers,
            document.get("model_providers", {}),
            timeout,
        )

    def for_node(self, node):
        role = node_role(node)
        settings = replace(self, model=self.role_models.get(role) or self.model)
        provider_name = self.role_providers.get(role)
        if provider_name:
            if provider_name not in self.providers:
                raise ValueError(f"CONFIG_UNKNOWN_PROVIDER: {provider_name}")
            provider = self.providers[provider_name]
            settings = replace(
                settings,
                base_url=provider.get("base_url", "").rstrip("/"),
                api_key=os.getenv(provider.get("api_key_env", "OPENAI_API_KEY"), ""),
                input_rate=provider.get("input_rate"),
                output_rate=provider.get("output_rate"),
            )
        return settings


@dataclass(frozen=True)
class QualityPolicy:
    version: str = "building-quality-1"
    minimum_oblique_iou: float = 0.70
    minimum_plan_iou: float = 0.75
    minimum_height_ratio: float = 0.8
    maximum_height_ratio: float = 1.3
    maximum_triangles: int = 200_000
    minimum_likeness: float = 0.7
    minimum_style: float = 0.65
    minimum_detail: float = 0.65


DEFAULT_QUALITY = QualityPolicy()
LIMITS = {
    "mean_oblique_iou": DEFAULT_QUALITY.minimum_oblique_iou,
    "plan_iou": DEFAULT_QUALITY.minimum_plan_iou,
    "height_ratio": (
        DEFAULT_QUALITY.minimum_height_ratio,
        DEFAULT_QUALITY.maximum_height_ratio,
    ),
    "max_triangles": DEFAULT_QUALITY.maximum_triangles,
}
ACCEPT = {
    "likeness": DEFAULT_QUALITY.minimum_likeness,
    "style": DEFAULT_QUALITY.minimum_style,
    "detail": DEFAULT_QUALITY.minimum_detail,
}


@dataclass(frozen=True)
class CaptureProfile:
    version: str = "photogrammetry-capture-1"
    viewer_url: str = "http://127.0.0.1:8767/"
    width: int = 1440
    height: int = 1080
    footprint_buffer_m: float = 1.0
    ground_sample_buffer_m: float = 9.0
    minimum_camera_range_m: float = 90.0
    horizontal_range_factor: float = 1.35
    vertical_range_factor: float = 2.3
    target_height_fraction: float = 0.48
    oblique_pitch_deg: float = -25.0
    overhead_pitch_deg: float = -89.8
    ready_timeout_s: float = 120.0
    stable_samples: int = 3
    poll_interval_ms: int = 350
    solar_noon_date: str = "2026-06-21"
    ground_estimator: str = "lowest-two-mean-v1"

    @classmethod
    def load(cls):
        data = configuration()[0].get("capture", {})
        if set(data) - set(cls.__dataclass_fields__):
            raise ValueError("CONFIG_UNKNOWN_CAPTURE_KEY")
        return cls(**data)

    def manifest(self):
        return asdict(self)


@dataclass(frozen=True)
class PublicationProfile:
    auto_publish: bool = False
    grant: str | None = field(default=None, repr=False)

    @classmethod
    def load(cls, library_dir=None):
        path = (library_dir or paths().library_dir) / "workflow-profile.json"
        return (
            cls(**json.loads(path.read_text(encoding="utf-8")))
            if path.exists()
            else cls()
        )

    def options(self, enabled=None, grant=None):
        return {
            "publish_kit": self.auto_publish if enabled is None else enabled,
            "kit_grant": grant or self.grant,
        }
