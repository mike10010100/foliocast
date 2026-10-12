#!/usr/bin/env bash
# ==============================================================================
# Script: install_kindle_usb.sh
# Purpose: Compiles the static Kindle ARM client and installs the launcher
#          and binary directly to a USB-connected Kindle Paperwhite.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

KINDLE_DIR="${1:-}"

# Auto-detect Kindle mount point if not explicitly passed
if [[ -z "${KINDLE_DIR}" ]]; then
    CANDIDATES=(
        "/media/${USER}/Kindle"
        "/run/media/${USER}/Kindle"
        "/media/Kindle"
        "/Volumes/Kindle"
    )
    for cand in "${CANDIDATES[@]}"; do
        if [[ -d "${cand}/documents" ]]; then
            KINDLE_DIR="${cand}"
            break
        fi
    done
fi

if [[ -z "${KINDLE_DIR}" || ! -d "${KINDLE_DIR}/documents" ]]; then
    echo "======================================================================"
    echo "🔍 Waiting for Kindle USB Connection..."
    echo "======================================================================"
    echo "Please plug your Kindle Paperwhite into this machine over USB."
    echo ""
    echo "If your Kindle is already mounted at a custom path, run:"
    echo "  $0 /path/to/Kindle"
    echo ""
    echo "Checking common mount locations:"
    echo "  - /media/${USER}/Kindle"
    echo "  - /run/media/${USER}/Kindle"
    echo "  - /Volumes/Kindle"
    echo "======================================================================"
    exit 1
fi

echo "======================================================================"
echo "📖 FolioCast: Installing to Kindle at: ${KINDLE_DIR}"
echo "======================================================================"

VERSION=$(tr -d '[:space:]' < VERSION 2>/dev/null || echo "1.0.0")

# 1. Compile static ARMv7 binary
echo "🔨 Compiling static ARM binary (v${VERSION})..."
mkdir -p build
PUB=""
if [[ -s "secrets/ota_ed25519.key" ]]; then
    PUB=$(go -C client-go run ./cmd/otasign pubkey -key "${ROOT_DIR}/secrets/ota_ed25519.key" 2>/dev/null || true)
fi

CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -C client-go \
    -ldflags="-s -w -X main.Version=${VERSION} -X main.OTAPublicKey=${PUB}" \
    -o "${ROOT_DIR}/build/foliocast-arm" .

# 2. Copy launcher scripts to documents folder
DOCUMENTS_DIR="${KINDLE_DIR}/documents"
echo "📂 Copying launcher to ${DOCUMENTS_DIR}/FolioCast.sh..."
cp client-go/launcher/FolioCast.sh "${DOCUMENTS_DIR}/FolioCast.sh"
chmod +x "${DOCUMENTS_DIR}/FolioCast.sh" 2>/dev/null || true

# Also create TransitTracker.sh compatibility copy in documents
cp client-go/launcher/FolioCast.sh "${DOCUMENTS_DIR}/TransitTracker.sh"
chmod +x "${DOCUMENTS_DIR}/TransitTracker.sh" 2>/dev/null || true

# 3. Stage the binary in documents (both primary and backup for immediate offline boot)
echo "📦 Staging binary at ${DOCUMENTS_DIR}/foliocast-arm..."
cp build/foliocast-arm "${DOCUMENTS_DIR}/foliocast-arm"
cp build/foliocast-arm "${DOCUMENTS_DIR}/foliocast_backup"
chmod +x "${DOCUMENTS_DIR}/foliocast-arm" "${DOCUMENTS_DIR}/foliocast_backup" 2>/dev/null || true

# Optional server configuration argument
SERVER_URL="${2:-}"
if [[ -n "${SERVER_URL}" ]]; then
    echo "${SERVER_URL}" > "${DOCUMENTS_DIR}/foliocast_server.txt"
    echo "🌐 Configured server URL: ${SERVER_URL}"
fi

# 4. Flush writes to USB
echo "💾 Flushing disk buffers (sync)..."
sync

echo "======================================================================"
echo "✅ Installation Complete!"
echo "======================================================================"
echo "Next steps:"
echo "  1. Safely eject the Kindle from your system:"
echo "     eject ${KINDLE_DIR} (or click Eject in file manager)"
echo "  2. Unplug the USB cable."
echo "  3. Open your Kindle Library and tap 'FolioCast' (or 'Transit Tracker')."
echo "======================================================================"
