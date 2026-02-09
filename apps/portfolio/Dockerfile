# syntax=docker/dockerfile:1
FROM nginx:1.25-alpine

# Copy static files
COPY src/ /usr/share/nginx/html/

# Custom nginx config for SPA routing and caching
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:80/health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
