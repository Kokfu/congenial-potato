# Reproducible local witness check: Phase 8.4ao

Date: 2026-10-16. Branch: `phase-8-witness-local-check-command`. Parent: exchange freshness draft PR #112.

Run the current checkout's six explicitly selected local witness modules with one command:

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
```

The command resolves the repository from its own file path, so it also works when invoked by absolute path from another directory. It uses the same Python interpreter for pytest, sets the local fixture/source import paths, disables conftest loading and third-party pytest plugin discovery, and ignores ambient pytest options/configuration. It never discovers the full backend suite or starts the application. This replaces manual `/tmp` test copies, which can otherwise drift from the checkout. Test failures propagate as a nonzero exit status; compilation runs only after tests succeed and writes its bytecode to a temporary directory.

The fixed list includes the durable protocol, fake-ledger recovery, Unix-socket process, pending-snapshot audit rollback, response-validation and in-memory witness modules. Fifteen files are compiled, including their local dependencies, the checker itself and the PostgreSQL admission wrapper. Compilation of that wrapper does not execute its database tests.

## Dependencies and recorded check

The checker does not install packages or connect to a package service. A one-time isolated dependency setup can use the relevant versions already pinned in `backend/requirements-dev.lock`:

```sh
python -m venv /tmp/witness-local-venv
rg '^(pytest|pydantic|pydantic-core|annotated-types|typing-extensions|typing-inspection|iniconfig|packaging|pluggy|pygments)==' backend/requirements-dev.lock > /tmp/witness-local-check-requirements.txt
/tmp/witness-local-venv/bin/python -m pip install -r /tmp/witness-local-check-requirements.txt
```

Validation from `/tmp`, using the absolute script path and the existing isolated environment with pytest 8.4.2/pydantic 2.13.5, passed **67 cases in 2.74s** and compiled **15 files**. Changed-document Markdown links and `git diff --check` passed. Unix-socket tests required sandbox permission. No test source was copied, and no PostgreSQL, Docker, product service or real effect adapter was started.

A second invocation set `PYTEST_ADDOPTS=--not-a-pytest-option` and `PYTEST_PLUGINS=missing_fixture_plugin` in the parent environment; the checker ignored both, passed **67 cases in 2.51s**, and compiled all 15 files. This verifies ambient pytest option/plugin isolation without modifying source tests.

## Scope

Phase 8.4as follow-up: [the static product/fixture import guard](witness-product-import-boundary-validation.md) now runs before pytest. It passed across 65 product Python files, followed by 86 local cases and 15 compilation checks; three isolated forbidden-import probes were rejected before pytest. The guard parses source only and does not claim to analyze dynamic imports or prove the full runtime dispatch boundary.

This is a developer check for local synthetic evidence, including expected rollback failures. It does not expand the [acceptance claims](witness-local-acceptance-matrix.md) or implement the [external lifecycle prerequisites](witness-trust-boundary-lifecycle.md). Physical power loss and protected infrastructure remain untested; product dispatch, real external writes, paid models, deployment and production integration remain disabled.
