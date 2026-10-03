# Phase P5e: serves the static build behind the gateway for `make demo` (repo-root docker-compose.yml).
# Multi-stage: build with Node, serve with a tiny static server so the runtime image stays small.

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:20-alpine AS serve
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /app/dist ./dist
EXPOSE 4173
CMD ["serve", "-s", "dist", "-l", "4173"]
