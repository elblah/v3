---
name: love2d-game-dev
description: Löve2d Game development essential tips (like how to create screenshots, run in xvfb, etc)
---

# Screenshot

love.graphics.captureScreenshot('/path/to/save/filename.png')

# X11

You can try to run Love2d... if you can't run it because of X11 problems you can use Xvfb

example script:
# MAKE SURE TO USE A FREE DISPLAY NUMBER
# :99 IS JUST AN EXAMPLE NOT A FIXED RULE
# USER WHATEVER NUMBER IS FREE!!!
Xvfb :99 -screen 0 1024x768x24 &
xpid=$!
sleep 5 # wait Xvfb startup
DISPLAY=:99 timeout -k 2s 10s love .
kill -9 $xpid
