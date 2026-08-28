"""Operator-dismissed certnames (ghosts) hidden from the live fleet UI."""
from sqlalchemy import Column, String, DateTime
from datetime import datetime, timezone
from ..database import Base


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DismissedNode(Base):
    """A certname the operator removed from GUI fleet lists.

    Used when the host is gone but PuppetDB / CA still list it
    (unclassified ghosts). get_live_nodes() excludes these names.
    """

    __tablename__ = "dismissed_nodes"

    certname = Column(String(255), primary_key=True)
    dismissed_at = Column(DateTime, default=_utc_naive)
    dismissed_by = Column(String(128), nullable=False, server_default="")
    reason = Column(String(255), nullable=False, server_default="ghost")
