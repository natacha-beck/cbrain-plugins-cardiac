#!/usr/bin/env python3
import os
import sys
import argparse
import warnings
from pathlib import Path


import cv2
import matplotlib.pyplot as plt
import numpy as np
import pytesseract
from pytesseract import Output
from sklearn.cluster import KMeans

warnings.filterwarnings('ignore')
os.environ['LOKY_MAX_CPU_COUNT'] = '1'

def get_text_mask(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    d = pytesseract.image_to_data(gray, output_type=Output.DICT)

    mask = np.zeros_like(gray, dtype=np.uint8)
    n_boxes = len(d['level'])

    for i in range(n_boxes):
        (x, y, w, h, text) = (d['left'][i], d['top'][i], d['width'][i], d['height'][i], d['text'][i])
        if text.strip() != "":
            cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)

    return mask

# === 1. CLAHE Enhancer ===
def apply_clahe_to_bgr(image):
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))
    enhanced_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    return enhanced_img

# === 2. Colored Annotation Mask via HSV + KMeans ===
def get_annotation_mask_kmeans_clahe(image, k=3, sat_thresh=20, min_area=20):
    image_clahe = apply_clahe_to_bgr(image)
    hsv = cv2.cvtColor(image_clahe, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    mask_color = s > sat_thresh
    pixels = hsv[mask_color]

    if len(pixels) < k:
        return np.zeros(image.shape[:2], dtype=np.uint8)

    kmeans = KMeans(n_clusters=k, random_state=42)
    labels = kmeans.fit_predict(pixels)
    centers = kmeans.cluster_centers_

    mask_result = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for i, center in enumerate(centers):
        h_c, s_c, v_c = center
        if s_c > sat_thresh and v_c > 20:
            match_mask = (labels == i)
            color_pixels_idx = np.where(mask_color)
            mask_result[color_pixels_idx[0][match_mask], color_pixels_idx[1][match_mask]] = 255

    num_labels, labels_img, stats, _ = cv2.connectedComponentsWithStats(mask_result, connectivity=8)
    cleaned_mask = np.zeros_like(mask_result)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            cleaned_mask[labels_img == i] = 255

    return cleaned_mask

# === 3. Grayscale Annotation Mask via Canny + Contour Filtering ===
#def get_grayscale_annotation_mask(image, min_area=30, max_area=2000):
def get_grayscale_annotation_mask(image, min_area=100, max_area=1000):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    edges = cv2.Canny(enhanced, 50, 150)
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if min_area < area < max_area:
            cv2.drawContours(mask, [cnt], -1, 255, -1)
    return mask

# === 4. Combine Masks ===
def get_combined_annotation_mask(image, k=3, sat_thresh=40, color_min_area=20, gray_min_area=30, gray_max_area=2000):
    color_mask = get_annotation_mask_kmeans_clahe(image, k=k, sat_thresh=sat_thresh, min_area=color_min_area)
    gray_mask = get_grayscale_annotation_mask(image, min_area=gray_min_area, max_area=gray_max_area)
    text_mask = get_text_mask(image)

    combined_mask = cv2.bitwise_or(color_mask, gray_mask)
    combined_mask = cv2.bitwise_or(combined_mask, text_mask)
    return combined_mask

# === 5. Inpainting ===
def clean_and_inpaint(image, mask, radius=3):
    kernel = np.ones((5, 5), np.uint8)
    mask_clean = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_OPEN, kernel)
    result = cv2.inpaint(image, mask_clean, inpaintRadius=radius, flags=cv2.INPAINT_NS)
    return result, mask_clean

# === Updated 6. Deannotation with Saving ===
def deannotate_image(image_path, output_path=None, show=False):
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"[WARN] Could not read image: {image_path}")
        return

    combined_mask = get_combined_annotation_mask(image)
    inpainted, _ = clean_and_inpaint(image, combined_mask)

    # Save output if path is provided
    if output_path:
        output_path = Path(output_path).with_suffix(".png")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), inpainted):
            print(f"[WARN] Could not write image: {output_path}")
            return False

    # Show preview (optional)
    if show:
        plt.figure(figsize=(15, 5))
        plt.subplot(1, 2, 1)
        plt.title("Original")
        plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        plt.axis('off')

        plt.subplot(1, 2, 2)
        plt.title("Inpainted")
        plt.imshow(cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB))
        plt.axis('off')
        plt.tight_layout()
        plt.show()

    return True

# === Batch Processor ===
def batch_deannotate_images(input_root, output_root):
    image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    input_root = Path(input_root)
    output_root = Path(output_root)

    image_paths = [p for p in input_root.rglob("*") if p.suffix.lower() in image_extensions]

    print(f"[INFO] Found {len(image_paths)} images to process.")

    if not image_paths:
        print(f"[ERROR] No images found in {input_root}")
        return 1

    failed = 0
    for img_path in image_paths:
        relative_path = img_path.relative_to(input_root)
        output_path = output_root / relative_path.with_suffix(".tif")  # save all as .tif
        if deannotate_image(img_path, output_path=output_path, show=False) is False:
            failed += 1

    print(f"[DONE] Inpainted images saved to {output_root}")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove annotations (text, colored and grayscale marks) from images by inpainting.")
    parser.add_argument("input_root", help="Input directory (searched recursively)")
    parser.add_argument("output_root", help="Output directory (images saved as .tif)")
    args = parser.parse_args()
    sys.exit(batch_deannotate_images(args.input_root, args.output_root))
