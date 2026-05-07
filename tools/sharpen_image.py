"""
LAB Sharpening Tool
====================
이미지를 LAB 컬러 공간에서 처리해 색상은 유지하면서 선명도만 높입니다.

원리:
  - RGB → LAB 변환 (L=명도, A/B=색상)
  - L 채널(명도)만 선명화 → 색 손상 없음
  - A/B 채널(색상)은 채도 boost만 적용
  - LAB → RGB 변환

Requirements:
    pip install opencv-python numpy

Usage:
    python tools/sharpen_image.py --input image.png
    python tools/sharpen_image.py --input image.png --output sharp.png
    python tools/sharpen_image.py --input image.png --strength 2.0 --saturation 1.2
"""

import argparse
import sys
from pathlib import Path


def sharpen_lab(input_path: str, output_path: str, strength: float = 1.5, saturation: float = 1.1):
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("ERROR: opencv-python이 필요합니다. 아래 명령어를 먼저 실행하세요:")
        print("  pip install opencv-python numpy")
        sys.exit(1)

    # 이미지 로드
    img_bgr = cv2.imread(input_path)
    if img_bgr is None:
        print(f"ERROR: 이미지를 불러올 수 없습니다: {input_path}")
        sys.exit(1)

    h, w = img_bgr.shape[:2]
    print(f"  원본 크기: {w}x{h}")

    # BGR → LAB 변환
    img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2Lab).astype(float)
    L = img_lab[:, :, 0]
    A = img_lab[:, :, 1]
    B = img_lab[:, :, 2]

    # L 채널(명도)만 Unsharp Masking으로 선명화
    L_uint8 = np.clip(L, 0, 255).astype("uint8")
    blurred = cv2.GaussianBlur(L_uint8, (0, 0), sigmaX=3)
    sharpened_L = cv2.addWeighted(L_uint8, 1.0 + strength, blurred, -strength, 0)

    # A/B 채널(색상) 채도 boost - 128 기준으로 배율 적용
    A_boosted = 128.0 + (A - 128.0) * saturation
    B_boosted = 128.0 + (B - 128.0) * saturation

    # 클리핑 후 병합
    L_final = np.clip(sharpened_L, 0, 255).astype("uint8")
    A_final = np.clip(A_boosted, 0, 255).astype("uint8")
    B_final = np.clip(B_boosted, 0, 255).astype("uint8")

    img_lab_result = np.stack([L_final, A_final, B_final], axis=2)

    # LAB → BGR 변환 후 저장
    img_bgr_result = cv2.cvtColor(img_lab_result, cv2.COLOR_Lab2BGR)
    cv2.imwrite(output_path, img_bgr_result)
    print(f"  저장 완료: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="LAB 컬러 공간 선명화 도구 - 색상 유지하면서 선명도만 향상"
    )
    parser.add_argument("--input", "-i", required=True, help="입력 이미지 경로")
    parser.add_argument(
        "--output", "-o", default=None,
        help="출력 경로 (기본값: 원본파일명_sharp.png)"
    )
    parser.add_argument(
        "--strength", "-s", type=float, default=1.5,
        help="선명화 강도 (기본값: 1.5 / 권장 범위: 0.5~3.0)"
    )
    parser.add_argument(
        "--saturation", "-c", type=float, default=1.1,
        help="채도 boost (기본값: 1.1 / 권장 범위: 1.0~1.5)"
    )
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"ERROR: 파일이 없습니다: {args.input}")
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        p = Path(args.input)
        output_path = str(p.parent / f"{p.stem}_sharp{p.suffix}")

    print(f"[LAB Sharpen]")
    print(f"  입력: {args.input}")
    print(f"  선명화 강도: {args.strength} | 채도 boost: {args.saturation}")
    sharpen_lab(args.input, output_path, args.strength, args.saturation)
    print("완료!")


if __name__ == "__main__":
    main()
