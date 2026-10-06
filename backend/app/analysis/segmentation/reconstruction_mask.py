from __future__ import annotations

import cv2
import numpy as np

from app.analysis.gpu_operations import convert_color
from app.analysis.segmentation.plant_mask import create_plant_mask


def create_reconstruction_mask(
    image: np.ndarray,
    *,
    plant_mask: np.ndarray | None = None,
    valid_pixel_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Keep the plant, soil and pot; leave the enclosure and lamps empty.

    The visible terracotta rim supplies a bounded pot silhouette prior, including
    its dark interior/body. GrabCut refines that prior against the surrounding
    enclosure. Plant-only masks remain separate for biological measurements.
    Without a supported rim, preserve the plant rather than inventing a pot.
    """
    bgr = np.asarray(image, dtype=np.uint8)
    if bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError("建模影像必須是三通道彩色影像。")
    height, width = bgr.shape[:2]
    valid = np.ones((height, width), bool) if valid_pixel_mask is None else np.asarray(valid_pixel_mask) > 0
    if valid.shape != (height, width):
        raise ValueError("建模遮罩尺寸與影像不一致。")
    plant = create_plant_mask(bgr, valid_pixel_mask=valid.astype(np.uint8)).mask if plant_mask is None else np.asarray(plant_mask)
    if plant.shape != (height, width):
        raise ValueError("植物遮罩尺寸與影像不一致。")
    plant = (plant > 0) & valid
    hue, saturation, value = cv2.split(convert_color(bgr, cv2.COLOR_BGR2HSV))
    blue, green, red = cv2.split(bgr.astype(np.float32))
    rim = ((hue <= 24) | (hue >= 170)) & (saturation >= 65) & (value >= 45) & (red > green * 1.25) & (red > blue * 1.3) & valid
    rim_pixels = rim.astype(np.uint8) * 255
    joined = cv2.morphologyEx(rim_pixels, cv2.MORPH_CLOSE, np.ones((3, 5), np.uint8))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    plant_x = float(np.median(np.where(plant)[1])) if plant.any() else width / 2
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        count = int(rim[y:y + h, x:x + w].sum())
        if w < max(10, width * .008) or h < 3 or w / h < .7 or count < 12:
            continue
        score = count / (1 + abs(x + w / 2 - plant_x) / max(w, 1))
        candidates.append((score, contour, (x, y, w, h)))
    if not candidates:
        return plant.astype(np.uint8) * 255
    _, contour, (x, y, w, h) = max(candidates, key=lambda item: item[0])
    center_x, center_y = x + w / 2, y + h / 2
    # A near-circular rim is a top view: its interior already contains the pot.
    body_height = 0 if h >= w * .6 else w * .78
    near_plant = plant.copy()
    yy, xx = np.indices(plant.shape)
    near_plant &= (np.abs(xx - center_x) <= w * 1.5) & (yy <= center_y + h / 2)
    # Some views have a completely clipped, white canopy with no green seeds.
    # Recover illuminated tissue in the pot's immediate upper neighborhood;
    # distant overhead lamps remain outside this content-derived region.
    pale_tissue = ((saturation < 65) | ((green >= red * .85) & (green >= blue * .9))) & (value >= 100)
    pale_tissue &= (np.abs(xx - center_x) <= w * 1.2) & (yy < y) & (yy >= center_y - w * 2.5) & valid
    count, tissue_labels, stats, _ = cv2.connectedComponentsWithStats(pale_tissue.astype(np.uint8), connectivity=8)
    tissue_keep = stats[:, cv2.CC_STAT_AREA] >= max(12, int(w * h * .01))
    tissue_keep[0] = False
    near_plant |= tissue_keep[tissue_labels]
    plant_y = int(np.where(near_plant)[0].min()) if near_plant.any() else y
    x0, x1 = max(0, int(x - w * .35)), min(width, int(x + w * 1.35 + 1))
    y0, y1 = max(0, int(min(plant_y, y) - w * .15)), min(height, int(center_y + max(h / 2, body_height) + w * .18 + 1))
    # Include all nearby foliage in the crop, even when wider than the pot.
    if near_plant.any():
        px = np.where(near_plant)[1]
        x0, x1 = max(0, min(x0, int(px.min()) - 8)), min(width, max(x1, int(px.max()) + 9))
    labels = np.full((height, width), cv2.GC_BGD, np.uint8)
    labels[y0:y1, x0:x1] = cv2.GC_PR_BGD
    hull = cv2.convexHull(contour)
    pot = np.zeros((height, width), np.uint8)
    cv2.fillConvexPoly(pot, hull, 255)
    if body_height:
        body = np.array([[x, int(center_y)], [x + w - 1, int(center_y)],
                         [int(center_x + w * .43), int(center_y + body_height)],
                         [int(center_x - w * .43), int(center_y + body_height)]], np.int32)
        cv2.fillConvexPoly(pot, body, 255)
    labels[pot > 0] = cv2.GC_PR_FGD
    # A bounded interior seed keeps dark soil and the black pot from being
    # confused with the black enclosure. No global brightness exclusion.
    interior = cv2.erode(pot, np.ones((max(3, int(w * .15)), max(3, int(w * .2))), np.uint8)) > 0
    labels[interior | rim | near_plant] = cv2.GC_FGD
    labels[~valid] = cv2.GC_BGD
    crop_labels = labels[y0:y1, x0:x1].copy()
    crop_image = np.ascontiguousarray(bgr[y0:y1, x0:x1])
    if not (crop_labels == cv2.GC_FGD).any() or not (crop_labels == cv2.GC_PR_BGD).any():
        return ((plant | (pot > 0)) & valid).astype(np.uint8) * 255
    # OpenCV's k-means initialization otherwise depends on prior RNG use. A
    # resumed worker must regenerate identical masks and checkpoint signatures.
    cv2.setRNGSeed(42)
    cv2.grabCut(crop_image, crop_labels, None, np.zeros((1, 65)), np.zeros((1, 65)), 3, cv2.GC_INIT_WITH_MASK)
    result = np.zeros((height, width), np.uint8)
    result[y0:y1, x0:x1] = np.isin(crop_labels, [cv2.GC_FGD, cv2.GC_PR_FGD]).astype(np.uint8) * 255
    # The pot and enclosure can share very similar dark colors. Constrain region
    # growth to the pot prior and a narrow tissue neighborhood; color agreement
    # alone must not fill the empty gap between the canopy and pot.
    allowed = cv2.dilate(pot, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    allowed |= cv2.dilate(near_plant.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    result[~allowed] = 0
    # Keep the pot interior solid; dark soil is still part of the subject.
    cv2.fillConvexPoly(result, hull, 255)
    result[near_plant] = 255
    result[~valid] = 0
    return result
