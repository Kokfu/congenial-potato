# syntax=docker/dockerfile:1
FROM postgres:17.6
# Initialization runs as postgres. Do not depend on host checkout permissions or
# relax the permissions of host secrets to make a bind-mounted script readable.
COPY --chown=postgres:postgres --chmod=0500 docker/init-db.sh /docker-entrypoint-initdb.d/01-workflow-db.sh
