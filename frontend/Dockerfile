# Multi-stage: build with Node, serve static files with nginx.
# Base images pinned by digest (dependency-hygiene audit: floating tags drift
# silently). Refresh with: curl -s https://hub.docker.com/v2/repositories/library/<image>/tags/<tag> | jq .digest
FROM node:24-alpine@sha256:50c8e8ca1d27439048670df5883f32d57cf81cff6233222c893fd0d9884cbd81 AS build
WORKDIR /app
# .npmrc carries engine-strict, so the image honours the same Node floor as
# local dev and CI rather than building on whatever the base tag drifted to.
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginx:1.31-alpine@sha256:72ba65eb42c10344912a84ff42408db7d34f2feb642204570ab8fc5ffd29f1d3
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
