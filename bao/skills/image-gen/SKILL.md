---
name: image-gen
description: Use to draw, generate, design, or create images, art, or illustrations.
metadata: {"bao":{"emoji":"🎨","icon":"spark","display":{"name":"Image Generation","nameZh":"图像生成","descriptionZh":"根据提示词生成插画、海报和视觉素材。"},"category":"creative","capabilityRefs":["image_generation"],"activationRefs":["image_generation"],"examplePrompts":["帮我生成一张产品海报","画一张极简风格的插画"]}}
---

# Image Generation

## When to Use
- User asks to create, draw, generate, or design an image/picture
- User describes a visual scene they want to see

## Workflow
1. Call `generate_image(prompt="detailed English description")`
2. Tool returns an image contribution that Bao attaches to the final reply automatically
3. Reply normally with a brief description; do not call a separate send tool for the current session

## Prompt Tips
- Write prompts in English for best quality
- Be specific: style, mood, lighting, composition, colors
- Include art style if relevant: "watercolor", "photorealistic", "anime", "oil painting"
- One image per call; adjust prompt and retry if unsatisfied
- Use `aspect_ratio` for non-square images: "16:9" (landscape), "9:16" (portrait)
