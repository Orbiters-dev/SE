"""
Nano Banana Image Generator
Google Gemini image generation tool using the Nano Banana model.

Usage:
    python tools/generate_image.py --prompt "A futuristic city at sunset" [--output path.png] [--model flash|pro] [--edit input.png]

Modes:
    Text-to-Image:  python tools/generate_image.py --prompt "description"
    Image Editing:  python tools/generate_image.py --prompt "edit instructions" --edit source.png
"""

import argparse
import os
import sys
from pathlib import Path
from env_loader import load_env

load_env()


def get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in .env")
        sys.exit(1)

    from google import genai
    return genai.Client(api_key=api_key)


MODEL_MAP = {
    "flash": "gemini-2.5-flash-image",
    "pro": "nano-banana-pro-preview",
}


def generate_image(prompt: str, output_path: str, model_key: str = "flash", edit_path: str = None):
    from google.genai import types

    client = get_client()
    model_id = MODEL_MAP.get(model_key, MODEL_MAP["flash"])

    contents = []
    if edit_path:
        from PIL import Image
        img = Image.open(edit_path)
        contents.append(img)
    contents.append(prompt)

    print(f"Model: {model_id}")
    print(f"Prompt: {prompt}")
    if edit_path:
        print(f"Edit source: {edit_path}")
    print("Generating...")

    response = client.models.generate_content(
        model=model_id,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
        ),
    )

    saved = False
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print(f"Response text: {part.text}")
        elif part.inline_data is not None:
            image = part.as_image()
            image.save(output_path)
            print(f"Image saved: {output_path}")
            saved = True

    if not saved:
        print("WARNING: No image was returned. The model may have refused the prompt.")
        if response.candidates and response.candidates[0].finish_reason:
            print(f"Finish reason: {response.candidates[0].finish_reason}")


def main():
    parser = argparse.ArgumentParser(description="Nano Banana Image Generator")
    parser.add_argument("--prompt", "-p", required=True, help="Image generation prompt")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: Data Storage/images/<timestamp>.png)")
    parser.add_argument("--model", "-m", choices=["flash", "pro"], default="flash", help="Model: flash (fast) or pro (high quality)")
    parser.add_argument("--edit", "-e", default=None, help="Source image path for editing mode")
    args = parser.parse_args()

    if args.output:
        output_path = args.output
    else:
        from datetime import datetime
        img_dir = Path("Data Storage/images")
        img_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(img_dir / f"nanobanana_{timestamp}.png")

    generate_image(args.prompt, output_path, args.model, args.edit)


if __name__ == "__main__":
    main()
