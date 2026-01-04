# syntax=docker/dockerfile:1

FROM node:20-alpine AS builder
WORKDIR /app

# Build-time overrides for Vite envs; pass --build-arg to set.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_CLERK_PUBLISHABLE_KEY=pk_test_placeholder
ARG VITE_CLERK_JWT_TEMPLATE=backend
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}
ENV VITE_CLERK_JWT_TEMPLATE=${VITE_CLERK_JWT_TEMPLATE}

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
