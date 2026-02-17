#!/bin/bash
# upload_to_b2.sh - Upload dataset to B2 and generate admin-ready path
if [ $# -ne 1 ]; then
    echo "Usage: $0 <local_file>"
    echo "Example: $0 breast_cancer_data.tar.gz"
    exit 1
fi

LOCAL_FILE=$1
FILENAME=$(basename "$LOCAL_FILE")
B2_PATH="datasets/$FILENAME"

echo "🚀 Uploading $LOCAL_FILE to B2..."
echo "Target: $B2_PATH"

# Upload with progress
b2 upload-file --threads 10 datican-repo "$LOCAL_FILE" "$B2_PATH"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Upload complete!"
    echo ""
    echo "📋 Copy this path to Django Admin:"
    echo "   $B2_PATH"
    echo ""
    echo "🔗 Direct B2 URL (temporary):"
    b2 get-url "datican-repo" "$B2_PATH"
else
    echo "❌ Upload failed"
    exit 1
fi