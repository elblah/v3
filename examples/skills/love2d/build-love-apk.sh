#!/bin/bash

# Build LÖVE APK from .love file
# Requires: apktool, apksigner, keytool (default-jdk), wget, rsvg-convert (optional)
# Usage: ./build-love-apk.sh game.love [output.apk]
# Options:
#   --package NAME         Package name (REQUIRED - e.g., com.studio.gamename)
#   --app-name NAME        App display name (REQUIRED - e.g., "Space Invaders")
#   --orientation ORIENT   Screen orientation: portrait or landscape (default: unchanged)
#   --manifest FILE        Custom AndroidManifest.xml to use
#   --icon FILE            SVG icon to convert to adaptive icon format
#   --clean                Force fresh download and decompile

set -e

LOVE_FILE=""
OUTPUT_APK=""
PACKAGE_NAME=""
APP_NAME=""
ORIENTATION=""
MANIFEST_FILE=""
ICON_FILE=""
FORCE_CLEAN=false

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --package)
            PACKAGE_NAME="$2"
            shift 2
            ;;
        --app-name)
            APP_NAME="$2"
            shift 2
            ;;
        --orientation)
            ORIENTATION="$2"
            shift 2
            ;;
        --manifest)
            MANIFEST_FILE="$2"
            shift 2
            ;;
        --icon)
            ICON_FILE="$2"
            shift 2
            ;;
        --clean)
            FORCE_CLEAN=true
            shift
            ;;
        *.love)
            LOVE_FILE="$1"
            shift
            ;;
        *.apk)
            OUTPUT_APK="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Check arguments
if [ -z "$LOVE_FILE" ]; then
    echo "Usage: $0 game.love [output.apk]"
    echo "Options:"
    echo "  --package NAME         Package name (REQUIRED - e.g., com.studio.gamename)"
    echo "  --app-name NAME        App display name (REQUIRED - e.g., \"Space Invaders\")"
    echo "  --orientation ORIENT   Screen orientation: portrait or landscape"
    echo "  --manifest FILE        Custom AndroidManifest.xml to use"
    echo "  --icon FILE            SVG icon to convert to adaptive icon format"
    echo "  --clean                Force fresh download and decompile"
    exit 1
fi

if [ -z "$PACKAGE_NAME" ]; then
    echo "Error: --package is required (e.g., --package com.studio.gamename)"
    exit 1
fi

if [ -z "$APP_NAME" ]; then
    echo "Error: --app-name is required (e.g., --app-name \"Space Invaders\")"
    exit 1
fi

if [ ! -f "$LOVE_FILE" ]; then
    echo "Error: $LOVE_FILE not found"
    exit 1
fi

# Validate orientation
if [ -n "$ORIENTATION" ] && [ "$ORIENTATION" != "portrait" ] && [ "$ORIENTATION" != "landscape" ]; then
    echo "Error: orientation must be 'portrait' or 'landscape'"
    exit 1
fi

# Check dependencies
MISSING_DEPS=""

if ! command -v apktool &> /dev/null; then
    MISSING_DEPS="$MISSING_DEPS apktool"
fi

if ! command -v keytool &> /dev/null; then
    MISSING_DEPS="$MISSING_DEPS keytool (default-jdk)"
fi

if ! command -v apksigner &> /dev/null; then
    MISSING_DEPS="$MISSING_DEPS apksigner"
fi

if ! command -v wget &> /dev/null; then
    MISSING_DEPS="$MISSING_DEPS wget"
fi

if [ -n "$ICON_FILE" ] && ! command -v rsvg-convert &> /dev/null; then
    MISSING_DEPS="$MISSING_DEPS rsvg-convert (librsvg2-bin)"
fi

if [ -n "$MISSING_DEPS" ]; then
    echo "Error: Missing dependencies:$MISSING_DEPS"
    echo ""
    echo "Install with:"
    echo "  sudo apt install apktool apksigner default-jdk wget"
    [ -n "$ICON_FILE" ] && echo "  sudo apt install librsvg2-bin  # for SVG icon support"
    exit 1
fi

# Set defaults
GAME_NAME=$(basename "$LOVE_FILE" .love)
OUTPUT_APK="${OUTPUT_APK:-${GAME_NAME}.apk}"

# Working directories
TMP_DIR="./tmp"
LOVE_APK_URL="https://github.com/love2d/love-android/releases/download/11.5a/love-11.5-android-embed.apk"
LOVE_APK="$TMP_DIR/love-11.5-android-embed.apk"
DECODED_DIR="$TMP_DIR/love-decoded"
KEYSTORE="$TMP_DIR/debug.keystore"
KEYSTORE_PASS="android"
KEY_ALIAS="androiddebugkey"

echo "Building APK for: $LOVE_FILE"
echo "Package: $PACKAGE_NAME"
echo "App name: $APP_NAME"
[ -n "$ORIENTATION" ] && echo "Orientation: $ORIENTATION"
[ -n "$MANIFEST_FILE" ] && echo "Custom manifest: $MANIFEST_FILE"
[ -n "$ICON_FILE" ] && echo "Icon: $ICON_FILE"
[ "$FORCE_CLEAN" = true ] && echo "Clean build: yes"
echo ""

# Create tmp directory
mkdir -p "$TMP_DIR"

# Clean if requested
if [ "$FORCE_CLEAN" = true ]; then
    echo "Cleaning tmp directory..."
    rm -rf "$LOVE_APK" "$DECODED_DIR"
fi

# Download LÖVE APK if not exists
if [ ! -f "$LOVE_APK" ]; then
    echo "Downloading LÖVE APK..."
    wget -q "$LOVE_APK_URL" -O "$LOVE_APK"
else
    echo "LÖVE APK already downloaded"
fi

# Decode APK if not already decoded
if [ ! -d "$DECODED_DIR" ]; then
    echo "Decoding APK with apktool..."
    apktool d -s -o "$DECODED_DIR" "$LOVE_APK"
else
    echo "APK already decoded"
fi

# Copy game.love to assets
echo "Copying game file..."
mkdir -p "$DECODED_DIR/assets"
cp "$LOVE_FILE" "$DECODED_DIR/assets/game.love"

# Handle manifest
MANIFEST="$DECODED_DIR/AndroidManifest.xml"

if [ -n "$MANIFEST_FILE" ]; then
    if [ ! -f "$MANIFEST_FILE" ]; then
        echo "Error: Manifest file not found: $MANIFEST_FILE"
        exit 1
    fi
    echo "Applying custom AndroidManifest.xml..."
    cp "$MANIFEST_FILE" "$MANIFEST"
fi

# Update package name and app label
echo "Updating package name and app label..."
sed -i "s/package=\"[^\"]*\"/package=\"$PACKAGE_NAME\"/" "$MANIFEST"
sed -i "s/android:label=\"[^\"]*\"/android:label=\"$APP_NAME\"/g" "$MANIFEST"
sed -i "s/android:name=\"[^\"]*\.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION\"/android:name=\"${PACKAGE_NAME}.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION\"/g" "$MANIFEST"
sed -i "s/android:authorities=\"[^\"]*\.androidx-startup\"/android:authorities=\"${PACKAGE_NAME}.androidx-startup\"/g" "$MANIFEST"

# Update orientation if specified
if [ -n "$ORIENTATION" ]; then
    echo "Setting orientation to $ORIENTATION..."
    sed -i "s/android:screenOrientation=\"[^\"]*\"/android:screenOrientation=\"$ORIENTATION\"/g" "$MANIFEST"
fi

# Handle icon conversion
if [ -n "$ICON_FILE" ]; then
    if [ ! -f "$ICON_FILE" ]; then
        echo "Error: Icon file not found: $ICON_FILE"
        exit 1
    fi
    
    echo "Generating launcher icons..."
    
    # Standard launcher icon sizes
    declare -A SIZES=(
        ["mdpi"]=48
        ["hdpi"]=72
        ["xhdpi"]=96
        ["xxhdpi"]=144
        ["xxxhdpi"]=192
    )
    
    for density in "${!SIZES[@]}"; do
        size="${SIZES[$density]}"
        out_dir="$DECODED_DIR/res/drawable-$density"
        mkdir -p "$out_dir"
        echo "  $density: ${size}x${size}"
        rsvg-convert -w "$size" -h "$size" "$ICON_FILE" -o "$out_dir/love.png"
    done
fi

# Create keystore if not exists
if [ ! -f "$KEYSTORE" ]; then
    echo "Creating debug keystore..."
    keytool -genkey -v -keystore "$KEYSTORE" -storepass "$KEYSTORE_PASS" \
        -alias "$KEY_ALIAS" -keypass "$KEYSTORE_PASS" \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=Debug, OU=Debug, O=Debug, L=Debug, S=Debug, C=US" 2>/dev/null
else
    echo "Keystore already exists"
fi

# Build APK
echo "Building APK..."
apktool b -o "$OUTPUT_APK" "$DECODED_DIR"

# Sign APK
echo "Signing APK..."
apksigner sign --ks "$KEYSTORE" --ks-pass "pass:$KEYSTORE_PASS" --key-pass "pass:$KEYSTORE_PASS" "$OUTPUT_APK" 2>/dev/null

echo ""
echo "Done! APK created: $OUTPUT_APK"
ls -la "$OUTPUT_APK"
