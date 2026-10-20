# cockroachdb-continuum

Idiomatic Python back-port of the **Cockroach Continuum** features for the
CockroachDB Python Library. Namespace: `cockroachdb.continuum`.

## Pillars

### vCluster — workload tagging & QoS

Tag a transaction with an `application_name` and steer its admission-control
quality-of-service. Activation is via a context manager or decorator; the core
`CockroachDBTemplate` applies the settings at transaction start (like follower
reads) by issuing `SET LOCAL application_name` and
`SET LOCAL default_transaction_quality_of_service`.

```python
from cockroachdb.continuum import Priority, vcluster, virtual_cluster

with vcluster("analytics-batch", priority=Priority.LOW):
    template.execute(run_report)  # runs at background QoS, tagged "analytics-batch"


@virtual_cluster("checkout", priority=Priority.HIGH)
def place_order() -> None:
    template.execute(...)  # runs at critical QoS
```

`Priority.LOW/NORMAL/HIGH` map to `background`/`regular`/`critical`.

### Plenum — storage insights

Customer-safe per-table row and byte estimates using only `SHOW TABLES` and
`SHOW RANGES FROM DATABASE ... WITH TABLES, DETAILS` — never `crdb_internal`.
Version-tolerant: missing columns degrade to `None` instead of raising.

```python
from cockroachdb.continuum import storage_summary

for t in storage_summary(conn):
    print(t.schema, t.table, t.rows, t.bytes)
```

### Aegis — autonomous-ops findings

A pluggable client protocol with findings/recommendations and an event exhaust.
`SimulatedAegisClient` is in-memory for dev/tests; `HttpAegisClient` is a stub
(the Aegis API is not yet public). `make_aegis(config)` returns the simulated
client when `endpoint` is `None`.

```python
from cockroachdb.continuum import AegisConfig, AegisExhaust, make_aegis

client = make_aegis(AegisConfig())
exhaust = AegisExhaust(client)
exhaust.record_retry("place_order", attempt=1, sqlstate="40001")
```

### Agent / MCP surface

Expose least-privilege tools to agents. `@agent_tool` marks callables;
`CrdbAgent` produces MCP `tools/list` / `tools/call` shapes. Destructive tools
are hidden unless `allow_destructive=True`.

```python
from cockroachdb.continuum import CrdbAgent, CrdbOpsTools

agent = CrdbAgent.from_providers(CrdbOpsTools(connection_factory=connect))
agent.list_tools()  # {"tools": [{"name": "health", ...}, ...]}
agent.invoke("health")  # {"content": [...], "isError": False}
```
