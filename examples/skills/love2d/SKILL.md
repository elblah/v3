---
name: love2d-game-dev
description: Löve2d Game development essential tips (like how to create screenshots, run in xvfb, etc)
---

# Screenshot

Capture screenshots for visual debugging:

```lua
love.graphics.captureScreenshot('/path/to/save/filename.png')
```

Analyze the screenshot with:
```python
read_image(path="/path/to/save/filename.png")
```

**How it works:**
- **Vision models** (`AICODER_FULL_VISION=1`): Model sees actual image
- **Non-vision models**: Image converted to ASCII via chafa, model sees text

The `read_image` tool works for both model types.

# X11 Display

Love2d needs a display. Use one of these approaches:

## Option 1: With Xvfb (Headless, Screenshot supported, simple run script):

```bash
xvfb-run bash -c 'love . & x=$!; sleep 5; xdotool key --repeat 25 a; scrot -u; kill $x'
```

## Option 2: With Xvfb (Headless, Screenshots Supported)

Use this method only if xvfb-run is not ok

```bash
# Find a free display number
DISPLAY_NUM=99
while [ -e /tmp/.X$DISPLAY_NUM-lock ]; do
    DISPLAY_NUM=$((DISPLAY_NUM + 1))
done

# Start Xvfb and run Love2d
Xvfb :$DISPLAY_NUM -screen 0 1024x768x24 &
xpid=$!
sleep 5  # Wait for Xvfb startup
DISPLAY=:$DISPLAY_NUM timeout -k 2s 10s love .
kill -9 $xpid
```

## Option 3: just run love .

Important depending on the environment the user might need to run `xhost +`. This usually happens when the aicoder is running inside a sandbox like bwrap.

```bash
love .
```

**Note:** Without X11, `love.graphics.captureScreenshot()` will fail. Use Option 1 if you need screenshot capability.
