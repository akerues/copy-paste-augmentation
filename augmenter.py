import os
import cv2
import numpy as np
import random
import dataset_parser
import shutil

def apply_crop_augmentations(crop_img):
    """
    Applies random horizontal flip, random brightness, and random rotation to crop.
    """
    # 1. Random Horizontal Flip (50% chance)
    if random.random() < 0.5:
        crop_img = cv2.flip(crop_img, 1)
        
    # 2. Random Brightness adjustment (0.8 to 1.2)
    try:
        hsv = cv2.cvtColor(crop_img, cv2.COLOR_BGR2HSV)
        hsv = np.array(hsv, dtype=np.float64)
        hsv[:, :, 2] = hsv[:, :, 2] * random.uniform(0.8, 1.2)
        hsv[:, :, 2] = np.clip(hsv[:, :, 2], 0, 255)
        hsv = np.array(hsv, dtype=np.uint8)
        crop_img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    except Exception as e:
        print(f"Warning: Brightness adjustment failed, skipping: {e}")
        
    # 3. Random Rotation (-15 to +15 degrees) without clipping boundaries
    try:
        angle = random.uniform(-15, 15)
        h, w = crop_img.shape[:2]
        M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
        
        # Calculate new bounding dimensions
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        
        M[0, 2] += (new_w / 2) - w/2
        M[1, 2] += (new_h / 2) - h/2
        
        crop_img = cv2.warpAffine(crop_img, M, (new_w, new_h), borderMode=cv2.BORDER_REPLICATE)
    except Exception as e:
        print(f"Warning: Rotation failed, skipping: {e}")
        
    return crop_img

def extract_crops(pairs, target_classes):
    """
    Extracts object crops from the dataset for the given target_classes.
    Returns a list of dicts: {'image': numpy_crop, 'class_id': int}
    """
    crops = []
    
    for img_path, label_path in pairs:
        boxes = dataset_parser.parse_yolo_boxes_raw(label_path)
        if not boxes:
            continue
            
        # Check if this image has any targets before loading the heavy image
        has_target = any(b[0] in target_classes for b in boxes)
        if not has_target:
            continue
            
        img = cv2.imread(img_path)
        if img is None:
            continue
            
        h, w = img.shape[:2]
        
        for class_id, xc, yc, box_w, box_h in boxes:
            if class_id in target_classes:
                # Normalize if absolute
                if box_w > 1.1 or box_h > 1.1 or xc > 1.1 or yc > 1.1:
                    xc_norm = xc / w
                    yc_norm = yc / h
                    w_norm = box_w / w
                    h_norm = box_h / h
                else:
                    xc_norm = xc
                    yc_norm = yc
                    w_norm = box_w
                    h_norm = box_h
                    
                x_min = int((xc_norm - w_norm / 2) * w)
                y_min = int((yc_norm - h_norm / 2) * h)
                x_max = int((xc_norm + w_norm / 2) * w)
                y_max = int((yc_norm + h_norm / 2) * h)
                
                # Clamp to image boundaries
                x_min = max(0, x_min)
                y_min = max(0, y_min)
                x_max = min(w, x_max)
                y_max = min(h, y_max)
                
                if x_max > x_min and y_max > y_min:
                    crop = img[y_min:y_max, x_min:x_max].copy()
                    crops.append({'image': crop, 'class_id': class_id})
                    
    return crops

def generate_single_composite(pairs, target_class_id, crops_by_class, global_avg_w_rel, global_avg_h_rel):
    """
    Generates a single composite image and label list in memory.
    """
    class_crops = crops_by_class.get(target_class_id, [])
    if not class_crops:
        return None
        
    crop_dict = random.choice(class_crops)
    crop_img = crop_dict['image'].copy()
    
    # Apply Flip, Brightness, Rotation
    crop_img = apply_crop_augmentations(crop_img)
    
    # Select random background image
    bg_path, bg_label_path = random.choice(pairs)
    bg_img = cv2.imread(bg_path)
    if bg_img is None:
        return None
        
    bg_h, bg_w = bg_img.shape[:2]
    crop_h, crop_w = crop_img.shape[:2]
    
    # Calculate target size: average size of bounding boxes in the background image
    bg_boxes = dataset_parser.parse_yolo_boxes_raw(bg_label_path)
    target_w_px = None
    target_h_px = None
    
    if bg_boxes:
        w_pixels = []
        h_pixels = []
        for _, _, _, bw, bh in bg_boxes:
            if bw <= 1.1 and bh <= 1.1:
                w_pixels.append(bw * bg_w)
                h_pixels.append(bh * bg_h)
            else:
                w_pixels.append(bw)
                h_pixels.append(bh)
        if w_pixels and h_pixels:
            target_w_px = sum(w_pixels) / len(w_pixels)
            target_h_px = sum(h_pixels) / len(h_pixels)
            
    if target_w_px is None or target_h_px is None:
        # Use global average as a fallback
        target_w_px = global_avg_w_rel * bg_w
        target_h_px = global_avg_h_rel * bg_h
        
    # Scale to average size while keeping aspect ratio and adding variation
    scale_w = target_w_px / crop_w
    scale_h = target_h_px / crop_h
    scale = (scale_w + scale_h) / 2.0
    scale *= random.uniform(0.85, 1.15) # natural scale variation
    
    # Prevent excessive scaling
    min_scale = max(0.05 * bg_w / crop_w, 0.05 * bg_h / crop_h)
    max_scale = min(0.60 * bg_w / crop_w, 0.60 * bg_h / crop_h)
    scale = max(min_scale, min(scale, max_scale))
    
    new_w = int(crop_w * scale)
    new_h = int(crop_h * scale)
    
    if new_w <= 0 or new_h <= 0:
        return None
        
    crop_img = cv2.resize(crop_img, (new_w, new_h))
    crop_h, crop_w = crop_img.shape[:2]
    
    # Random position
    max_x = bg_w - crop_w
    max_y = bg_h - crop_h
    if max_x <= 0 or max_y <= 0:
        return None
        
    paste_x = random.randint(0, max_x)
    paste_y = random.randint(0, max_y)
    
    # Paste image
    bg_img[paste_y:paste_y+crop_h, paste_x:paste_x+crop_w] = crop_img
    
    # Calculate new YOLO bounding box
    new_xc = (paste_x + crop_w / 2.0) / bg_w
    new_yc = (paste_y + crop_h / 2.0) / bg_h
    new_nw = crop_w / bg_w
    new_nh = crop_h / bg_h
    
    new_label_line = f"{target_class_id} {new_xc:.6f} {new_yc:.6f} {new_nw:.6f} {new_nh:.6f}\n"
    
    # Read original labels to append
    original_labels = []
    if os.path.exists(bg_label_path):
        with open(bg_label_path, 'r') as f:
            original_labels = f.readlines()
            
    original_labels.append(new_label_line)
    
    # Generate proposed filenames (based on background file name)
    base_name, ext = os.path.splitext(os.path.basename(bg_path))
    suffix = random.randint(1000, 9999)
    new_img_name = f"{base_name}_aug_{suffix}{ext}"
    new_label_name = f"{base_name}_aug_{suffix}.txt"
    
    return bg_img, original_labels, new_img_name, new_label_name

def generate_augmented_images(dir_path, target_counts, progress_callback=None):
    """
    Generates new composite images and saves them in the .aug_staging subfolder.
    """
    staging_dir = os.path.join(dir_path, '.aug_staging')
    staging_images = os.path.join(staging_dir, 'images')
    staging_labels = os.path.join(staging_dir, 'labels')
    
    # Re-create staging folder cleanly
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_images, exist_ok=True)
    os.makedirs(staging_labels, exist_ok=True)
    
    pairs = dataset_parser.get_image_label_pairs(dir_path)
    if not pairs:
        return 0
        
    target_classes = set(target_counts.keys())
    
    if progress_callback:
        progress_callback("Extracting instances...", 10)
        
    crops = extract_crops(pairs, target_classes)
    if not crops:
        return 0
        
    crops_by_class = {c: [] for c in target_classes}
    for c in crops:
        crops_by_class[c['class_id']].append(c)
        
    # Calculate global average relative size
    global_w_rels = []
    global_h_rels = []
    for _, lp in pairs:
        boxes = dataset_parser.parse_yolo_boxes_raw(lp)
        for _, _, _, bw, bh in boxes:
            if bw <= 1.1 and bh <= 1.1:
                global_w_rels.append(bw)
                global_h_rels.append(bh)
                
    if global_w_rels:
        global_avg_w_rel = sum(global_w_rels) / len(global_w_rels)
        global_avg_h_rel = sum(global_h_rels) / len(global_h_rels)
    else:
        global_avg_w_rel = 0.15
        global_avg_h_rel = 0.15

    generated_count = 0
    total_needed = sum(target_counts.values())
    current_done = 0
    
    for class_id, needed in target_counts.items():
        for _ in range(needed):
            res = generate_single_composite(pairs, class_id, crops_by_class, global_avg_w_rel, global_avg_h_rel)
            if res is None:
                continue
                
            bg_img, labels, new_img_name, new_label_name = res
            
            # Save to staging folder
            out_img_path = os.path.join(staging_images, new_img_name)
            out_label_path = os.path.join(staging_labels, new_label_name)
            
            cv2.imwrite(out_img_path, bg_img)
            with open(out_label_path, 'w') as f:
                f.writelines(labels)
                
            generated_count += 1
            current_done += 1
            
            if progress_callback:
                progress = 10 + int(90 * (current_done / total_needed))
                progress_callback(f"Generated {current_done}/{total_needed} images...", progress)
                
    return generated_count

def generate_single_replacement(dir_path, rejected_img_path, rejected_label_path):
    """
    Regenerates a single composite image and overwrites the rejected staging files directly in place.
    """
    # 1. Determine target class ID by reading the last line of the rejected label file
    if not os.path.exists(rejected_label_path):
        return False
        
    try:
        with open(rejected_label_path, 'r') as f:
            lines = f.readlines()
        if not lines:
            return False
        last_line = lines[-1].strip().split()
        if not last_line:
            return False
        class_id = int(float(last_line[0]))
    except Exception as e:
        print(f"Failed to parse class ID from rejected label: {e}")
        return False
        
    pairs = dataset_parser.get_image_label_pairs(dir_path)
    if not pairs:
        return False
        
    crops = extract_crops(pairs, {class_id})
    if not crops:
        return False
        
    crops_by_class = {class_id: crops}
    
    # Calculate global averages
    global_w_rels = []
    global_h_rels = []
    for _, lp in pairs:
        boxes = dataset_parser.parse_yolo_boxes_raw(lp)
        for _, _, _, bw, bh in boxes:
            if bw <= 1.1 and bh <= 1.1:
                global_w_rels.append(bw)
                global_h_rels.append(bh)
                
    if global_w_rels:
        global_avg_w_rel = sum(global_w_rels) / len(global_w_rels)
        global_avg_h_rel = sum(global_h_rels) / len(global_h_rels)
    else:
        global_avg_w_rel = 0.15
        global_avg_h_rel = 0.15
        
    # Generate new composite
    res = generate_single_composite(pairs, class_id, crops_by_class, global_avg_w_rel, global_avg_h_rel)
    if res is None:
        return False
        
    bg_img, labels, _, _ = res
    
    # Overwrite rejected files directly in-place
    cv2.imwrite(rejected_img_path, bg_img)
    with open(rejected_label_path, 'w') as f:
        f.writelines(labels)
        
    return True
