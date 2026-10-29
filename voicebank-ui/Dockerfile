# VoiceBank Analytics — Interface React (construite avec Vite, servie par nginx)
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js tailwind.config.cjs postcss.config.cjs ./
COPY public ./public
COPY src ./src
ARG REACT_APP_API_URL=http://localhost:8000
ARG REACT_APP_POWER_BI_URL=
ENV REACT_APP_API_URL=$REACT_APP_API_URL REACT_APP_POWER_BI_URL=$REACT_APP_POWER_BI_URL
RUN npm run build

FROM nginx:1.27-alpine
ARG REACT_APP_API_URL=http://localhost:8000
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i "s#__API_URL__#${REACT_APP_API_URL}#g" /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
