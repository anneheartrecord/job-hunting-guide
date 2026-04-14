#!/usr/bin/env python3
"""Generate article illustrations using Google Gemini imagen-3.0-generate-002"""

import base64
import json
import os
import sys
import urllib.request

API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    sys.exit("Error: GEMINI_API_KEY environment variable is not set. Usage: GEMINI_API_KEY=xxx python generate_images.py")
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_STYLE = """Minimal hand-drawn illustration with a subtle tech edge. Off-white paper background, dark gray sketch lines, muted umbrella yellow as the only accent color, with occasional thin circuit-trace or node-graph line details woven into the composition. Lots of negative space, Notion-like doodle aesthetic meets minimal blueprint hints. Faceless round-headed human figure, clean editorial composition, conceptual rather than literal, simple background. No realism, no 3D, no painterly texture, no high saturation, no complex scene, no photographic detail. The overall mood is restrained, lucid, slightly ironic, and emotionally calm. Keep the whole series visually consistent. Use Chinese wherever possible for any visible language or textual content, unless a proper noun, technical term, or special usage is better kept in its original form."""

IMAGES = [
    {
        "filename": "01-resume-01.png",
        "scene": 'Scene: A faceless round-headed figure holding a piece of paper (resume), next to it large bold text "10秒", and an interviewer figure quickly flipping pages. The concept is "resume = sales copy". Add one short Chinese quote in a natural handwritten style near the bottom: 「简历不是档案，是你的销售文案」'
    },
    {
        "filename": "01-resume-02.png",
        "scene": 'Scene: One-page resume principle. A refined single-page resume drawn as a shield shape, highlighted in muted yellow. Next to it, a pile of multi-page resumes crossed out with X marks. Add one short Chinese quote in a natural handwritten style near the bottom: 「一页放不下，说明你还没想清楚」'
    },
    {
        "filename": "01-resume-03.png",
        "scene": 'Scene: STAR method. Four interconnected gears labeled with letters S, T, A, R respectively. Between the gears there are data curves and percentage symbols. Add one short Chinese quote in a natural handwritten style near the bottom: 「没有数字的经历就是空气」'
    },
    {
        "filename": "01-resume-04.png",
        "scene": 'Scene: Planting hooks. A resume page with several lines of text, each line ending with a fish hook icon, representing guiding the interviewer to ask questions. Add one short Chinese quote in a natural handwritten style near the bottom: 「好简历是一个钩子矩阵」'
    },
    {
        "filename": "01-resume-05.png",
        "scene": 'Scene: Personal summary in three sentences. Three lines of text stacked, labeled "过去" (past), "现在" (present), "未来" (future), forming a clean timeline. Add one short Chinese quote in a natural handwritten style near the bottom: 「三句话，过去、现在、未来」'
    },
]


def generate_image(prompt, output_path):
    """Generate image using Gemini 2.0 Flash with image generation."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={API_KEY}"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"Generate an illustration based on this description. Output ONLY the image, no text response.\n\n{prompt}"
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "responseMimeType": "text/plain"
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        # Extract image from response
        for candidate in result.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "inlineData" in part:
                    img_data = base64.b64decode(part["inlineData"]["data"])
                    with open(output_path, "wb") as f:
                        f.write(img_data)
                    print(f"  Saved: {output_path} ({len(img_data)} bytes)")
                    return True

        print(f"  No image in response. Response keys: {list(result.keys())}")
        if "candidates" in result:
            for c in result["candidates"]:
                for p in c.get("content", {}).get("parts", []):
                    if "text" in p:
                        print(f"  Text response: {p['text'][:200]}")
        return False

    except Exception as e:
        print(f"  Error: {e}")
        if hasattr(e, 'read'):
            err_body = e.read().decode('utf-8')[:500]
            print(f"  Response: {err_body}")
        return False


def main():
    # If a specific index is given, only generate that one
    indices = range(len(IMAGES))
    if len(sys.argv) > 1:
        indices = [int(x) for x in sys.argv[1:]]

    for i in indices:
        img = IMAGES[i]
        print(f"\n[{i+1}/5] Generating {img['filename']}...")
        prompt = f"{BASE_STYLE}\n\n{img['scene']}"
        output_path = os.path.join(OUTPUT_DIR, img["filename"])
        success = generate_image(prompt, output_path)
        if not success:
            print(f"  FAILED to generate {img['filename']}")


if __name__ == "__main__":
    main()
