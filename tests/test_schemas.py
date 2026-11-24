"""
test_schemas.py — Unit tests for Pydantic artifact schemas.
"""

import pytest
from pipeline.schemas import (
    RequirementsArtifact,
    DesignArtifact,
    UserStory,
    validate_requirements,
    validate_design,
)


def test_valid_requirements_artifact():
    data = {
        "project_name": "CLI Todo App",
        "summary": "A fast command line todo manager with tags and priorities.",
        "user_stories": [
            {
                "id": "US-1",
                "role": "Developer",
                "action": "Add tasks with a due date",
                "benefit": "Track deadlines easily",
            }
        ],
        "functional_requirements": [
            "Support add, list, and complete commands",
            "Store items in SQLite",
        ],
        "non_functional_requirements": [
            "Sub-100ms startup latency",
        ],
        "acceptance_criteria": {
            "AC-1": "Running 'todo add Buy milk' stores task with status pending",
            "AC-2": "Running 'todo list' prints all active items",
        },
        "assumptions": [
            "Single user local SQLite database",
        ],
        "out_of_scope": [
            "Cloud synchronization",
        ],
    }

    is_valid, err, model = validate_requirements(data)
    assert is_valid is True
    assert err == ""
    assert model is not None
    assert model.project_name == "CLI Todo App"
    assert len(model.user_stories) == 1
    assert "AC-1" in model.acceptance_criteria


def test_requirements_invalid_ac_keys():
    data = {
        "project_name": "App",
        "summary": "Test app",
        "user_stories": [{"id": "US-1", "role": "User", "action": "run", "benefit": "win"}],
        "functional_requirements": ["Must work"],
        "acceptance_criteria": {
            "criterion_1": "Invalid criterion key format",
        },
    }

    is_valid, err, model = validate_requirements(data)
    assert is_valid is False
    assert model is None
    assert "Acceptance criteria keys must follow pattern 'AC-1'" in err


def test_requirements_missing_mandatory_fields():
    data = {
        "project_name": "App",
        # missing summary, user_stories, functional_requirements, acceptance_criteria
    }

    is_valid, err, model = validate_requirements(data)
    assert is_valid is False
    assert "validation failed" in err


def test_validate_requirements_invalid_json_string():
    is_valid, err, model = validate_requirements("not a json string {{{")
    assert is_valid is False
    assert "Invalid JSON syntax" in err


# ---------------------------------------------------------------------------
# Design Schema Tests
# ---------------------------------------------------------------------------

def test_valid_design_artifact():
    data = {
        "project_name": "Calculator Library",
        "tech_stack": ["Python 3.10+"],
        "modules": [
            {
                "file_path": "src/calc.py",
                "description": "Core calculation logic",
                "interfaces": ["def add(a: float, b: float) -> float"],
            }
        ],
        "data_models": [],
        "mermaid_diagram": "flowchart TD\n  User --> Calc[Calculator Module]",
        "ac_mapping": {
            "AC-1": ["src/calc.py"],
        },
    }

    is_valid, err, model = validate_design(data)
    assert is_valid is True
    assert err == ""
    assert model is not None
    assert model.project_name == "Calculator Library"
    assert "AC-1" in model.ac_mapping


def test_design_invalid_mermaid_syntax():
    data = {
        "project_name": "Calculator",
        "tech_stack": ["Python"],
        "modules": [{"file_path": "src/calc.py", "description": "calc", "interfaces": []}],
        "mermaid_diagram": "this is not a valid diagram header",
        "ac_mapping": {"AC-1": ["src/calc.py"]},
    }

    is_valid, err, model = validate_design(data)
    assert is_valid is False
    assert "Mermaid diagram must start with a valid diagram type" in err


def test_design_empty_mermaid():
    data = {
        "project_name": "Calculator",
        "tech_stack": ["Python"],
        "modules": [{"file_path": "src/calc.py", "description": "calc", "interfaces": []}],
        "mermaid_diagram": "   ",
        "ac_mapping": {"AC-1": ["src/calc.py"]},
    }

    is_valid, err, model = validate_design(data)
    assert is_valid is False
    assert "Mermaid diagram cannot be empty" in err


def test_design_invalid_ac_mapping_keys():
    data = {
        "project_name": "Calculator",
        "tech_stack": ["Python"],
        "modules": [{"file_path": "src/calc.py", "description": "calc", "interfaces": []}],
        "mermaid_diagram": "flowchart TD\n  A --> B",
        "ac_mapping": {"bad_key": ["src/calc.py"]},
    }

    is_valid, err, model = validate_design(data)
    assert is_valid is False
    assert "AC mapping keys must follow pattern 'AC-1'" in err
