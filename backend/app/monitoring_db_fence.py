"""Database-local generation fencing for monitoring result writes.

A new generation must be granted only to an authorized, active monitoring run.
The caller must coordinate that grant with its Redis lease and supervisor.
No cross-store atomicity is claimed.
"""
import logging
from sqlalchemy import Integer, String, update, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from app.db import Base


class MonitoringFence(Base):
    __tablename__ = "monitoring_fences"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)


class MonitoringResult(Base):
    __tablename__ = "monitoring_results"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[str] = mapped_column(String(4096), nullable=False)


NAME = "audit-integrity"
logger = logging.getLogger(__name__)


def begin_monitoring_generation(session: Session) -> int:
    """Advance database fencing generation; caller must hold trusted run authority.

    Requires the singleton fence row installed by migration 007. Transaction
    serialization is enforced by UPDATE's row lock on PostgreSQL.
    """
    result = session.execute(
        update(MonitoringFence)
        .where(MonitoringFence.name == NAME)
        .values(generation=MonitoringFence.generation + 1)
        .returning(MonitoringFence.generation)
    ).scalar_one_or_none()
    if result is None:
        raise RuntimeError("monitoring fence not initialized")
    return result


def write_monitoring_result(session: Session, generation: int, value: str) -> bool:
    """Write at most one distinct result per generation in the same DB transaction.

    The UPDATE locks the fence row until commit, serializing it against new
    generation grants. No external webhook or Redis side effect is fenced.
    """
    if type(generation) is not int or generation <= 0:
        raise ValueError("invalid generation")
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("invalid result")
    current = session.execute(
        update(MonitoringFence)
        .where(MonitoringFence.name == NAME, MonitoringFence.generation == generation)
        .values(generation=MonitoringFence.generation)
        .returning(MonitoringFence.generation)
    ).scalar_one_or_none()
    if current is None:
        return False
    existing = session.get(MonitoringResult, NAME)
    if existing is None:
        session.add(MonitoringResult(name=NAME, generation=generation, value=value))
    elif existing.generation == generation:
        # Identical retries succeed without rewriting; conflicting retries fail closed.
        return existing.value == value
    else:
        existing.generation = generation
        existing.value = value
    session.flush()
    return True


def begin_authorized_monitoring_generation(session: Session, lease, *, ttl_seconds: int = 30) -> int:
    """Fail closed before granting a DB generation unless the live Redis lease renews.

    This is a pre-grant authorization check, not a distributed transaction:
    lease ownership can change after renewal. External side effects still
    require their own durable fencing/idempotency protocol.
    """
    from app.audit_monitor_lease import RedisMonitoringLease

    if not isinstance(lease, RedisMonitoringLease):
        logger.warning("monitoring_generation_denied reason=invalid_authority")
        raise PermissionError("monitoring lease authority required")
    try:
        authorized = lease.renew("audit-monitor:single-run", ttl_seconds)
    except Exception as exc:
        logger.warning("monitoring_generation_denied reason=redis_unavailable")
        raise PermissionError("monitoring lease unavailable") from exc
    if not authorized:
        logger.warning("monitoring_generation_denied reason=lease_not_owned")
        raise PermissionError("monitoring lease not owned")
    generation = begin_monitoring_generation(session)
    logger.info("monitoring_generation_granted generation=%d", generation)
    return generation
