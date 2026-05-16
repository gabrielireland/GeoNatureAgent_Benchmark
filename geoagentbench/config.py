"""Experiment YAML configuration loader with validation."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

VALID_ARCHITECTURES = {"single_agent", "multi_agent_planner_worker"}
VALID_PROMPT_STRATEGIES = {"zero_shot", "chain_of_thought", "few_shot"}
VALID_PROMPT_VERSIONS = {"v1", "v2", "v3"}
VALID_ENABLED_VALUES = {"true", "false", "stop"}


@dataclass
class ExperimentConfig:
    """Parsed experiment configuration."""

    experiment_id: str
    description: str = ""

    # Lifecycle — "true" (run), "false" (skip, deactivated), "stop" (skip, permanently retired)
    enabled: str = "true"

    # Model
    model_id: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2048

    # Sampling (None = use model default)
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    seed: Optional[int] = None

    # Multi-seed: list of seeds to iterate over. [None] = single un-seeded run
    # (backward compatible). Each entry becomes config.seed at runtime.
    seeds: List[Optional[int]] = field(default_factory=lambda: [None])

    # Agent
    architecture: str = "single_agent"
    prompt_strategy: str = "zero_shot"
    prompt_version: str = "v2"
    max_turns: int = 10

    # Cases
    case_set: str = "dev"
    case_file: Optional[str] = None
    categories: Optional[List[str]] = None
    case_ids: Optional[List[str]] = None

    # Vertex AI (for LiteLLM)
    vertex_project: str = ""
    vertex_region: str = ""

    # Output
    output_prefix: str = ""
    gcs_bucket: str = ""
    log_to_bigquery: bool = False
    bigquery_dataset: str = ""
    compare_with: List[str] = field(default_factory=list)

    # Lineage
    based_on: Optional[str] = None

    # Source file path (set by load_experiment_config, not serialised)
    _source_yaml_path: Optional[str] = field(default=None, repr=False)

    @property
    def is_enabled(self) -> bool:
        """Return True only when enabled is 'true'."""
        return self.enabled.lower() == "true"

    @property
    def client_kwargs(self) -> Dict:
        """Keyword args for create_client()."""
        kwargs = {}
        if self.model_id.startswith("vertex_ai/"):
            kwargs["vertex_project"] = self.vertex_project or os.getenv("VERTEXAI_PROJECT", "")
            kwargs["vertex_region"] = self.vertex_region or os.getenv("VERTEXAI_LOCATION", "us-central1")
        elif not self.model_id.startswith("gemini/"):
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                kwargs["api_key"] = api_key
        for param in ("temperature", "top_p", "top_k", "seed"):
            val = getattr(self, param)
            if val is not None:
                kwargs[param] = val
        return kwargs

    def validate(self) -> List[str]:
        """Validate config and return list of errors (empty = valid)."""
        errors = []

        if not self.experiment_id:
            errors.append("experiment_id is required")

        if self.enabled.lower() not in VALID_ENABLED_VALUES:
            errors.append(f"enabled '{self.enabled}' not in {VALID_ENABLED_VALUES}")

        if self.architecture not in VALID_ARCHITECTURES:
            errors.append(f"architecture '{self.architecture}' not in {VALID_ARCHITECTURES}")

        if self.prompt_strategy not in VALID_PROMPT_STRATEGIES:
            errors.append(f"prompt_strategy '{self.prompt_strategy}' not in {VALID_PROMPT_STRATEGIES}")

        if self.prompt_version not in VALID_PROMPT_VERSIONS:
            errors.append(f"prompt_version '{self.prompt_version}' not in {VALID_PROMPT_VERSIONS}")

        if self.max_tokens < 1:
            errors.append(f"max_tokens must be positive, got {self.max_tokens}")

        if self.max_turns < 1:
            errors.append(f"max_turns must be positive, got {self.max_turns}")

        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            errors.append(f"temperature {self.temperature} outside [0.0, 2.0]")

        if self.top_p is not None and not (0.0 <= self.top_p <= 1.0):
            errors.append(f"top_p {self.top_p} outside [0.0, 1.0]")

        if self.top_k is not None and self.top_k < 1:
            errors.append(f"top_k must be >= 1, got {self.top_k}")

        return errors


def load_experiment_config(path: str) -> ExperimentConfig:
    """Load experiment config from YAML file."""
    import yaml

    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"Experiment config not found: {filepath}")

    with open(filepath) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML in {filepath}: expected a mapping, got {type(data).__name__}")

    model = data.get("model", {})
    agent = data.get("agent", {})
    tasks = data.get("tasks", {})
    output = data.get("output", {})
    sampling = data.get("sampling", {})
    vertex = data.get("vertex", {})

    # Resolve seed list. Precedence:
    #   1. sampling.seeds: [int, int, ...]  → explicit multi-seed
    #   2. sampling.seed: int               → single-seed (back-compat)
    #   3. neither                           → [None] (model default, single run)
    raw_seeds = sampling.get("seeds")
    raw_seed = sampling.get("seed")
    if raw_seeds is not None:
        if not isinstance(raw_seeds, list) or not raw_seeds:
            raise ValueError(
                f"sampling.seeds must be a non-empty list in {filepath}"
            )
        seeds_list: List[Optional[int]] = [
            (None if s is None else int(s)) for s in raw_seeds
        ]
        seed_default = seeds_list[0]
    elif raw_seed is not None:
        seeds_list = [int(raw_seed)]
        seed_default = int(raw_seed)
    else:
        seeds_list = [None]
        seed_default = None

    return ExperimentConfig(
        experiment_id=data.get("experiment_id", filepath.stem),
        description=data.get("description", ""),
        enabled=str(data.get("enabled", "true")).lower(),
        model_id=model.get("model_id", "claude-sonnet-4-20250514"),
        max_tokens=model.get("max_tokens", 2048),
        temperature=sampling.get("temperature"),
        top_p=sampling.get("top_p"),
        top_k=sampling.get("top_k"),
        seed=seed_default,
        seeds=seeds_list,
        architecture=agent.get("architecture", "single_agent"),
        prompt_strategy=agent.get("prompt_strategy", "zero_shot"),
        prompt_version=agent.get("prompt_version", "v2"),
        max_turns=agent.get("max_turns", 10),
        case_set=tasks.get("case_set", "dev"),
        categories=tasks.get("categories"),
        case_ids=tasks.get("ids"),
        vertex_project=vertex.get("project") or os.getenv("VERTEXAI_PROJECT", ""),
        vertex_region=vertex.get("region") or os.getenv("VERTEXAI_LOCATION", "us-central1"),
        output_prefix=os.getenv("GCS_OUTPUT_PREFIX") or output.get("prefix", ""),
        gcs_bucket=output.get("bucket") or os.getenv("GCS_BUCKET") or os.getenv("BUCKET", ""),
        log_to_bigquery=output.get("log_to_bigquery", False),
        bigquery_dataset=output.get("bigquery_dataset", ""),
        compare_with=output.get("compare_with") or [],
        based_on=data.get("based_on"),
        _source_yaml_path=str(filepath),
    )
