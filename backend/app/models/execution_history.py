"""
Database model for orchestration execution history.
"""
from sqlalchemy import Column, String, DateTime, Integer, Text, JSON
from datetime import datetime, timezone
from ..database import Base


def _utc_naive() -> datetime:
    """Naive UTC for TIMESTAMP WITHOUT TIME ZONE (asyncpg-safe)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ExecutionHistory(Base):
    """Tracks execution history for commands, tasks, and plans."""
    __tablename__ = "execution_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_type = Column(String(20), nullable=False, index=True)  # 'command', 'task', or 'plan'
    node_name = Column(String(255), nullable=False, index=True)
    command_name = Column(String(255), nullable=True)  # For commands
    task_name = Column(String(255), nullable=True)  # For tasks
    plan_name = Column(String(255), nullable=True)  # For plans
    environment = Column(String(255), nullable=True)  # For plans
    parameters = Column(JSON, nullable=True)  # Store any additional parameters
    result_format = Column(String(20), nullable=True)  # 'human', 'json', 'rainbow'
    status = Column(String(20), nullable=False)  # 'success', 'failure', 'running', 'queued'
    executed_at = Column(DateTime, nullable=False, index=True, default=_utc_naive)
    executed_by = Column(String(255), nullable=False)  # Username who executed
    duration_ms = Column(Integer, nullable=True)  # Execution duration in milliseconds
    error_message = Column(Text, nullable=True)  # Error message if failed
    result_preview = Column(Text, nullable=True)  # First 500 chars of result
