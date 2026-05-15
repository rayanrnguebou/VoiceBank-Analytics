# VOICEBANK ANALYTICS - Dockerfile Interface React
# Auteur : Nguebou Temgoua Rayan

# Etape 1 : Build React
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Etape 2 : Serveur Nginx pour servir le build
FROM nginx:alpine

# Copier le build React
COPY --from=builder /app/build /usr/share/nginx/html

# Configuration Nginx pour React Router
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
