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
    project_name: str = Field(..., description="Project name")
    tech_stack: list[str] = Field(..., min_length=1, description="Selected technologies and libraries")
    modules: list[ModuleDesign] = Field(..., min_length=1, description="List of module designs")
    data_models: list[str] = Field(default_factory=list, description="Data models or schemas")
    mermaid_diagram: str = Field(..., description="Mermaid architecture/sequence diagram")
    ac_mapping: dict[str, list[str]] = Field(..., min_length=1, description="Mapping of AC-x to implementing module paths")

    @field_validator("ac_mapping")
    @classmethod
    def validate_ac_keys(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        for key in v.keys():
            if not re.match(r"^AC-\d+$", key):
                raise ValueError(f"AC mapping keys must follow pattern 'AC-1', 'AC-2', found: '{key}'")
        return v

    @field_validator("mermaid_diagram")
    @classmethod
    def validate_mermaid(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Mermaid diagram cannot be empty.")
        valid_prefixes = ("graph", "flowchart", "classDiagram", "sequenceDiagram", "stateDiagram", "erDiagram")
        if not any(trimmed.startswith(p) for p in valid_prefixes):
            raise ValueError(
                f"Mermaid diagram must start with a valid diagram type ({', '.join(valid_prefixes)}). Found: '{trimmed[:25]}...'"
            )
        return v


class TestReportArtifact(BaseModel):
    """
    Schema for test_report.json produced by the Tester.
    """
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    ac_coverage: dict[str, str] = Field(..., description="Map of AC-x to test function and status")
    failures: dict[str, str] = Field(default_factory=dict, description="Test name to failure stacktrace")

    @field_validator("ac_coverage")
    @classmethod
    def validate_ac_coverage_keys(cls, v: dict[str, str]) -> dict[str, str]:
        for key in v.keys():
            if not re.match(r"^AC-\d+$", key):
                raise ValueError(f"AC coverage keys must follow pattern 'AC-1', 'AC-2', found: '{key}'")
        return v


class ReviewReportArtifact(BaseModel):
    """
    Schema for review.json or summary produced by the Reviewer.
    """
    passed: bool
    traceability_matrix: dict[str, dict[str, Any]] = Field(..., description="AC to Test to Status")
    issues: list[dict[str, str]] = Field(default_factory=list)


def validate_test_report(content: Union[str, dict[str, Any]]) -> tuple[bool, str, TestReportArtifact | None]:
    """
    Validate raw JSON string or dictionary against TestReportArtifact schema.

    Returns: (is_valid, error_message, parsed_model_or_none)
    """
    try:
        data = json.loads(content) if isinstance(content, str) else content
        artifact = TestReportArtifact.model_validate(data)
        return True, "", artifact
    except json.JSONDecodeError as jde:
        return False, f"Invalid JSON syntax in test_report.json: {jde}", None
    except Exception as e:
        return False, f"Test report schema validation failed: {e}", None


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


def validate_design(content: Union[str, dict[str, Any]]) -> tuple[bool, str, DesignArtifact | None]:
    """
    Validate raw JSON string or dictionary against DesignArtifact schema.

    Returns: (is_valid, error_message, parsed_model_or_none)
    """
    try:
        data = json.loads(content) if isinstance(content, str) else content
        artifact = DesignArtifact.model_validate(data)
        return True, "", artifact
    except json.JSONDecodeError as jde:
        return False, f"Invalid JSON syntax in design.json: {jde}", None
    except Exception as e:
        return False, f"Design schema validation failed: {e}", None
