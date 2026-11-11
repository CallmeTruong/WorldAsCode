from typing import Literal
from pydantic import BaseModel, Field, AliasChoices, model_validator


class Feature(BaseModel):
    id: str
    description: str
    evidence: Literal["observed", "inferred", "unknown"]
    confidence: float = Field(ge=0, le=1)
    source: str = Field(validation_alias=AliasChoices("source", "source_region", "source region", "sourceRegion"))
    parent: str | None = None


class BuildingSpec(BaseModel):
    name: str
    suitability: Literal["usable", "insufficient_evidence"]
    observed_floors: int | None = Field(default=None, ge=1, le=150)
    components: list[Feature] = Field(min_length=3, max_length=80)
    repetitions: list[dict] = Field(default_factory=list)
    materials: list[dict] = Field(min_length=1)
    proportions: dict
    camera: dict
    uncertainty: list[str] = Field(min_length=1)
    quality_contract: list[str] = Field(min_length=3)

    @model_validator(mode="after")
    def unique_features(self):
        ids = [c.id for c in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate component ids")
        if any(c.parent is not None and c.parent not in ids for c in self.components):
            raise ValueError("unknown component parent")
        return self


SCORE_KEYS = ("mass", "facade", "roof", "details", "materials", "proportions")


class Review(BaseModel):
    scores: dict[str, float]
    critical_defects: list[str]
    defects: list[dict]
    matched_features: list[str]
    inferred_regions: list[str]
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def score_contract(self):
        if set(self.scores) != set(SCORE_KEYS) or any(not 0 <= s <= 1 for s in self.scores.values()):
            raise ValueError("six bounded feature scores required")
        return self

    @property
    def quality(self):
        return sum(self.scores.values()) / len(SCORE_KEYS)


def prefer(candidate: dict, incumbent: dict | None) -> bool:
    if not candidate.get("geometry_passed") or not candidate.get("review"):
        return False
    review = Review.model_validate(candidate["review"])
    if incumbent is None:
        return True
    prior = Review.model_validate(incumbent["review"])
    if len(review.critical_defects) > len(prior.critical_defects):
        return False
    if len(review.critical_defects) < len(prior.critical_defects):
        return True
    # Retain meaningful gains only, with no feature dropping >0.08.
    return review.quality > prior.quality + 0.005 and all(
        review.scores[k] >= prior.scores[k] - 0.08 for k in SCORE_KEYS)
