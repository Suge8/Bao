#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
source scripts/uv_pytest.sh

run_uv_pytest core -m smoke \
    tests/test_asyncio_runner.py \
    tests/test_jsonc_patch.py \
    tests/test_chat_model_basic.py \
    tests/test_provider_retry_core.py \
    tests/test_hub_builder_core.py \
    tests/test_plan_tools.py \
    tests/test_chat_service.py \
    tests/test_session_service.py \
    "$@"
