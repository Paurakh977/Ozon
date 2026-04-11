
FROM node:22-slim AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

FROM base AS deps
WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --config.node-linker=hoisted


FROM base AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY ./ ./
RUN pnpm run build


FROM base AS prod-deps
WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --prod --frozen-lockfile --config.node-linker=hoisted


FROM node:22-slim AS runner
WORKDIR /app

# Install production tools for liteparse AND Java Headless for javaldx warnings
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-java-common \
    default-jre-headless \
    imagemagick \
    ghostscript \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Allow ImageMagick to process PDFs
RUN sed -i 's|<policy domain="coder" rights="none" pattern="PDF"/>|<policy domain="coder" rights="read|write" pattern="PDF"/>|' /etc/ImageMagick-6/policy.xml 2>/dev/null || true

# Create non-root user WITH a real home directory  for LibreOffice cache
RUN groupadd --system --gid 1001 nodejs && \
    useradd --system --uid 1001 --gid nodejs -m -d /home/nodejs nodejs

# Pre-create the DConf and LibreOffice cache directories and grant permissions
# so LibreOffice never throws a Permission Denied error
RUN mkdir -p /home/nodejs/.cache/dconf /home/nodejs/.config/libreoffice && \
    chown -R nodejs:nodejs /home/nodejs

COPY --from=builder --chown=nodejs:nodejs /app/dist ./dist
COPY --from=prod-deps --chown=nodejs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nodejs:nodejs /app/package.json ./

# Explicitly set HOME so LibreOffice knows exactly where to write
ENV HOME=/home/nodejs
ENV NODE_ENV=production
ENV PORT=3001

USER nodejs

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3001/stt', (r) => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "dist/main.js"]