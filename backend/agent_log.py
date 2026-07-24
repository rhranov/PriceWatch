"""
Agent Activity Log
==================
Append-only log written by every agent operation (price checks, research,
auto-corrections, scraper failures). Persists across sessions so the next
Claude session can read what happened without relying on human memory.

Format (one line per event):
  2026-06-29 14:32  PRICE CHANGE       GMKtec EVO-X2 on Galaxus: EUR 3240 -> 2847 (-12.1%)
  2026-06-29 14:33  SCRAPER FAIL       amazon-de | ASUS Ascent GX10: no price element (run #3)
  2026-06-29 14:40  PRICE CHECK END    14 listings checked, 1 change, 0 errors

Log file: data/agent_log.jsonl
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import structlog

log = structlog.get_logger(__name__)

LOG_FILE = Path(__file__).parent.parent / "data" / "agent_log.jsonl"

_lock = asyncio.Lock()


async def log_event(event_type: str, message: str, **details) -> None:
    """
    Append one bounded JSON object to agent_log.jsonl.
    Never raises — logging must not crash the caller.
    """
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": str(event_type).replace("\r", " ").replace("\n", " ")[:80],
            "message": str(message)[:10_000],
            "details": {
                str(key)[:100]: str(value)[:1_000]
                for key, value in list(details.items())[:50]
            },
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        async with _lock:
            async with aiofiles.open(LOG_FILE, "a", encoding="utf-8") as f:
                await f.write(line)
    except Exception as e:
        log.warning("agent_log: write failed", error=str(e))


def read_recent(days: int = 7) -> list[dict]:
    """
    Read and parse log entries from the last N days.
    Returns list of dicts: {ts, event_type, message, details_raw}
    Synchronous — safe to call from local integration handlers.
    """
    if not LOG_FILE.exists():
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    entries = []

    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                if len(line) > 50_000:
                    continue
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        continue
                    ts = datetime.fromisoformat(str(record.get("ts", "")))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts.timestamp() < cutoff:
                        continue
                    entries.append({
                        "ts": ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                        "event_type": str(record.get("event_type", ""))[:80],
                        "message": str(record.get("message", ""))[:10_000],
                    })
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
    except Exception as e:
        log.warning("agent_log: read failed", error=str(e))

    return entries


def build_briefing(days: int = 7) -> str:
    """
    Summarise recent log activity into a plain-text briefing for the agent.
    Called by the local activity briefing at the start of every session.
    """
    entries = read_recent(days)
    if not entries:
        return f"No activity logged in the last {days} days. This may be the first session."

    # Bucket by event type
    price_changes = [e for e in entries if e["event_type"] == "PRICE CHANGE"]
    scraper_fails = [e for e in entries if e["event_type"] == "SCRAPER FAIL"]
    check_ends = [e for e in entries if e["event_type"] == "PRICE CHECK END"]
    research_events = [e for e in entries if e["event_type"].startswith("RESEARCH")]
    discoveries = [e for e in entries if e["event_type"] == "DISCOVERY"]

    # Detect consecutive failures: find sources that appear in scraper_fails
    # multiple times with no successful check in between
    fail_counts: dict[str, int] = {}
    for e in scraper_fails:
        key = e["message"].split(":")[0].strip() if ":" in e["message"] else e["message"]
        fail_counts[key] = fail_counts.get(key, 0) + 1

    persistent_failures = {k: v for k, v in fail_counts.items() if v >= 2}

    lines = [
        f"Session briefing — last {days} days ({len(entries)} log entries)\n",
        "=" * 56,
    ]

    # Last price check
    if check_ends:
        lines.append(f"\nLast price check:  {check_ends[-1]['ts']}")
        lines.append(f"  {check_ends[-1]['message']}")
    else:
        lines.append("\nNo price check runs recorded in this period.")

    # Price changes
    if price_changes:
        lines.append(f"\nPrice changes ({len(price_changes)}):")
        for e in price_changes[-10:]:
            lines.append(f"  {e['ts']}  {e['message']}")
    else:
        lines.append("\nNo price changes recorded.")

    # Persistent scraper failures — needs attention
    if persistent_failures:
        lines.append(f"\n!! NEEDS ATTENTION — persistent scraper failures:")
        for key, count in persistent_failures.items():
            lines.append(f"  {key}  ({count} consecutive failures)")
    elif scraper_fails:
        lines.append(f"\nTransient scraper failures ({len(scraper_fails)}) — no persistent issues.")

    # Research / discoveries
    if research_events or discoveries:
        lines.append(f"\nResearch activity ({len(research_events)} events, {len(discoveries)} discoveries):")
        for e in (research_events + discoveries)[-5:]:
            lines.append(f"  {e['ts']}  {e['message']}")

    lines.append("\n" + "=" * 56)
    lines.append("End of briefing. Recommend calling audit_dashboard if >48h since last price check.")

    return "\n".join(lines)
