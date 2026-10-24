FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# `vite preview` serves the production build and proxies /api to the backend,
# so no separate web server is needed for this local-only setup.
EXPOSE 5173
CMD ["npm", "run", "preview"]
