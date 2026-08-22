"""Per-client-IP daily budget for upstream-consuming (cold) requests.

Cache hits are never limited; only calls that would spend the shared
dandanplay quota count against the budget, so a single heavy client
cannot drain the daily quota for everyone. Counters live in process
memory (single-worker deployment) and reset at local midnight; a restart
also resets them, which is an acceptable trade-off.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from ..config import settings

logger = logging.getLogger(__name__)

_day: date = date.today()
_counters: Dict[str, int] = {}


def _rollover() -> None:
    global _day
    today = date.today()
    if today != _day:
        _day = today
        _counters.clear()


def seconds_until_reset() -> int:
    """Seconds until local midnight, for Retry-After headers."""
    now = datetime.now()
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    return max(1, int((tomorrow - now).total_seconds()))


def try_consume(ip: Optional[str]) -> bool:
    """Reserve one upstream call for this IP; False when over budget.

    Unlimited when the budget is disabled (<= 0) or the IP is unknown.
    """
    budget = settings.IP_DAILY_UPSTREAM_BUDGET
    if budget <= 0 or not ip:
        return True
    _rollover()
    used = _counters.get(ip, 0)
    if used >= budget:
        if used == budget:
            # Log once per IP per day, on the first rejection
            _counters[ip] = used + 1
            logger.warning(f"IP {ip} 已达每日回源预算({budget})，后续冷回源请求将被拒绝")
        return False
    _counters[ip] = used + 1
    return True


def snapshot() -> Dict[str, int]:
    """Summary for the monitoring dashboard."""
    _rollover()
    budget = settings.IP_DAILY_UPSTREAM_BUDGET
    return {
        "budget": budget,
        "tracked_ips": len(_counters),
        "over_budget_ips": sum(1 for v in _counters.values() if v > budget) if budget > 0 else 0,
    }
