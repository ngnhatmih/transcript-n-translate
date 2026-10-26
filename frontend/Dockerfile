# Dựng bản tĩnh rồi phục vụ bằng nginx — không chạy Vite/Node trong production.
FROM node:20-alpine AS build

WORKDIR /app

# `npm ci` theo lockfile: image không được cài phiên bản khác với máy đã test.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
