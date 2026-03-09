#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

PYTHONPATH=. uv run pytest -m smoke \
    tests/test_asyncio_runner.py \
    tests/test_jsonc_patch.py \
    tests/test_chat_model.py \
    tests/test_provider_retry.py \
    tests/test_gateway_builder.py \
    tests/test_plan.py \
    tests/test_chat_service.py \
    tests/test_session_service.py \
    "$@"
