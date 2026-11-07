# Private, Not Isolated

## Scenario

Two production environments communicate over a private network path. The
approved consumer must be able to call exactly one service in the restricted
environment:

| Entry point | Intended access |
|---|---|
| `PRIVATE_ENDPOINT` | `assistant.internal.lab` only |
| `OPERATIONS_ENDPOINT` | All internal services required by operations |

A review questioned whether "private" and "approved consumer" actually imply
service isolation. You have the current access-plane configuration, a service
catalog, a sanitized operations trace, a prior AI-assisted audit, a local lab,
and a verifier written during that audit.

## Lab Model

The two local URLs are access-plane entry points, not direct service URLs:

| Environment role | Variable | Local listener |
|---|---|---|
| Approved consumer | `PRIVATE_ENDPOINT` | `http://127.0.0.1:28480` |
| Internal operations | `OPERATIONS_ENDPOINT` | `http://127.0.0.1:28481` |

Keep the two endpoints distinct when reproducing and verifying behavior. The
lab returns an `X-Lab-Entrypoint` response header so you can confirm which one
handled a request.

The configuration assigns each entry point a named route set. Within a route
set, `request_host` corresponds to the HTTP `Host` value and selects a
synthetic service. This describes the lab mechanics only; you must determine
whether the configured access satisfies the intended boundary.

## Start the Lab

From this directory, start the macOS lab:

```bash
./run_lab.sh
```

Keep that terminal open. It prints the absolute configuration path in use. Edit
that exact `config/access-plane.json` file from another terminal or your editor.
Saved, valid routing changes take effect on the next request; do not restart the
lab. If a request returns `500`, inspect the lab terminal for a configuration
error.

In a second terminal, set the endpoints and run the supplied verifier:

```bash
export PRIVATE_ENDPOINT=http://127.0.0.1:28480
export OPERATIONS_ENDPOINT=http://127.0.0.1:28481
python3 verify_isolation.py
```

The supplied verifier is part of the prior audit and may be incomplete or
misleading. Its setup check should still identify the approved-consumer entry
point. When comparing behavior before and after an edit, keep the endpoint,
host, and path deliberate so you know which boundary the result tests.

You may use an editor, CLI, documentation, internet access, or an AI assistant.
Think aloud and verify claims against the running system.

## Task

1. Triage the supplied evidence. Identify real findings, unsupported claims,
   and misleading checks. Rank findings by exploitability and blast radius.
2. Demonstrate any cross-boundary access through `PRIVATE_ENDPOINT`. Capture
   the flag from a service that the approved consumer must not reach.
3. Apply the smallest sound change to `config/access-plane.json`.
4. Replace or repair `verify_isolation.py` so it proves:
   - the approved service remains reachable;
   - prohibited services are not reachable through `PRIVATE_ENDPOINT`;
   - the operations path still works.
5. Explain how you would implement the same security properties in a cloud or
   infrastructure stack you know well. Choose the provider and tooling.
6. Describe a no-interruption rollout, monitoring plan, and rollback.

Do not obtain the flag by inspecting processes, environment variables, or
reverse engineering the lab binary. The flag must be retrieved through the
network path.

## Constraints

- Existing approved traffic cannot be interrupted.
- Internal operations must retain access to `workflow-api`.
- Do not rely on hostnames being secret.

## Deliverables

- Captured flag and reproduction command or script.
- Ranked findings with evidence.
- Updated `config/access-plane.json`.
- Working `verify_isolation.py` and its output.
- Short production design and migration explanation.
