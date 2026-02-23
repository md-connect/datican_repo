#!/bin/bash

# Array of file IDs and names
files=(
    "4_z0bec0784b25143bc9ec50f13_f218e9f19d4cf10e5_d20260217_m224859_c003_v0312021_t0002_u01771368539919|DATICAN_Brain_MRI_Dataset.tar.gz|brain-mri"
    "4_z0bec0784b25143bc9ec50f13_f23922b0f02cc15cf_d20260217_m224630_c003_v0312034_t0029_u01771368390592|DATICAN_Breast_Cancer_Dataset.tar.gz|breast-cancer"
    "4_z0bec0784b25143bc9ec50f13_f106bc96abd0948e1_d20260217_m224409_c003_v0312029_t0020_u01771368249473|DATICAN_Chest_Xray_Dataset.tar.gz|chest-xray"
    "4_z0bec0784b25143bc9ec50f13_f2389c1d0b7f6ccd9_d20260217_m224425_c003_v0312030_t0029_u01771368265188|DATICAN_Knee_Xray_Dataset.tar.gz|knee-xray"
    "4_z0bec0784b25143bc9ec50f13_f2522f417cecdfe77_d20260217_m224512_c003_v0312027_t0058_u01771368312385|DATICAN_Spine_MRI_Dataset.tar.gz|spine-mri"
    "4_z0bec0784b25143bc9ec50f13_f1184ff0555c5c007_d20260217_m221632_c003_v0312031_t0030_u01771366592350|DATICAN_Teeth_Dataset.tar.gz|teeth-xray"
)

for file in "${files[@]}"; do
    IFS='|' read -r file_id old_name folder <<< "$file"
    new_path="datasets/$folder/$old_name"
    
    echo "Moving $old_name to $folder..."
    
    # Download
    b2 download-file-by-id "$file_id" "/tmp/$old_name"
    
    # Upload
    b2 upload-file datican-repo "/tmp/$old_name" "$new_path"
    
    # Delete old version
    b2 delete-file-version "$file_id" "datasets/$old_name"
    
    # Clean up
    rm "/tmp/$old_name"
    
    echo "✓ Moved $old_name to $new_path"
    echo "---"
done

echo "All files moved successfully!"