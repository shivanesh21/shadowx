"""
schemas.py — Pydantic models for artifact validation in ShadowX Factory.

Agents communicate exclusively through artifacts stored on disk and validated
against these schemas.
"""

from __future__ import annotations
import json
import re
from typing import Any, Union
from pydantic import BaseModel, Field, field_validator


class UserStory(BaseModel):
    id: str = Field(description="Story identifier, e.g. US-1")
    role: str = Field(description="User role or persona")
    action: str = Field(description="Action or capability required")
    benefit: str = Field(description="Business outcome or value")


class RequirementsArtifact(BaseModel):
    """
    Schema for docs/requirements.json produced by the Analyst.
    """
    project_name: str = Field(..., description="Project name")
    summary: str = Field(..., description="High-level product overview")
    user_stories: list[UserStory] = Field(..., min_length=1, description="List of user stories")
    functional_requirements: list[str] = Field(..., min_length=1, description="Functional requirements")
    non_functional_requirements: list[str] = Field(default_factory=list, description="NFRs (performance, security, etc.)")
    acceptance_criteria: dict[str, str] = Field(..., min_length=1, description="Numbered acceptance criteria AC-1, AC-2...")
    assumptions: list[str] = Field(default_factory=list, description="Explicit assumptions")
    out_of_scope: list[str] = Field(default_factory=list, description="Out-of-scope items")

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_ac_keys(cls, v: dict[str, str]) -> dict[str, str]:
        for key in v.keys():
            if not re.match(r"^AC-\d+$", key):
                raise ValueError(f"Acceptance criteria keys must follow pattern 'AC-1', 'AC-2', found: '{key}'")
        return v


class ModuleDesign(BaseModel):
    file_path: str = Field(..., description="Relative file path under src/")
    description: str = Field(..., description="Purpose and responsibilities")
    interfaces: list[str] = Field(default_factory=list, description="Signatures of functions and classes")


class DesignArtifact(BaseModel):
    """
    Schema for docs/design.json produced by the Architect.
    """
    project_name: str
    tech_stack: list[str]
    modules: list[ModuleDesign]
    data_models: list[str] = Field(default_factory=list)
    mermaid_diagram: str = Field(..., description="Mermaid architecture/sequence diagram")
    ac_mapping: dict[str, list[str]] = Field(..., description="Mapping of AC-x to implementing module paths")


class TestReportArtifact(BaseModel):
    """
    Schema for test_report.json produced by the Tester.
    """
    passed: int
    failed: int
    errors: int
    ac_coverage: dict[str, str] = Field(..., description="Map of AC-x to test function and status")
    failures: dict[str, str] = Field(default_factory=dict, description="Test name to failure stacktrace")


class ReviewReportArtifact(BaseModel):
    """
    Schema for review.json or summary produced by the Reviewer.
    """
    passed: bool
    traceability_matrix: dict[str, dict[str, Any]] = Field(..., description="AC to Test to Status")
    issues: list[dict[str, str]] = Field(default_factory=list)


def validate_requirements(content: Union[str, dict[str, Any]]) -> tuple[bool, str, RequirementsArtifact | None]:
    """
    Validate raw JSON string or dictionary against RequirementsArtifact schema.

    Returns: (is_valid, error_message, parsed_model_or_none)
    """
    try:
        data = json.loads(content) if isinstance(content, str) else content
        artifact = RequirementsArtifact.model_validate(data)
        return True, "", artifact
    except json.JSONDecodeError as jde:
        return False, f"Invalid JSON syntax in requirements.json: {jde}", None
    except Exception as e:
        return False, f"Requirements schema validation failed: {e}", None
