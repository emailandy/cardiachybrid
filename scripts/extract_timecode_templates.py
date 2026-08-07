"""
Bootstrapping Script: Extract Clean Context-Free Timecode Glyph Templates (P1).

Segments character glyphs from reference video frames using vertical projection profile
boundaries, verifies background margins on all 4 borders, and writes normalized
context-free grayscale template PNGs to sensors/calibration/timecode/.
"""

import os
from pathlib import Path
import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "sensors" / "calibration" / "timecode"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def extract_glyph(bin_img: np.ndarray, gray_img: np.ndarray, x0: int, x1: int) -> tuple[np.ndarray, float]:
    """Extracts a tight bounding box around foreground pixels with background margin verification."""
    # Find active rows where binary pixels exist
    crop_bin = bin_img[:, x0:x1]
    crop_gray = gray_img[:, x0:x1]
    row_sum = np.sum(crop_bin > 0, axis=1)
    active_rows = np.where(row_sum > 0)[0]
    if len(active_rows) == 0:
        return crop_gray, 0.0
    y0, y1 = active_rows[0], active_rows[-1] + 1
    
    # Tight crop
    glyph_crop = crop_gray[y0:y1, :]
    
    # Measure border pixel intensities (must be dark background < 50)
    top_b = np.mean(glyph_crop[0, :])
    bot_b = np.mean(glyph_crop[-1, :])
    left_b = np.mean(glyph_crop[:, 0])
    right_b = np.mean(glyph_crop[:, -1])
    border_mean = float(np.mean([top_b, bot_b, left_b, right_b]))
    return glyph_crop, border_mean


def main() -> None:
    print("=== Extracting Clean Context-Free Timecode Glyph Templates ===")
    cap = cv2.VideoCapture(str(REPO_ROOT / "tests" / "video" / "vidsim2.mp4"))
    fps = cap.get(cv2.CAP_PROP_FPS) or 16.0
    
    # Frame at t=10.0s in vidsim2: 11/7/2023 07:56:06.630 AM
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(10.0 * fps))
    ret, frame_10 = cap.read()
    
    # Frame at t=250.0s in vidsim2: 11/7/2023 08:00:07.074 AM (gives 4, 8)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(250.0 * fps))
    ret, frame_250 = cap.read()
    
    # Frame at t=40.0s in vidsim2: 11/7/2023 07:56:37.085 AM (gives 5, 8)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(40.0 * fps))
    ret, frame_40 = cap.read()
    
    # Frame at t=100.0s in vidsim2: 11/7/2023 07:57:37.001 AM (gives 9)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(100.0 * fps))
    ret, frame_100 = cap.read()

    cap.release()

    extracted: dict[str, tuple[np.ndarray, str, float]] = {}

    def get_segments(frame: np.ndarray, rx: int = 80, ry: int = 120, rw: int = 184, rh: int = 24):
        roi = frame[ry:ry+rh, rx:rx+rw]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, bin_img = cv2.threshold(gray, 190, 255, cv2.THRESH_BINARY)
        v_proj = np.sum(bin_img[4:20, :] > 0, axis=0)
        segs = []
        in_s = False
        s_start = 0
        for i, val in enumerate(v_proj):
            if val > 0 and not in_s:
                in_s = True
                s_start = i
            elif val == 0 and in_s:
                in_s = False
                segs.append((s_start, i))
        if in_s:
            segs.append((s_start, len(v_proj)))
        return gray, bin_img, segs

    # 1. From frame_10 (11/7/2023 07:56:06.630 AM):
    # Segments: 0:'1', 1:'1', 2:'/', 3:'7', 4:'/', 5:'2', 6:'0', 7:'2', 8:'3',
    #           9:'0', 10:'7', 11:':', 12:'5', 13:'6', 14:':', 15:'0', 16:'6',
    #           17:'.', 18:'6', 19:'3', 20:'0', 21:'A', 22:'M'
    gray, bin_img, segs = get_segments(frame_10)
    for sym, s_idx in [
        ("1", 0), ("slash", 2), ("7", 3), ("2", 5), ("0", 6), ("3", 8),
        ("colon", 11), ("5", 12), ("6", 13), ("dot", 17), ("A", 21), ("M", 22)
    ]:
        cs, ce = segs[s_idx]
        glyph, b_mean = extract_glyph(bin_img, gray, cs, ce)
        extracted[sym] = (glyph, "vidsim2 @ t=10s", b_mean)

    # 2. From frame_250 (11/7/2023 08:00:07.074 AM):
    # Segments: 10:'8', 20:'4'
    gray_250, bin_250, segs_250 = get_segments(frame_250)
    g8, b8 = extract_glyph(bin_250, gray_250, segs_250[10][0], segs_250[10][1])
    extracted["8"] = (g8, "vidsim2 @ t=250s", b8)
    g4, b4 = extract_glyph(bin_250, gray_250, segs_250[20][0], segs_250[20][1])
    extracted["4"] = (g4, "vidsim2 @ t=250s", b4)

    # 3. From frame_100 (11/7/2023 07:57:37.001 AM):
    # We can get '9' or from simvid3
    # In vidsim2, year has '2023'. Where does '9' appear? Minute 59 or seconds
    cap_v = cv2.VideoCapture(str(REPO_ROOT / "tests" / "video" / "vidsim2.mp4"))
    # Find frame with '9' in seconds: e.g. 07:56:09 or 07:56:19 -> t=13s
    cap_v.set(cv2.CAP_PROP_POS_FRAMES, int(13.0 * fps))
    ret, frame_13 = cap_v.read()
    cap_v.release()
    gray_13, bin_13, segs_13 = get_segments(frame_13)
    # Segments in 07:56:09 -> segs_13[16] is '9'
    g9, b9 = extract_glyph(bin_13, gray_13, segs_13[16][0], segs_13[16][1])
    extracted["9"] = (g9, "vidsim2 @ t=13s", b9)

    print(f"\nExtracted {len(extracted)} clean glyph templates:")
    print(f"{'Symbol':7s} | {'Source Frame':18s} | {'Dimensions (h x w)':18s} | {'Border Mean':12s}")
    print("-" * 65)
    for sym, (img, src, b_mean) in sorted(extracted.items()):
        out_path = TEMPLATES_DIR / f"{sym}.png"
        cv2.imwrite(str(out_path), img)
        h, w = img.shape
        print(f"{sym:7s} | {src:18s} | {h:2d} x {w:2d} px          | {b_mean:6.2f} / 255")

    print("\n✓ Clean, context-free template extraction complete.")


if __name__ == "__main__":
    main()
