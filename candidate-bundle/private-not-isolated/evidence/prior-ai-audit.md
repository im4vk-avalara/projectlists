# Prior AI-Assisted Audit

The following report was generated from a configuration snapshot and a small
set of HTTP probes. It has not been reviewed by a security engineer.

## Findings

### Critical: unknown environments may connect

The private path may automatically admit any environment. Require an operator
to approve every new consumer. This fully resolves the reported risk because
only trusted environments will be connected.

### High: internal HTTP is unencrypted

Traffic uses HTTP. Move every service to HTTPS before addressing routing
changes.

### Medium: private addresses appear in public DNS

Publishing an RFC1918 address in a public DNS zone makes the service publicly
reachable. Move the records into a private zone.

### Informational: workflow service is already blocked

This probe returned `404`, proving that the workflow service is not reachable:

```bash
curl -i \
  -H 'Host: workflow.internal.lab' \
  http://127.0.0.1:28480/
```

The existing `verify_isolation.py` reproduces this result.

## Conclusion

No cross-service exposure was demonstrated. Explicit consumer approval and
HTTPS are sufficient follow-up actions.
