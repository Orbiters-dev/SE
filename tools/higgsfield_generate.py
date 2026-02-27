"""
Higgsfield AI - Image & Video Generation Tool
================================================
Uses the higgsfield-client Python SDK to generate images and videos.

Requirements:
  pip install higgsfield-client python-dotenv

Environment variables (.env):
  HF_API_KEY=your-api-key
  HF_API_SECRET=your-api-secret

Get credentials from: https://cloud.higgsfield.ai/

Usage:
  python tools/higgsfield_generate.py --mode image --prompt "A serene lake at sunset"
  python tools/higgsfield_generate.py --mode video --prompt "A cat walking on a beach"
  python tools/higgsfield_generate.py --mode image --prompt "Product photo" --resolution 2K --aspect-ratio 1:1
"""

import argparse
import json
import os
import sys
from pathlib import Path

from env_loader import load_env

# Load secrets from secure location
load_env()

# Validate credentials
api_key = os.getenv("HF_API_KEY", "")
api_secret = os.getenv("HF_API_SECRET", "")

if not api_key or not api_secret:
    print("[ERROR] HF_API_KEY and HF_API_SECRET are required in .env")
    print("Get your credentials from: https://cloud.higgsfield.ai/")
    sys.exit(1)

# Set the combined key format the SDK expects
os.environ["HF_KEY"] = f"{api_key}:{api_secret}"

import higgsfield_client


# Available models (from Higgsfield Cloud)
MODELS = {
    "text-to-image": "bytedance/seedream/v4/text-to-image",
    "text-to-video": "kling/v2.1/text-to-video",
    "image-to-video": "kling/v2.1/image-to-video",
}


def generate_image(prompt, resolution="2K", aspect_ratio="16:9"):
    """Generate an image from a text prompt."""
    print(f"[Higgsfield] Generating image...")
    print(f"  Prompt: {prompt}")
    print(f"  Resolution: {resolution}, Aspect Ratio: {aspect_ratio}")

    result = higgsfield_client.subscribe(
        MODELS["text-to-image"],
        arguments={
            "prompt": prompt,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "camera_fixed": False,
        },
        on_queue_update=lambda status: print(f"  Status: {type(status).__name__}"),
    )

    if result and "images" in result:
        for i, img in enumerate(result["images"]):
            print(f"  Image {i+1}: {img.get('url', 'N/A')}")
    else:
        print(f"  Result: {json.dumps(result, indent=2, ensure_ascii=False)}")

    return result


def generate_video(prompt, aspect_ratio="16:9", duration=5):
    """Generate a video from a text prompt."""
    print(f"[Higgsfield] Generating video...")
    print(f"  Prompt: {prompt}")
    print(f"  Aspect Ratio: {aspect_ratio}, Duration: {duration}s")

    result = higgsfield_client.subscribe(
        MODELS["text-to-video"],
        arguments={
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": str(duration),
        },
        on_queue_update=lambda status: print(f"  Status: {type(status).__name__}"),
    )

    if result and "video" in result:
        print(f"  Video URL: {result['video'].get('url', 'N/A')}")
    else:
        print(f"  Result: {json.dumps(result, indent=2, ensure_ascii=False)}")

    return result


def image_to_video(image_path, prompt="", aspect_ratio="16:9", duration=5):
    """Generate a video from an image."""
    print(f"[Higgsfield] Converting image to video...")
    print(f"  Image: {image_path}")
    print(f"  Prompt: {prompt}")

    # Upload image first
    image_url = higgsfield_client.upload_file(image_path)
    print(f"  Uploaded image: {image_url}")

    result = higgsfield_client.subscribe(
        MODELS["image-to-video"],
        arguments={
            "image_url": image_url,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": str(duration),
        },
        on_queue_update=lambda status: print(f"  Status: {type(status).__name__}"),
    )

    if result and "video" in result:
        print(f"  Video URL: {result['video'].get('url', 'N/A')}")
    else:
        print(f"  Result: {json.dumps(result, indent=2, ensure_ascii=False)}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Higgsfield AI Generation Tool")
    parser.add_argument(
        "--mode",
        choices=["image", "video", "img2vid"],
        required=True,
        help="Generation mode: image, video, or img2vid",
    )
    parser.add_argument("--prompt", required=True, help="Text prompt for generation")
    parser.add_argument("--resolution", default="2K", help="Image resolution (default: 2K)")
    parser.add_argument("--aspect-ratio", default="16:9", help="Aspect ratio (default: 16:9)")
    parser.add_argument("--duration", type=int, default=5, help="Video duration in seconds (default: 5)")
    parser.add_argument("--image", help="Image path for img2vid mode")

    args = parser.parse_args()

    if args.mode == "image":
        generate_image(args.prompt, args.resolution, args.aspect_ratio)
    elif args.mode == "video":
        generate_video(args.prompt, args.aspect_ratio, args.duration)
    elif args.mode == "img2vid":
        if not args.image:
            print("[ERROR] --image is required for img2vid mode")
            sys.exit(1)
        image_to_video(args.image, args.prompt, args.aspect_ratio, args.duration)


if __name__ == "__main__":
    main()
