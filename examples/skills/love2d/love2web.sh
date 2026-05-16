#!/bin/bash
# Make a LÖVE game ready for web (with PWA support)
# Usage: ./love2web.sh <game.love>

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$1" ]; then
    echo "Usage: $0 <game.love>"
    exit 1
fi

# Resolve game path
if [[ "$1" = /* ]]; then
    GAME="$1"
else
    GAME="$(pwd)/$1"
fi

if [ ! -f "$GAME" ]; then
    echo "Error: $GAME not found"
    exit 1
fi

GAME_NAME=$(basename "$GAME" .love)
WEB_DIR="${GAME_NAME}-web"

echo "Building web version of: $GAME_NAME"

# Create web directory
mkdir -p "$WEB_DIR"

# Clone love.js if not present
if [ ! -d "love.js-repo" ]; then
    echo "Downloading love.js..."
    git clone --depth=1 https://github.com/2dengine/love.js love.js-repo
fi

# Copy love.js files
echo "Copying love.js files..."
mkdir -p "$WEB_DIR/11.5"
cp love.js-repo/11.5/love.js love.js-repo/11.5/love.wasm "$WEB_DIR/11.5/"
mkdir -p "$WEB_DIR/lua"
cp love.js-repo/lua/*.lua "$WEB_DIR/lua/"
cp love.js-repo/nogame.love "$WEB_DIR/"
cp love.js-repo/player.js "$WEB_DIR/"
cp love.js-repo/style.css "$WEB_DIR/"

# Determine PWA version
if [ -d ".git" ]; then
    PWA_VERSION="v_$(git rev-parse --short HEAD 2>/dev/null || echo '1')"
else
    PWA_VERSION="v_$(date +%s)"
fi

# Copy game
echo "Copying game..."
cp "$GAME" "$WEB_DIR/"

# Create manifest.json for PWA
# To force update: change PWA_VERSION above or touch sw.js
cat > "$WEB_DIR/manifest.json" << EOF
{
  "name": "$GAME_NAME",
  "short_name": "$GAME_NAME",
  "description": "A LÖVE game",
  "start_url": "/index.html",
  "display": "fullscreen",
  "orientation": "portrait",
  "background_color": "#1a1a1a",
  "theme_color": "#1a1a1a",
  "version": "$PWA_VERSION",
  "icons": [
    {
      "src": "icon.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
EOF

# Create service worker with relative paths and update check
cat > "$WEB_DIR/sw.js" << EOF
// VERSION: $PWA_VERSION (auto-generated)
const PWA_VERSION = '$PWA_VERSION';
console.log('SW ' + PWA_VERSION + ' loaded');
const PWA_FILES = [
  'index.html',
  'manifest.json',
  '${GAME_NAME}.love',
  'player.js',
  'style.css',
  '11.5/love.js',
  '11.5/love.wasm',
  'lua/normalize1.lua',
  'lua/normalize2.lua',
  'nogame.love',
  'icon.png'
];

// Install: cache all files, skip waiting
self.addEventListener('install', e => {
  console.log('SW caching files...');
  e.waitUntil(
    caches.open(PWA_VERSION).then(cache => cache.addAll(PWA_FILES)).then(() => {
      console.log('SW all files cached');
    })
  );
  self.skipWaiting();
});

// Activate: claim all clients immediately
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== PWA_VERSION).map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: serve from cache, else fetch and cache for next time
self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(r => {
      if (r) {
        console.log('SW serve from cache:', e.request.url);
        return r;
      }
      console.log('SW fetch from network:', e.request.url);
      return fetch(e.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(PWA_VERSION).then(cache => cache.put(e.request, clone));
          console.log('SW cached:', e.request.url);
        }
        return response;
      }).catch(() => {
        console.log('SW fallback to index.html');
        return caches.match('index.html');
      });
    })
  );
});

EOF

# Create index.html with PWA meta tags
cat > "$WEB_DIR/index.html" << EOF
<!doctype html>
<html lang="en-us">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#1a1a1a">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="$GAME_NAME">
    <title>$GAME_NAME</title>
    <link rel="manifest" href="manifest.json">
    <link rel="apple-touch-icon" href="icon.png">
    <link rel="stylesheet" href="style.css">
  </head>
  <body>
    <canvas id="canvas"></canvas>
    <div id="spinner" class="pending"></div>
    <script src="player.js?g=${GAME_NAME}.love"></script>
    <script>
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('sw.js?v=$PWA_VERSION');
      }
    </script>
  </body>
</html>
EOF

# Create icon (use SVG if exists, else placeholder)
if [ -f "icon.svg" ] && command -v rsvg-convert &> /dev/null; then
    echo "Generating icon..."
    rsvg-convert -w 512 -h 512 icon.svg -o "$WEB_DIR/icon.png"
else
    # Create placeholder icon (1x1 green pixel)
    printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\x00\x00\x00\x00IEND\xaeB`\x82' > "$WEB_DIR/icon.png"
fi

# Create server.py
cat > "$WEB_DIR/server.py" << 'EOF'
#!/usr/bin/env python3
import http.server
import socketserver
import os

PORT = int(os.environ.get('PORT', 8000))

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Last-Modified', '0')
        super().end_headers()

print(f"Open http://localhost:{PORT}")
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
EOF
chmod +x "$WEB_DIR/server.py"

# Copy .htaccess
cp love.js-repo/.htaccess "$WEB_DIR/"

echo ""
echo "Done! To run:"
echo "  cd $WEB_DIR"
echo "  python3 server.py"
echo "  Then open http://localhost:8000"
echo "  On mobile: Add to home screen for PWA install"