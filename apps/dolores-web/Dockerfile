# Build stage
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# This script copies assets to public/vad/ which Vite then bundles into dist/vad/
RUN npm run build

# Production stage
FROM nginx:1.27-alpine
# Copy the entire dist folder (which already contains the 'vad' subfolder)
# We copy it to /usr/share/nginx/html/app so that /app/ requests find it perfectly.
COPY --from=build /app/dist /usr/share/nginx/html/app
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
