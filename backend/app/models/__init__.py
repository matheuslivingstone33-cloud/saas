"""Modelos ORM. Importar daqui garante que o Alembic enxergue todo o metadata."""

from app.db.base import Base
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.cost_event import CostEvent
from app.models.credit_ledger import CreditLedger
from app.models.lead import Lead, RamoCnae
from app.models.learning import ScoreWeights
from app.models.message import Message
from app.models.opt_out import OptOut
from app.models.privacy import PrivacyRequest
from app.models.user import Subscription, User

__all__ = [
    "AuditLog",
    "Base",
    "Campaign",
    "CostEvent",
    "CreditLedger",
    "Lead",
    "Message",
    "OptOut",
    "PrivacyRequest",
    "RamoCnae",
    "ScoreWeights",
    "Subscription",
    "User",
]
