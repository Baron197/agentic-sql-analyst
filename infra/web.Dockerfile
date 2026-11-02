# The web image (Phase 8): the built React app served by Caddy, which also forwards /api to the
# API container and gets the HTTPS certificate. Build from the repo root:
#   docker build -f infra/web.Dockerfile .
FROM node:24.22.2-bookworm-slim AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM caddy:2.11.7-alpine
# Run as a non-root user. The caddy binary carries cap_net_bind_service, so it can still bind
# ports 80 and 443 (compose keeps that one capability and drops the rest).
RUN addgroup -S -g 10002 caddy && adduser -S -D -H -u 10002 -G caddy caddy \
    && chown -R caddy:caddy /data /config
COPY infra/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
USER caddy
