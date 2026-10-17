# Listener thread startup cleanup: Phase 8.4br

Date: 2026-10-17. Branch: `phase-8-witness-listener-startup-cleanup`. Parent: draft PR [#141](https://github.com/Kokfu/congenial-potato/pull/141), commit `4c75f52375feeaf6a58a59fb1177f5dba741c07d`.

The local witness bound and listened on its Unix socket before creating the listener thread. If thread construction or `start()` raised `RuntimeError` or `OSError`, startup propagated the raw error without closing the listening descriptor or removing its endpoint. An unstarted thread reference could also make later `close()` attempt an invalid join.

Startup now handles those thread failures by setting the stop flag, closing the listener, clearing listener/thread references, and removing only a socket path whose device/inode matches the one bound by this instance. It returns `WitnessTransportDenied`. Normal close shares the same owned-path removal helper. Recovery uses a fresh server instance; restarting the failed instance is not established by this change.

Five new cases failed on the parent. Four inject the two failure types at thread construction/start, then verify closed listener descriptors, removed paths, idempotent close, byte-identical witness state, and a healthy authenticated generation query through a fresh real server. The fifth replaces the path during failed thread startup and verifies both failure cleanup and subsequent close preserve the replacement socket.

```sh
/workspace/witness-venv/bin/python scripts/check_local_witness.py
```

Result: **174 local cases passed in 6.93s**, **65 product-source static import checks passed**, **15 files compiled**; inventory **70/13/57/1/24/9**, with the transport module independently collecting 57 cases. Changed-document Markdown targets and whitespace checks passed. PostgreSQL was not rerun for this listener-only failure-path change. The [previous seven-case focused result](witness-client-exchange-deadline-validation.md) and [older 35-case admission result](witness-current-postgres-checkpoint.md) remain historical; compilation of the PostgreSQL helper does not execute its tests.

Shell Git authentication was unavailable at the preceding checkpoint. Publication uses the GitHub connector Git-data API with an exact tree comparison and a synchronized clean local commit.

This covers synchronous thread-construction/start failure and owned local endpoint cleanup. Inode inspection/unlink remains non-atomic; concurrent replacement/startup, arbitrary thread implementation failure after launching work, resource exhaustion elsewhere and service-wide availability are not guaranteed. It supplies no independent recovery, protected storage or production transport evidence. All [external prerequisites](witness-trust-boundary-lifecycle.md) and disabled product dispatch/paid-model/real-effect/production/deployment/merge gates remain in force.
