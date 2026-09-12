# Multi-stage: build with Node, serve static files with nginx.
# Base images pinned by digest (dependency-hygiene audit: floating tags drift
# silently). Refresh with: curl -s https://hub.docker.com/v2/repositories/library/<image>/tags/<tag> | jq .digest
FROM node:26-alpine@sha256:ef24c5053d50fdc3e4e56eb4e7ddb7861874ab0fdc797046ba897581deb8e868 AS build
WORKDIR /app
# .npmrc carries engine-strict, so the image honours the same Node floor as
# local dev and CI rather than building on whatever the base tag drifted to.
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
