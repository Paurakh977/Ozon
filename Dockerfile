# ─────────────────────────────────────────────────────────────────
# Stage 1: Install Dependencies
# ─────────────────────────────────────────────────────────────────
FROM oven/bun:1-slim AS deps
WORKDIR /app
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile

# ─────────────────────────────────────────────────────────────────
# Stage 2: Build Next.js in Standalone Mode
# ─────────────────────────────────────────────────────────────────
FROM oven/bun:1-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Allow passing NEXT_PUBLIC vars into the build (passed via --build-arg)
ARG NEXT_PUBLIC_AGENT_WS_URL
ENV NEXT_PUBLIC_AGENT_WS_URL=${NEXT_PUBLIC_AGENT_WS_URL}

# Environment variables needed at build time (Next.js automatically loads local .env files via COPY . .)
ENV NEXT_TELEMETRY_DISABLED=1
RUN bun run build

# ─────────────────────────────────────────────────────────────────
# Stage 3: Production Runtime
# ─────────────────────────────────────────────────────────────────
FROM oven/bun:1-slim AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Install LibreOffice, ImageMagick, and Ghostscript for liteparse
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice \
        imagemagick \
        ghostscript \
        fonts-liberation \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Allow ImageMagick to process PDFs (bypass default security policy)
RUN sed -i 's|<policy domain="coder" rights="none" pattern="PDF"/>|<policy domain="coder" rights="read\|write" pattern="PDF"/>|' /etc/ImageMagick-6/policy.xml 2>/dev/null || true

# Copy standalone output from builder
COPY --from=builder /app/public ./public
# The standalone build outputs the entrypoint to .next/standalone
COPY --from=builder /app/.next/standalone ./
# Static files MUST be copied manually to the standalone directory
COPY --from=builder /app/.next/static ./.next/static
# Copy liteparse vendor files for PDF processing
COPY --from=builder /app/node_modules/@llamaindex/liteparse ./node_modules/@llamaindex/liteparse

EXPOSE 3000

# Run the standalone server.js using Bun
CMD [ "bun", "run", "server.js"]