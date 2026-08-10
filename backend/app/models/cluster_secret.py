"""Encrypted cluster secrets stored in the shared GUI database."""
from datetime import datetime
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class ClusterSecret(Base):
    """Named secret (Fernet enc:v1:…) shared by all clustered consoles.

    Values are encrypted with encrypt_secret() using OPENVOX_GUI_SECRET_KEY.
    Both consoles must use the same secret_key or decrypt fails.
    """

    __tablename__ = "cluster_secrets"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_enc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
