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

# Mouse and Touch Events

**Important:** Mouse events in Love2d already capture touch events as well. When developing cross-platform games that support both mouse and touch input, you only need to handle mouse events - touch input is automatically converted to mouse events.

**Why this matters:**
- If you handle both mouse and touch events separately, you'll get **duplicated events**
- Touch on mobile devices will trigger both `touchpressed` and `mousepressed` callbacks
- This can cause unintended double-actions in your game

**Best practice:**
```lua
-- Only handle mouse events - touch is automatically included
function love.mousepressed(x, y, button, istouch, presses)
    -- This is called for both mouse clicks and touch
    if button == 1 then
        -- Handle left click/tap
    end
end

function love.mousereleased(x, y, button, istouch, presses)
    -- Handle release
end

function love.mousemoved(x, y, dx, dy, istouch)
    -- Handle drag
end
```

**Note:** The `istouch` parameter tells you if the event originated from touch or mouse, but you usually don't need to differentiate unless you have touch-specific features.

# Mobile-Specific Setup (Android/iOS)

## Force Portrait Mode

On Android and iOS, you must ensure width and height are in portrait orientation when setting the window mode:

```lua
-- Force portrait orientation on Android
local w, h = 390, 844
if love.system.getOS() == "Android" then
    -- Lock to portrait on Android
    love.window.setMode(w, h, {resizable = false, msaa = 8})
end
```

**Important:**
- `w` and `h` must represent portrait dimensions (width < height)
- If you set landscape dimensions on mobile, the app may not display correctly
- `resizable = false` is recommended for consistent mobile experience
- `msaa = 8` provides anti-aliasing for smoother graphics (adjust as needed for performance)

**Note:** This has been tested on Android. It likely applies to iOS as well, but hasn't been verified.

# Language Detection

Auto-detect the system language and apply it to your game:

```lua
-- Detect system language first, then load saved settings
local detectedLang = detectSystemLanguage()
setLanguage(detectedLang)

-- Auto-detect language from system
local function detectSystemLanguage()
    -- Try love.system.getPreferredLocales() first (LÖVE 12+)
    local ok, locales = pcall(function() return love.system.getPreferredLocales() end)
    if ok and locales and #locales > 0 then
        for _, locale in ipairs(locales) do
            -- Extract language code (e.g., "en" from "en_US" or "en")
            local lang = locale:match("^([a-z][a-z])")
            if lang then
                -- Check if we support this language
                for _, supported in ipairs(LanguageList) do
                    if supported == lang then
                        return lang
                    end
                end
            end
        end
    end

    -- Fallback: try os.setlocale() on Unix systems
    local locale = os.setlocale()
    if locale then
        local lang = locale:match("^([a-z][a-z])")
        if lang then
            for _, supported in ipairs(LanguageList) do
                if supported == lang then
                    return lang
                end
            end
        end
    end

    return "en"  -- Default to English
end
```

**How it works:**
1. **Primary method**: Uses `love.system.getPreferredLocales()` (LÖVE 12+) to get the system's preferred language list
2. **Extraction**: Parses locale strings like "en_US" to extract the language code ("en")
3. **Validation**: Checks against your `LanguageList` to ensure you support the detected language
4. **Fallback**: If the modern API isn't available, tries `os.setlocale()` on Unix systems
5. **Default**: Falls back to "en" (English) if nothing matches

**Prerequisites:**
- Define a `LanguageList` table with your supported language codes:
  ```lua
  LanguageList = {"en", "es", "fr", "de", "ja", "zh", ...}
  ```
- Implement a `setLanguage(lang)` function to apply the detected language

# Reading/Writing Settings

Use `love.filesystem.read()` and `love.filesystem.write()` for reading and writing settings files:

```lua
local SETTINGS_FILE = "settings.json"

-- Read settings file
local content, err = love.filesystem.read(SETTINGS_FILE)
if not content then
    print("Error reading settings:", err)
    -- Use default settings if file doesn't exist
    content = "{}"
end

-- Parse JSON content
local ok, data = pcall(love.data.decode, "json", content)
if not ok then
    print("Error parsing settings JSON:", data)
    data = {}
end

-- Write settings file
local function saveSettings(data)
    local json = love.data.encode("json", data)
    local ok, err = love.filesystem.write(SETTINGS_FILE, json)
    if not ok then
        print("Error writing settings:", err)
    end
end
```

**Important notes:**
- `love.filesystem.read()` returns `nil, error_message` if the file doesn't exist or can't be read
- Always handle the error case - check `if not content then`
- Love2d's filesystem works in a sandboxed save directory specific to your game
- Use `love.filesystem.getInfo(SETTINGS_FILE)` to check if a file exists without reading it
- For JSON, use `love.data.encode("json", data)` and `love.data.decode("json", string)` (LÖVE 11+)

**Full example with language settings:**
```lua
local SETTINGS_FILE = "settings.json"
local LanguageList = {"en", "es", "fr", "de", "ja", "zh"}

local currentLanguage = "en"

local function loadSettings()
    local content, err = love.filesystem.read(SETTINGS_FILE)
    if not content then
        -- File doesn't exist, detect system language
        currentLanguage = detectSystemLanguage()
        return
    end

    local ok, data = pcall(love.data.decode, "json", content)
    if ok and data.language then
        currentLanguage = data.language
    else
        currentLanguage = detectSystemLanguage()
    end
end

local function saveSettings()
    local json = love.data.encode("json", {language = currentLanguage})
    love.filesystem.write(SETTINGS_FILE, json)
end
```
