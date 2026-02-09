# Portfolio

A geeky personal portfolio site with multiple switchable themes.

## Features

- **4 Themes**: Terminal, Cyberpunk, Circuit Board, Dracula
- **Live Theme Switching**: Click buttons or press 1-4 keys
- **Vim-style Navigation**: j/k to scroll, gg to top, G to bottom
- **Easter Eggs**: Konami code (↑↑↓↓←→←→BA), console messages
- **Responsive Design**: Works on mobile and desktop
- **Static Site**: Pure HTML/CSS/JS, served via nginx

## Local Development

```bash
# Using Python's built-in server
cd src && python -m http.server 8080

# Or with Docker
docker build -t portfolio .
docker run -p 8080:80 portfolio
```

## Customization

Edit `src/index.html` to update:
- Your name and bio in the hero section
- Skills in the skills section
- Projects in the projects section
- Contact links in the contact section

Edit `src/styles.css` to customize:
- Theme colors (CSS variables at the top)
- Fonts and typography
- Layout and spacing

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `j` | Scroll down |
| `k` | Scroll up |
| `gg` | Go to top |
| `G` | Go to bottom |
| `1-4` | Switch themes |

## Easter Eggs

- **Konami Code**: ↑↑↓↓←→←→BA triggers Matrix rain
- **Console**: Open DevTools for a hidden message
