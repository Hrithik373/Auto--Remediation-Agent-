# Phase P5e: the console's static build, served by nginx, which also proxies /api to the gateway
# (with buffering off so the SSE live loop streams). Built in LIVE mode (mocks off) for `make demo`;
# pass --build-arg VITE_USE_MOCKS=true for a self-contained mock-mode image.
FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_USE_MOCKS=false
ARG VITE_GRAFANA_URL=http://localhost:3000/d/sentinel-live/sentinel-live-loop?orgId=1&kiosk
ENV VITE_USE_MOCKS=$VITE_USE_MOCKS VITE_GRAFANA_URL=$VITE_GRAFANA_URL
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS serve
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 4173
