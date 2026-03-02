FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ARG BAO_UID=10001
ARG BAO_GID=10001

# Install Node.js 20 for the WhatsApp bridge
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg git && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${BAO_GID}" bao && \
    useradd --uid "${BAO_UID}" --gid "${BAO_GID}" --create-home --shell /bin/bash bao

WORKDIR /app

# Install Python dependencies first (cacheable layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p bao bridge && touch bao/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf bao bridge

# Copy full source and install
COPY bao/ bao/
COPY bridge/ bridge/
RUN uv pip install --system --no-cache .

# Build the WhatsApp bridge
WORKDIR /app/bridge
RUN npm install && npm run build
WORKDIR /app

# Create runtime directories
RUN mkdir -p /home/bao/.bao /tmp && \
    chown -R bao:bao /home/bao /app

USER bao
ENV HOME=/home/bao

ENTRYPOINT ["bao"]
