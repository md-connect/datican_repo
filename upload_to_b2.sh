#!/bin/bash
# upload_to_b2.sh - Reliable multi-dataset upload to B2 using rclone
# Usage:
#   ./upload_to_b2.sh <remote-folder1> <local-file1> [<remote-folder2> <local-file2> ...]

# === CONFIGURATION ===
# Name of the rclone remote you configured for B2
RCLONE_REMOTE="datican-b2"

# === CHECK INPUT ===
if [ $# -lt 2 ] || [ $(($# % 2)) -ne 0 ]; then
    echo "Usage: $0 <remote-folder1> <local-file1> [<remote-folder2> <local-file2> ...]"
    exit 1
fi

# === FUNCTION TO UPLOAD ONE FILE ===
upload_file() {
    local remote_folder="$1"
    local local_file="$2"

    if [ ! -f "$local_file" ]; then
        echo "❌ Local file not found: $local_file"
        return 1
    fi

    remote_path="datican-repo/datasets/$remote_folder/$(basename "$local_file")"
    echo "📦 Uploading $local_file → $remote_path"

    rclone copy "$local_file" "$RCLONE_REMOTE:$remote_path" -P --verbose
    if [ $? -eq 0 ]; then
        echo "✅ Upload completed: $local_file → $remote_path"
    else
        echo "❌ Upload failed: $local_file → $remote_path"
    fi
}

# === LOOP OVER ARGUMENT PAIRS ===
while [ $# -gt 0 ]; do
    REMOTE_FOLDER="$1"
    LOCAL_FILE="$2"
    upload_file "$REMOTE_FOLDER" "$LOCAL_FILE"
    shift 2
done