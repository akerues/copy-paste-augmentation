import os
import glob
import yaml
from PyQt6.QtGui import QImageReader

def load_classes(yaml_path):
    class_map = {}
    if yaml_path and os.path.exists(yaml_path):
        try:
            with open(yaml_path, 'r') as f:
                data = yaml.safe_load(f)
                if 'names' in data:
                    names = data['names']
                    if isinstance(names, list):
                        for idx, name in enumerate(names):
                            class_map[idx] = name
                    elif isinstance(names, dict):
                        for idx, name in names.items():
                            class_map[int(idx)] = name
        except Exception as e:
            print(f"Error reading YAML: {e}")
    return class_map

def parse_yolo_labels(file_path):
    class_counts = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                # First part in YOLO format is the class ID
                try:
                    class_id = int(float(parts[0]))
                    class_counts[class_id] = class_counts.get(class_id, 0) + 1
                except ValueError:
                    continue # Skip invalid lines
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return class_counts

def parse_dataset(directory_path, yaml_path=None):
    class_map = load_classes(yaml_path)
    total_class_counts = {}
    
    # Look for all .txt files inside the 'labels' directory recursively
    labels_dir = os.path.join(directory_path, 'labels')
    if not os.path.exists(labels_dir):
        # Fallback to current directory if 'labels' doesn't exist
        labels_dir = directory_path
        
    txt_files = glob.glob(os.path.join(labels_dir, '**', '*.txt'), recursive=True)
    
    for txt_file in txt_files:
        if os.path.basename(txt_file) == 'classes.txt':
            continue
        
        file_counts = parse_yolo_labels(txt_file)
        for class_id, count in file_counts.items():
            total_class_counts[class_id] = total_class_counts.get(class_id, 0) + count
            
    # Map back to names
    result_counts = {}
    for class_id, count in total_class_counts.items():
        name = class_map.get(class_id, f"Class {class_id}")
        result_counts[name] = count
        
    return result_counts

def get_image_label_pairs(directory_path):
    images_dir = os.path.join(directory_path, 'images')
    labels_dir = os.path.join(directory_path, 'labels')
    
    if not os.path.exists(images_dir) or not os.path.exists(labels_dir):
        return []
        
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(images_dir, '**', f'*{ext}'), recursive=True))
        image_files.extend(glob.glob(os.path.join(images_dir, '**', f'*{ext.upper()}'), recursive=True))
        
    pairs = []
    for img_path in image_files:
        # Find corresponding label file
        rel_path = os.path.relpath(img_path, images_dir)
        base_name, _ = os.path.splitext(rel_path)
        label_path = os.path.join(labels_dir, base_name + '.txt')
        
        if os.path.exists(label_path):
            pairs.append((img_path, label_path))
            
    # Sort pairs to have a consistent order
    pairs.sort(key=lambda x: x[0])
    return pairs

def parse_yolo_boxes_raw(file_path):
    boxes = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 5:
                    try:
                        class_id = int(float(parts[0]))
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        width = float(parts[3])
                        height = float(parts[4])
                        boxes.append((class_id, x_center, y_center, width, height))
                    except ValueError as ve:
                        print(f"ValueError parsing box: {ve}")
                        continue
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return boxes

def convert_labels_to_yolov8(directory_path):
    pairs = get_image_label_pairs(directory_path)
    converted_count = 0
    error_count = 0
    
    for img_path, label_path in pairs:
        try:
            # Get image dimensions efficiently without loading full image
            reader = QImageReader(img_path)
            size = reader.size()
            img_w, img_h = size.width(), size.height()
            
            if img_w <= 0 or img_h <= 0:
                print(f"Skipping {img_path}: invalid dimensions")
                error_count += 1
                continue
                
            new_lines = []
            with open(label_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        try:
                            # Strict integer for class_id
                            class_id = int(float(parts[0]))
                            xc = float(parts[1])
                            yc = float(parts[2])
                            w = float(parts[3])
                            h = float(parts[4])
                            
                            # Normalize absolute coordinates
                            if w > 1.1 or h > 1.1 or xc > 1.1 or yc > 1.1:
                                xc = xc / img_w
                                yc = yc / img_h
                                w = w / img_w
                                h = h / img_h
                                
                            # Clamp values to 0.0 - 1.0 (good practice for YOLO)
                            xc = max(0.0, min(1.0, xc))
                            yc = max(0.0, min(1.0, yc))
                            w = max(0.0, min(1.0, w))
                            h = max(0.0, min(1.0, h))
                            
                            new_lines.append(f"{class_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
                        except ValueError:
                            continue
                            
            # Write back strictly
            with open(label_path, 'w') as f:
                f.writelines(new_lines)
            converted_count += 1
            
        except Exception as e:
            print(f"Error converting {label_path}: {e}")
            error_count += 1
            
    return converted_count, error_count
