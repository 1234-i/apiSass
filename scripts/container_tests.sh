#!/usr/bin/env bash
set -euo pipefail
# Run the Python unit tests inside the same image used by the API container.
# Requires docker compose up to have built/started the api service.
docker compose exec -T api pytest -q tests
