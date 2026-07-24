# Security

PriceWatch is designed for local use. Its HTTP services and database bind to loopback, and setup generates unique local credentials.

## Dependency-audit exception

`CVE-2026-31072` affects APScheduler's optional JSON and CBOR object deserializers. PriceWatch uses the default in-memory data store and passes Python objects directly; it does not configure either affected serializer or accept serialized scheduler data from users or the network. The advisory therefore has no reachable source-to-sink path in this application. It should be re-evaluated when APScheduler publishes a fixed release or if persistent scheduler serialization is introduced.

Do not report credentials from a local `.env` file. Remove them from any reproduction before sharing it.
