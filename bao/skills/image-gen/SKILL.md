---
name: image-gen
description: Use to draw, generate, design, or create images, art, or illustrations.
metadata: {"bao":{"emoji":"🎨"}}
---

# Image Generation

## When to Use
- User asks to create, draw, generate, or design an image/picture
- User describes a visual scene they want to see

## Workflow
1. Call `generate_image(prompt="detailed English description")`
2. Tool returns a local file path
3. Send to user: `message(content="brief description", media=["the_returned_path"])`

## Prompt Tips
- Write prompts in English for best quality
- Be specific: style, mood, lighting, composition, colors
- Include art style if relevant: "watercolor", "photorealistic", "anime", "oil painting"
- One image per call; adjust prompt and retry if unsatisfied
- Use `aspect_ratio` for non-square images: "16:9" (landscape), "9:16" (portrait)
