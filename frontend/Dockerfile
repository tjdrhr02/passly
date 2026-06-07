FROM node:20-alpine AS base
WORKDIR /app
COPY package*.json ./

# ── dev stage ─────────────────────────────────────────────────────────────────
FROM base AS dev
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host"]

# ── builder stage ─────────────────────────────────────────────────────────────
FROM base AS builder
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}
RUN npm ci
COPY . .
RUN npm run build

# ── production stage ──────────────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/dist ./dist
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
