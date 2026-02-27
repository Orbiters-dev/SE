"""
Flux.1 Image Generator (via fal.ai)
====================================
Generates images using Black Forest Labs' Flux.1 models through fal.ai API.

Requirements:
  pip install fal-client python-dotenv

Environment variables (.env):
  FAL_KEY=fal_sk_your_key_here

Get your API key from: https://fal.ai/dashboard/keys

Usage:
  python tools/flux_generate.py --prompt "A futuristic city at sunset"
  python tools/flux_generate.py --prompt "Product photo" --model dev --size square_hd
  python tools/flux_generate.py --prompt "Cat in space" --model pro --size landscape_16_9
  python tools/flux_generate.py --prompt "Logo design" --steps 28 --seed 42
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from env_loader import load_env

# Load secrets from secure location
load_env()

fal_key = os.getenv("FAL_KEY", "")
if not fal_key:
    print("[ERROR] FAL_KEY not found in .env")
    print("Get your API key from: https://fal.ai/dashboard/keys")
    sys.exit(1)

import fal_client

# Model endpoints
MODELS = {
    "schnell": "fal-ai/flux/schnell",       # Fast (1-4 steps, ~1s)
    "dev":     "fal-ai/flux/dev",            # High quality (28 steps)
    "pro":     "fal-ai/flux-pro/v1.1",       # Best quality (commercial)
    "ultra":   "fal-ai/flux-pro/v1.1-ultra", # Up to 2K resolution
}

# Default steps per model
DEFAULT_STEPS = {
    "schnell": 4,
    "dev": 28,
    "pro": 28,
    "ultra": 28,
}

VALID_SIZES = [
    "square_hd", "square",
    "portrait_4_3", "portrait_16_9",
    "landscape_4_3", "landscape_16_9",
]


def on_queue_update(update):
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(f"  {log['message']}")


def generate(prompt, model_key="schnell", image_size="landscape_4_3",
             steps=None, guidance=3.5, seed=None, num_images=1,
             output_format="png"):
    """Generate image(s) with Flux.1 via fal.ai."""
    endpoint = MODELS.get(model_key)
    if not endpoint:
        print(f"[ERROR] Unknown model '{model_key}'. Choose from: {', '.join(MODELS.keys())}")
        sys.exit(1)

    if steps is None:
        steps = DEFAULT_STEPS[model_key]

    print(f"[Flux.1] Generating with {model_key} ({endpoint})")
    print(f"  Prompt: {prompt}")
    print(f"  Size: {image_size} | Steps: {steps} | Guidance: {guidance}")
    if seed is not None:
        print(f"  Seed: {seed}")

    arguments = {
        "prompt": prompt,
        "image_size": image_size,
        "num_inference_steps": steps,
        "guidance_scale": guidance,
        "num_images": num_images,
        "output_format": output_format,
        "enable_safety_checker": True,
    }
    if seed is not None:
        arguments["seed"] = seed

    result = fal_client.subscribe(
        endpoint,
        arguments=arguments,
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    if not result or "images" not in result:
        print(f"[ERROR] Unexpected response: {result}")
        sys.exit(1)

    print(f"\n[OK] Generated {len(result['images'])} image(s)  |  Seed: {result.get('seed', 'N/A')}")

    urls = []
    for i, img in enumerate(result["images"]):
        url = img.get("url", "")
        w = img.get("width", "?")
        h = img.get("height", "?")
        print(f"  Image {i+1}: {w}x{h}  {url}")
        urls.append(url)

    return result, urls


def download_images(urls, output_dir):
    """Download generated images to local directory."""
    import urllib.request

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i, url in enumerate(urls):
        suffix = f"_{i+1}" if len(urls) > 1 else ""
        filename = f"flux_{timestamp}{suffix}.png"
        filepath = output_dir / filename
        urllib.request.urlretrieve(url, str(filepath))
        print(f"  Saved: {filepath}")
        saved.append(str(filepath))

    return saved


def main():
    parser = argparse.ArgumentParser(description="Flux.1 Image Generator (fal.ai)")
    parser.add_argument("--prompt", "-p", required=True, help="Image generation prompt")
    parser.add_argument("--model", "-m", choices=list(MODELS.keys()), default="schnell",
                        help="Model: schnell (fast), dev (quality), pro (best), ultra (2K)")
    parser.add_argument("--size", "-s", default="landscape_4_3",
                        help=f"Image size: {', '.join(VALID_SIZES)} or WxH (e.g. 1024x768)")
    parser.add_argument("--steps", type=int, default=None, help="Inference steps (default varies by model)")
    parser.add_argument("--guidance", "-g", type=float, default=3.5, help="Guidance scale (default: 3.5)")
    parser.add_argument("--seed", type=int, default=None, help="Seed for reproducibility")
    parser.add_argument("--num", "-n", type=int, default=1, help="Number of images (1-4)")
    parser.add_argument("--output", "-o", default=None, help="Output directory (default: Data Storage/images/)")
    parser.add_argument("--no-download", action="store_true", help="Skip downloading, just print URLs")

    args = parser.parse_args()

    # Handle custom WxH size
    if "x" in args.size.lower():
        try:
            w, h = args.size.lower().split("x")
            image_size = {"width": int(w), "height": int(h)}
        except ValueError:
            print(f"[ERROR] Invalid size format '{args.size}'. Use WxH (e.g. 1024x768)")
            sys.exit(1)
    else:
        image_size = args.size

    result, urls = generate(
        prompt=args.prompt,
        model_key=args.model,
        image_size=image_size,
        steps=args.steps,
        guidance=args.guidance,
        seed=args.seed,
        num_images=args.num,
    )

    if not args.no_download and urls:
        output_dir = args.output or "Data Storage/images"
        print(f"\nDownloading to {output_dir}/...")
        download_images(urls, output_dir)


if __name__ == "__main__":
    main()
