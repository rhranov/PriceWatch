"""
Deep Research Agent — Software 3.0 edition.

The agent IS Claude. Python code does only three things:
  1. Read live context from DB (scope rules, already-tracked products, active sources)
  2. Call Claude API with web_search built-in tool + a structured submit_discovery tool
  3. Write verified discoveries to pending_discoveries and flush results to the run record

All research logic, source selection, candidate evaluation, and qualification
judgment lives in the system prompt and Claude's reasoning — not in Python.

x.com / Twitter is covered via Anthropic's web_search_20250305 tool, which
indexes tweets. The agent is instructed to include explicit site:x.com queries.
"""

import asyncio
import json
import traceback
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_log import log_event

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# System prompt builder — reads from DB, never hardcodes entities
# ---------------------------------------------------------------------------

async def _build_system_prompt(session: AsyncSession) -> str:
    """Build the research system prompt from live DB state."""

    # --- Scope definition ---
    scope_r = await session.execute(text("""
        SELECT ps.name, ps.slug, ps.description, ps.qualifier_rules
        FROM product_scopes ps
        JOIN scope_sources ss ON ss.scope_id = ps.id
        WHERE ss.is_active = true
        GROUP BY ps.id, ps.name, ps.slug, ps.description, ps.qualifier_rules
        LIMIT 1
    """))
    scope_row = scope_r.fetchone()
    if not scope_row:
        raise RuntimeError("No active scope found in DB")

    scope_name  = scope_row.name
    scope_slug  = scope_row.slug
    scope_desc  = scope_row.description or ""
    qualifiers  = scope_row.qualifier_rules or {}

    qualifier_text = json.dumps(qualifiers, indent=2) if qualifiers else "(no structured rules — use description)"

    # --- Already-tracked products ---
    products_r = await session.execute(text("""
        SELECT p.name, p.brand, p.model, p.specs
        FROM products p
        WHERE p.status = 'active'
        ORDER BY p.name
    """))
    tracked = products_r.fetchall()
    tracked_lines = [
        f"  - {r.name} ({r.brand} {r.model})"
        for r in tracked
    ]

    # --- Active sources ---
    sources_r = await session.execute(text("""
        SELECT s.name, s.slug, s.base_url
        FROM sources s
        JOIN scope_sources ss ON ss.source_id = s.id
        WHERE s.is_active = true AND ss.is_active = true
        ORDER BY s.name
    """))
    sources = sources_r.fetchall()
    source_lines = [
        f"  - {r.name} ({r.slug}): {r.base_url}"
        for r in sources
    ]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return f"""You are a market intelligence agent for the PriceWatch price monitoring system.
Today is {today} (UTC).

## Your mission
Find NEW products that qualify for the **{scope_name}** scope and are available for purchase in Germany with a confirmed EUR price.

## Scope: {scope_name} (slug: {scope_slug})
{scope_desc}

Qualification rules (from DB):
{qualifier_text}

## Already tracked — DO NOT rediscover these
{chr(10).join(tracked_lines) if tracked_lines else "  (none yet)"}

## Active sources to check for listings
{chr(10).join(source_lines)}

## Research process

### Phase 1 — Market intelligence (use web_search for ALL of these)
Search broadly to catch announcements, launches, and availability updates:

1. **x.com / Twitter** — use explicit `site:x.com` searches:
   - `site:x.com {scope_name} launch OR release OR available`
   - `site:x.com {scope_name} price EUR`
   - `site:x.com AI hardware mini PC 2025 Germany`

2. **Tech news** — search each of these sources:
   - The Verge, Ars Technica, AnandTech, Tom's Hardware
   - HardwareLuxx, Heise.de, Golem.de, ComputerBase.de (German tech press — critical for DE market)

3. **Manufacturer sites** — search for product pages on manufacturer domains

4. **German retailers** — search Geizhals, Amazon.de, Alternate, Jacob for new listings matching the scope criteria

5. **Price & availability signals**:
   - Products announced but not yet released (track, note as "pre-order")
   - Price drops or restocks on existing near-qualifiers
   - Discontinued products (note so we can deactivate)

### Phase 2 — Candidate verification
For each candidate you find:
1. Confirm it meets the qualification rules from DB
2. Find a EUR price from a German retailer or EU store
3. Confirm it ships to Germany
4. Check if it is in stock or available for pre-order
5. Call `submit_discovery` only for verified candidates

### Submission rules
- ONLY call `submit_discovery` for products you have verified (EUR price confirmed, ships DE)
- If you cannot confirm a price, record it in your reasoning as "unverified" — do NOT submit
- Set confidence=high only if you verified the price on 2+ sources
- Include your research sources and reasoning in the `ai_reasoning` field

### Output
After all searches and submissions, write a brief summary covering:
- How many candidates you found and how many were verified
- Key market trends or signals worth noting
- Any products that were close to qualifying but fell short (and why)
- Upcoming launches to watch

Be thorough. Missing a genuine new product that qualifies is worse than spending extra time searching.
"""


# ---------------------------------------------------------------------------
# submit_discovery tool schema (Claude calls this to submit a candidate)
# ---------------------------------------------------------------------------

SUBMIT_DISCOVERY_TOOL = {
    "name": "submit_discovery",
    "description": (
        "Submit a verified product discovery. Only call this after confirming "
        "a EUR price, Germany availability, and that the product meets the scope qualifiers. "
        "Do NOT call for unverified candidates."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "product_name":    {"type": "string", "description": "Full product name including variant/memory spec"},
            "brand":           {"type": "string"},
            "model":           {"type": "string"},
            "price_eur":       {"type": "number", "description": "Verified EUR price"},
            "in_stock":        {"type": "boolean"},
            "listing_url":     {"type": "string", "description": "Direct URL to the product on the source"},
            "source_slug":     {"type": "string", "description": "Source slug from the active sources list"},
            "ai_reasoning":    {"type": "string", "description": "Why this qualifies, where you found the price"},
            "confidence":      {"type": "string", "enum": ["high", "medium", "low"], "default": "medium"},
            "verified_sources":{"type": "integer", "description": "Number of sources where you confirmed price+availability"},
        },
        "required": ["product_name", "brand", "model", "price_eur", "in_stock", "listing_url", "source_slug", "ai_reasoning"],
    },
}


# ---------------------------------------------------------------------------
# DB write: create a discovery record
# ---------------------------------------------------------------------------

async def _write_discovery(
    session: AsyncSession,
    args: dict,
    scope_slug: str,
) -> str:
    """Write one discovery to pending_discoveries. Returns outcome string."""
    confidence       = args.get("confidence", "medium")
    verified_sources = args.get("verified_sources", 1)
    source_slug      = args["source_slug"]

    # Live verification — never trust the agent-declared price or in_stock.
    # Fetch the URL right now and use what the page actually shows.
    from backend.scrapers.verify import verify_listing_url
    v_ok, v_price, v_title, v_in_stock, v_error = await verify_listing_url(
        source_slug, args["listing_url"], expected_product_name=args["product_name"]
    )
    if not v_ok:
        return (
            f"ERROR: URL verification failed for {args['listing_url']}: {v_error}. "
            f"Record as error in research JSON and recheck next run."
        )
    if v_price is None:
        return (
            f"ERROR: live fetch of {args['listing_url']} returned no price "
            f"(title: '{v_title}'). Product may be unavailable. "
            f"Record as error and recheck next run."
        )

    # Resolve scope
    scope_r = await session.execute(
        text("SELECT id FROM product_scopes WHERE slug = :slug"),
        {"slug": scope_slug},
    )
    scope_row = scope_r.fetchone()
    if not scope_row:
        return f"ERROR: scope '{scope_slug}' not found"

    # Resolve source
    src_r = await session.execute(
        text("SELECT id, name FROM sources WHERE slug = :slug"),
        {"slug": source_slug},
    )
    source_row = src_r.fetchone()
    source_name = source_row.name if source_row else source_slug

    # Model-supplied confidence never authorizes approval.
    status = "pending"

    await session.execute(text("""
        INSERT INTO pending_discoveries
            (id, scope_id, name, brand, model,
             source_name, source_url, price_eur, in_stock,
             ai_reasoning, status, found_at)
        VALUES
            (gen_random_uuid(), :scope_id, :name, :brand, :model,
             :source_name, :source_url, :price, :in_stock,
             :reasoning, :status, NOW())
    """), {
        "scope_id":    scope_row.id,
        "name":        args["product_name"],
        "brand":       args["brand"],
        "model":       args["model"],
        "source_name": source_name,
        "source_url":  args["listing_url"],
        "price":       v_price,
        "in_stock":    v_in_stock,
        "reasoning":   args.get("ai_reasoning", ""),
        "status":      status,
    })

    await log_event(
        "DISCOVERY",
        f"{status.upper()} — {args['product_name']} EUR {v_price:.2f} on {source_slug} (verified live)",
    )

    return f"{status.upper()}: {args['product_name']} EUR {v_price:.2f} → {status}"


# ---------------------------------------------------------------------------
# Main agent class
# ---------------------------------------------------------------------------

class ResearchAgent:

    def __init__(self, model: str | None = None):
        from backend.config import settings
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model  = model or settings.researcher_model

    async def run(
        self,
        session: AsyncSession,
        run_id: str,
        max_search_terms: int = 20,
    ) -> dict[str, Any]:
        """
        Run deep research for the active scope.
        Returns a summary dict suitable for writing to the AgentRun record.
        """
        await log_event("RESEARCH START", f"model={self.model}", run_id=run_id)
        log.info("Research agent starting", model=self.model, run_id=run_id)

        try:
            system_prompt = await _build_system_prompt(session)
        except Exception as e:
            log.error("Research: failed to build system prompt", error=str(e))
            return {"error": str(e), "discoveries": [], "errors": [{"error": str(e)}]}

        # Read active scope slug for discovery writes
        scope_r = await session.execute(text("""
            SELECT ps.slug FROM product_scopes ps
            JOIN scope_sources ss ON ss.scope_id = ps.id
            WHERE ss.is_active = true
            GROUP BY ps.id, ps.slug LIMIT 1
        """))
        scope_slug = scope_r.scalar()
        if not scope_slug:
            return {"error": "No active scope", "discoveries": [], "errors": []}

        tools = [
            {"type": "web_search_20250305", "name": "web_search"},
            SUBMIT_DISCOVERY_TOOL,
        ]

        messages = [{"role": "user", "content": "Begin deep research for the active scope."}]

        discoveries: list[dict] = []
        errors: list[dict] = []
        final_summary = ""

        # Agentic loop — Claude runs until it stops calling tools.
        #
        # web_search_20250305 is a SERVER-SIDE tool: Anthropic executes the search
        # and injects web_search_result blocks into the SAME response. The client
        # never provides tool_results for web_search — only for submit_discovery.
        # If stop_reason="tool_use" with only web_search blocks, that shouldn't
        # happen (server-side tools complete without requiring a client turn), but
        # we break safely if it does to avoid an infinite loop.
        while True:
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=8192,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            log.debug("Research agent response", stop_reason=response.stop_reason,
                      blocks=len(response.content))

            # Collect any text blocks for the summary
            for block in response.content:
                if hasattr(block, "text") and block.type == "text":
                    final_summary += block.text + "\n"

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason != "tool_use":
                log.warning("Unexpected stop reason", reason=response.stop_reason)
                break

            # Build tool_results ONLY for client-side tools (submit_discovery).
            # web_search is server-side: its results are already in response.content
            # as web_search_result_20250305 blocks — we skip it entirely.
            tool_results = []
            for block in response.content:
                if not hasattr(block, "type") or block.type != "tool_use":
                    continue
                if block.name == "web_search":
                    continue  # server-side — Anthropic handles execution + results

                if block.name == "submit_discovery":
                    try:
                        outcome = await _write_discovery(session, block.input, scope_slug)
                        await session.commit()
                        discoveries.append({**block.input, "outcome": outcome})
                        log.info("Discovery submitted", name=block.input.get("product_name"), outcome=outcome)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": outcome,
                        })
                    except Exception as e:
                        err = f"submit_discovery failed: {e}"
                        errors.append({"tool": "submit_discovery", "error": err,
                                       "product": block.input.get("product_name")})
                        log.error("Discovery write error", error=str(e))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"ERROR: {err}",
                            "is_error": True,
                        })

            if not tool_results:
                # Only web_search or unknown server-side tools in this turn —
                # no client response needed, but that means the loop shouldn't
                # have had stop_reason="tool_use". Break to avoid infinite loop.
                log.warning("tool_use stop with no client-side tools to handle; breaking")
                break

            # Continue: send assistant turn + tool results back
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        summary = (
            f"Research completed. Discoveries: {len(discoveries)}. "
            f"Errors: {len(errors)}.\n\n{final_summary.strip()}"
        )
        await log_event("RESEARCH END", f"{len(discoveries)} discoveries, {len(errors)} errors", run_id=run_id)

        return {
            "discoveries_found": len(discoveries),
            "discoveries": discoveries,
            "errors": errors,
            "summary": summary,
        }
