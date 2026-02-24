#!/bin/bash
# upload_to_b2.sh - Safe upload to B2 (no accidental duplicate versions)

if [ $# -lt 1 ]; then
    echo "Usage: $0 <local_file> [--force]"
    exit 1
fi

LOCAL_FILE=$1
FORCE=$2

if [ ! -f "$LOCAL_FILE" ]; then
    echo "❌ File does not exist: $LOCAL_FILE"
    exit 1
fi

FILENAME=$(basename "$LOCAL_FILE")
B2_PATH="datasets/teeth-xray-2/$FILENAME"
BUCKET="datican-repo"

echo "📦 Preparing upload: $LOCAL_FILE"
echo "Target: $B2_PATH"

# Check if file already exists in B2
EXISTS=$(b2 ls "b2://$BUCKET/datasets/teeth-xray-2" | grep -w "$FILENAME")

if [ -n "$EXISTS" ] && [ "$FORCE" != "--force" ]; then
    echo "⚠️ File already exists in B2."
    echo "Skipping upload to prevent duplicate version."
    echo "Use --force to overwrite."
    exit 0
fi

echo "🚀 Uploading..."

b2 file upload --threads 10 "$BUCKET" "$LOCAL_FILE" "$B2_PATH"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Upload complete!"
    echo ""
    echo "📋 Copy this path to Django Admin:"
    echo "   $B2_PATH"
    echo ""
    echo "🔗 Temporary signed URL (valid 1 hour):"
    b2 file url --with-auth --duration 3600 "b2://$BUCKET/$B2_PATH"
else
    echo "❌ Upload failed"
    exit 1
fi
