# AGENTS.md - portfolio

Static personal portfolio site.

## Project Overview
- **Role:** Personal portfolio hosting.
- **Tech Stack:** Static HTML/JS/CSS, Nginx.

## Build and Run
- **Dev mode:** Simply open `index.html` or use `live-server`.
- **Production Build:** Files are copied to `/usr/share/nginx/html` in Docker.

## Structure
- `src/`: Static assets (JS, CSS, Images).
- `nginx.conf`: Configuration for production serving.

## Testing Instructions
- **Validators:** Use HTML5/CSS3 validators for style checks.
- **Responsiveness:** Check with modern mobile and desktop viewports.

## Deployment Notes
- This app is stateless and serves static content only.
- Managed primarily via Docker and Nginx.
