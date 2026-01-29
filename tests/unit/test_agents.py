"""
Unit tests for the agents module.
"""


class TestAgentsImport:
    """Tests for agents module imports."""

    def test_analyst_importable(self) -> None:
        """Should be able to import analyst module."""
        from src.agents import analyst

        assert analyst is not None

    def test_critic_importable(self) -> None:
        """Should be able to import critic module."""
        from src.agents import critic

        assert critic is not None

    def test_fiscal_importable(self) -> None:
        """Should be able to import fiscal module."""
        from src.agents import fiscal

        assert fiscal is not None

    def test_guardrail_importable(self) -> None:
        """Should be able to import guardrail module."""
        from src.agents import guardrail

        assert guardrail is not None

    def test_planner_importable(self) -> None:
        """Should be able to import planner module."""
        from src.agents import planner

        assert planner is not None


class TestStateSchema:
    """Tests for state schema."""

    def test_state_schema_importable(self) -> None:
        """Should be able to import state schema."""
        from src.schemas.state import AgentState

        assert AgentState is not None

    def test_state_schema_is_typed_dict(self) -> None:
        """AgentState should be a TypedDict."""

        from src.schemas.state import AgentState

        # TypedDict classes have __annotations__
        assert hasattr(AgentState, "__annotations__")
