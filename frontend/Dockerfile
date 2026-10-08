# Multi-stage: build with Node, serve static files with nginx.
# Base images pinned by digest (dependency-hygiene audit: floating tags drift
# silently). Refresh with: curl -s https://hub.docker.com/v2/repositories/library/<image>/tags/<tag> | jq .digest
FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /app
# .npmrc carries engine-strict, so the image honours the same Node floor as
# local dev and CI rather than building on whatever the base tag drifted to.
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginx:1.31-alpine@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
