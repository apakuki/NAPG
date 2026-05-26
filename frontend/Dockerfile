# syntax=docker/dockerfile:1

# NAPG frontend — public Next.js 16 app, built to a standalone server.
FROM node:22-bookworm-slim AS build
WORKDIR /app

# NEXT_PUBLIC_* values are inlined into the client bundle at build time, so
# they must be present during `next build`. Default to the keyless public Base
# endpoints so no API key ever leaks into the browser bundle; override with
# --build-arg only if you deliberately want a private RPC on the client.
ARG NEXT_PUBLIC_BASE_RPC_URL=https://mainnet.base.org
ARG NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
ENV NEXT_PUBLIC_BASE_RPC_URL=$NEXT_PUBLIC_BASE_RPC_URL \
    NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL=$NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL \
    NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1

RUN useradd --create-home --uid 10001 nextjs

# Standalone output bundles a minimal server.js + traced node_modules. The
# tracer does not copy public/ or .next/static, so add them explicitly.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
