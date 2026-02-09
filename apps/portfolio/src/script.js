/**
 * Portfolio - Interactive JavaScript
 * Theme switching, animations, and easter eggs
 */

(function() {
  'use strict';

  // ============================================
  // THEME MANAGEMENT
  // ============================================

  const STORAGE_KEY = 'portfolio-theme';
  const DEFAULT_THEME = 'mono';

  function initTheme() {
    const savedTheme = localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
    setTheme(savedTheme);
  }

  function setTheme(themeName) {
    document.documentElement.setAttribute('data-theme', themeName);
    localStorage.setItem(STORAGE_KEY, themeName);
    
    // Update active button
    document.querySelectorAll('.theme-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.theme === themeName);
    });
    
    // Update footer display
    const themeDisplay = document.getElementById('current-theme');
    if (themeDisplay) {
      themeDisplay.textContent = themeName;
    }
    
    // Log to console for devs
    console.log(`%c🎨 Theme switched to: ${themeName}`, 
      `color: ${getComputedStyle(document.documentElement).getPropertyValue('--text-primary')}; font-weight: bold;`);
  }

  function setupThemeSwitcher() {
    document.querySelectorAll('.theme-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        setTheme(btn.dataset.theme);
      });
    });
  }

  // ============================================
  // UPTIME COUNTER
  // ============================================

  function initUptime() {
    const startTime = Date.now();
    const uptimeEl = document.getElementById('uptime');
    
    if (!uptimeEl) return;
    
    function updateUptime() {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      const hours = Math.floor(elapsed / 3600);
      const minutes = Math.floor((elapsed % 3600) / 60);
      const seconds = elapsed % 60;
      
      if (hours > 0) {
        uptimeEl.textContent = `${hours}h ${minutes}m ${seconds}s`;
      } else if (minutes > 0) {
        uptimeEl.textContent = `${minutes}m ${seconds}s`;
      } else {
        uptimeEl.textContent = `${seconds}s`;
      }
    }
    
    updateUptime();
    setInterval(updateUptime, 1000);
  }

  // ============================================
  // DYNAMIC YEAR
  // ============================================

  function initYear() {
    const yearEl = document.getElementById('year');
    if (yearEl) {
      yearEl.textContent = new Date().getFullYear();
    }
  }

  // ============================================
  // TYPING EFFECT FOR TERMINAL
  // ============================================

  function typeText(element, text, speed = 50) {
    return new Promise(resolve => {
      let i = 0;
      element.textContent = '';
      
      function type() {
        if (i < text.length) {
          element.textContent += text.charAt(i);
          i++;
          setTimeout(type, speed);
        } else {
          resolve();
        }
      }
      
      type();
    });
  }

  // ============================================
  // INTERSECTION OBSERVER FOR ANIMATIONS
  // ============================================

  function initScrollAnimations() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -50px 0px'
    });

    document.querySelectorAll('.section').forEach(section => {
      observer.observe(section);
    });
  }

  // ============================================
  // KONAMI CODE EASTER EGG
  // ============================================

  function initKonamiCode() {
    const konamiCode = [
      'ArrowUp', 'ArrowUp', 
      'ArrowDown', 'ArrowDown', 
      'ArrowLeft', 'ArrowRight', 
      'ArrowLeft', 'ArrowRight', 
      'b', 'a'
    ];
    let konamiIndex = 0;

    document.addEventListener('keydown', (e) => {
      if (e.key === konamiCode[konamiIndex]) {
        konamiIndex++;
        
        if (konamiIndex === konamiCode.length) {
          activateEasterEgg();
          konamiIndex = 0;
        }
      } else {
        konamiIndex = 0;
      }
    });
  }

  function activateEasterEgg() {
    console.log('%c🎮 KONAMI CODE ACTIVATED! 🎮', 
      'color: #ff2a6d; font-size: 24px; font-weight: bold; text-shadow: 2px 2px #05d9e8;');
    
    // Create matrix rain effect
    createMatrixRain();
    
    // Show secret message
    showSecretMessage();
  }

  function createMatrixRain() {
    const canvas = document.createElement('canvas');
    canvas.id = 'matrix-rain';
    canvas.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 9998;
      pointer-events: none;
      opacity: 0.8;
    `;
    document.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const chars = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEF';
    const charArray = chars.split('');
    const fontSize = 14;
    const columns = canvas.width / fontSize;
    const drops = Array(Math.floor(columns)).fill(1);

    function draw() {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      ctx.fillStyle = '#39ff14';
      ctx.font = `${fontSize}px monospace`;

      for (let i = 0; i < drops.length; i++) {
        const char = charArray[Math.floor(Math.random() * charArray.length)];
        ctx.fillText(char, i * fontSize, drops[i] * fontSize);

        if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
          drops[i] = 0;
        }
        drops[i]++;
      }
    }

    const interval = setInterval(draw, 33);

    // Remove after 5 seconds
    setTimeout(() => {
      clearInterval(interval);
      canvas.remove();
    }, 5000);
  }

  function showSecretMessage() {
    const message = document.createElement('div');
    message.innerHTML = `
      <div style="
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: rgba(0, 0, 0, 0.9);
        border: 2px solid #39ff14;
        border-radius: 8px;
        padding: 2rem;
        z-index: 10000;
        text-align: center;
        font-family: 'JetBrains Mono', monospace;
        animation: pulse 0.5s ease;
      ">
        <h3 style="color: #39ff14; margin-bottom: 1rem;">🎮 SECRET UNLOCKED! 🎮</h3>
        <p style="color: #7ee787;">You found the easter egg!</p>
        <p style="color: #58a6ff; font-size: 0.8rem; margin-top: 1rem;">
          "The Matrix has you..."
        </p>
        <button onclick="this.parentElement.parentElement.remove()" style="
          margin-top: 1rem;
          padding: 0.5rem 1rem;
          background: #39ff14;
          color: #0a0e14;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-family: inherit;
        ">Close</button>
      </div>
    `;
    document.body.appendChild(message);
  }

  // ============================================
  // CONSOLE EASTER EGG
  // ============================================

  function initConsoleEasterEgg() {
    console.log(`
%c    _    ____ _   _    ___     _______ ____  
   / \\  / ___| | | |  / \\ \\   / / ____/ ___| 
  / _ \\| |   | |_| | / _ \\ \\ / /|  _| \\___ \\ 
 / ___ \\ |___|  _  |/ ___ \\ V / | |___ ___) |
/_/   \\_\\____|_| |_/_/   \\_\\_/  |_____|____/ 
`, 'color: #39ff14; font-family: monospace;');

    console.log('%c👋 Hey there, fellow developer!', 
      'color: #58a6ff; font-size: 16px; font-weight: bold;');
    
    console.log('%c🔍 Curious about the code? Check out the source!', 
      'color: #7ee787; font-size: 12px;');
    
    console.log('%c🎮 Hint: Try the Konami Code... ↑↑↓↓←→←→BA', 
      'color: #f0883e; font-size: 12px;');
    
    console.log('%c📧 Want to connect? Find me on GitHub!', 
      'color: #bd93f9; font-size: 12px;');
  }

  // ============================================
  // KEYBOARD NAVIGATION (VIM-STYLE)
  // ============================================

  function initKeyboardNav() {
    document.addEventListener('keydown', (e) => {
      // Only if not in an input
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      
      const scrollAmount = 100;
      
      switch(e.key) {
        case 'j':
          window.scrollBy({ top: scrollAmount, behavior: 'smooth' });
          break;
        case 'k':
          window.scrollBy({ top: -scrollAmount, behavior: 'smooth' });
          break;
        case 'g':
          if (e.shiftKey) {
            // G - go to bottom
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
          }
          break;
        case 'Home':
          window.scrollTo({ top: 0, behavior: 'smooth' });
          break;
        case '1':
        case '2':
        case '3':
        case '4':
        case '5':
        case '6':
          // Number keys to switch themes
          const themes = ['mono', 'synthwave', 'paper', 'nord', 'catppuccin', 'gruvbox'];
          const index = parseInt(e.key) - 1;
          if (themes[index]) {
            setTheme(themes[index]);
          }
          break;
      }
    });
    
    // Double-tap 'g' to go to top (vim gg)
    let lastGPress = 0;
    document.addEventListener('keydown', (e) => {
      if (e.key === 'g' && !e.shiftKey) {
        const now = Date.now();
        if (now - lastGPress < 300) {
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        lastGPress = now;
      }
    });
  }

  // ============================================
  // SMOOTH SCROLL FOR ANCHOR LINKS
  // ============================================

  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
      anchor.addEventListener('click', function(e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
          target.scrollIntoView({ behavior: 'smooth' });
        }
      });
    });
  }

  // ============================================
  // INIT
  // ============================================

  function init() {
    initTheme();
    setupThemeSwitcher();
    initUptime();
    initYear();
    initScrollAnimations();
    initKonamiCode();
    initConsoleEasterEgg();
    initKeyboardNav();
    initSmoothScroll();
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
