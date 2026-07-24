"""
Sync layer between the local PriceWatch database and the scheduled Claude agent
that runs in Claude Desktop.

Flow:
  export_watchlist.py  →  data/sync/watchlist_export.json   (DB → file, agent reads)
  import_run.py        ←  data/sync/runs/*.json             (file → DB, agent writes)

The agent never touches Postgres directly. It reads the exported watchlist via
the device bridge and writes run-result files back; the backend ingests them.
"""
