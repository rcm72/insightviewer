
import cv2
import numpy as np
import os
import zipfile

def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0

def crop_with_margin(img, x, y, w, h, m=10):
    H, W = img.shape[:2]
    x0 = max(0, x - m)
    y0 = max(0, y - m)
    x1 = min(W, x + w + m)
    y1 = min(H, y + h + m)
    return img[y0:y1, x0:x1]

def split_page(in_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    img = cv2.imread(in_path)
    if img is None:
        raise RuntimeError(f"Cannot read: {in_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # 1) Find rectangles (photos) using edges
    edges = cv2.Canny(gray_blur, 30, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges_d = cv2.dilate(edges, kernel, iterations=2)
    contours, _ = cv2.findContours(edges_d, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rects = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        rect_area = w * h
        if rect_area < 80000 or w < 300 or h < 250:
            continue
        area = cv2.contourArea(c)
        fill = area / rect_area if rect_area else 0
        if fill > 0.12:
            rects.append((x, y, w, h, rect_area, fill))

    # Remove duplicates (overlapping rectangles)
    rects_sorted = sorted(rects, key=lambda t: t[4], reverse=True)
    kept = []
    for r in rects_sorted:
        box = r[:4]
        if all(iou(box, k[:4]) < 0.6 for k in kept):
            kept.append(r)

    photos = [r for r in kept if r[1] < 1500 and r[2] > 450 and r[3] > 330]
    photos = sorted(photos, key=lambda t: (t[1], t[0]))

    # Top row (3) + mid row (2)
    if len(photos) >= 5:
        top_row = sorted(photos[:3], key=lambda t: t[0])
        mid_row = sorted(photos[3:5], key=lambda t: t[0])
        ordered = top_row + mid_row
    else:
        ordered = photos

    out_files = []
    base_name = os.path.splitext(os.path.basename(in_path))[0]  # Get the base name of the input file
    for i, r in enumerate(ordered, start=1):
        x, y, w, h, _, _ = r
        crop = crop_with_margin(img, x, y, w, h, m=10)
        p = os.path.join(out_dir, f"{base_name}_slika{i}.jpg")
        cv2.imwrite(p, crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        out_files.append(p)

    # 2) Find the bottom diagram (larger image)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.int32)
    bg = lab[10, 10]
    diff = np.sqrt(((lab - bg) ** 2).sum(axis=2))

    H, W = gray.shape
    region_top = int(H * 0.59)  # Start slightly above the diagram
    region_bottom = H - 120  # Cut off the footer

    sub = (diff > 55).astype(np.uint8)[region_top:region_bottom, :]
    row_sum = sub.sum(axis=1)
    rows = np.where(row_sum > 0.04 * W)[0]  # Threshold

    if len(rows) > 0:
        top = region_top + rows[0]
        bottom = region_top + rows[-1]

        col_sum = sub.sum(axis=0)
        cols = np.where(col_sum > 0.02 * sub.shape[0])[0]
        left = int(cols[0]) if len(cols) else 0
        right = int(cols[-1]) if len(cols) else W - 1

        diagram = crop_with_margin(img, left, top, right - left, bottom - top, m=12)
        p = os.path.join(out_dir, f"{base_name}_slika{len(out_files) + 1}.jpg")
        cv2.imwrite(p, diagram, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        out_files.append(p)

    # ZIP
    zip_path = os.path.join(out_dir, f"{base_name}.zip")
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in out_files:
            z.write(p, arcname=os.path.basename(p))

    return zip_path

def process_directory(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    images = [f for f in os.listdir(input_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    for image in images:
        in_path = os.path.join(input_dir, image)
        print(f"Processing: {in_path}")
        try:
            zip_path = split_page(in_path, output_dir)
            print(f"Created ZIP: {zip_path}")
        except Exception as e:
            print(f"Error processing {in_path}: {e}")

if __name__ == "__main__":
    input_dir = "/home/robert/insightViewer/source/InsightViewer/app/static/images/bookBiologija1/"  # Change this to your input directory
    output_dir = "/home/robert/insightViewer/source/InsightViewer/app/static/images/bookBiologija1/slike"  # Change this to your output directory
    #output_dir = "output_images"  # Change this to your output directory
    process_directory(input_dir, output_dir)
