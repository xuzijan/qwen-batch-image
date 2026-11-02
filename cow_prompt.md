# Single-cow prompt

Copy the complete block below into the image-generation website.

```text
Task

Create exactly one original, visually appealing illustration in a simple, iconic, outline-free flat cartoon style. The illustration belongs to a large, diverse collection designed for semantic object-level layer separation. Follow the sample-specific image description for the single main subject and its action. Keep the composition extremely simple and readable as a small cartoon icon. The final result must feel like polished standalone artwork, not a segmentation diagram.

## 1. Scene and creativity

Treat the sample-specific subject and action as fixed semantic anchors. Show exactly one main subject. Use a plain, supportive background with at most one simple flat ground shape. Keep the subject large and centered, with generous empty space around it. Do not add other animals, people, furniture, tools, flowers, clouds, distant objects, or scenery.

## 2. Semantic layer structure

The entire illustration must naturally decompose into 2–4 semantic layers, including the background. Use one main subject, one simple ground shape when needed, and no other independent objects. Each layer corresponds to one complete meaningful entity. Internal color patches and small details remain part of the main subject. Plan the entity list and stacking order before rendering; do not exceed four layers.

## 3. Entity independence and occlusion

Give the single main subject a recognizable identity, a clean silhouette, and a clear boundary. Avoid occlusion, interlocking silhouettes, overlapping objects, tiny decorative entities, and ambiguous fused boundaries. Only the final composite illustration is required.

## 4. Visual style

Use a simple, iconic, outline-free flat cartoon illustration style. Represent the main subject with a clean, simplified silhouette, slightly exaggerated but natural cartoon proportions, and only a few large uniform color regions. Preserve only the visual features necessary to recognize the subject. Use solid flat fills with clean shape boundaries and a restrained harmonious palette.

Do not use black outlines, dark contour lines, ink strokes, borders, cast shadows, contact shadows, ambient occlusion, highlights, gradients, three-dimensional shading, realistic anatomy, fur or skin texture, complex patterns, or fine decorative details. Define every object only through filled shapes and their boundaries with adjacent regions.

## 5. Complexity control

Prioritize clarity at a glance over detail. Keep the entire image readable as a small cartoon icon. Use no detailed grass, leaves, flowers, clouds, scenery, texture, repeated objects, or decorative elements. Prefer a few broad shapes to many small marks.

## 6. Composition

Present one centered main subject against a nearly empty background. Use at most one simple flat ground shape and one plain background color. Maintain generous negative space and a clear visual hierarchy.

## 7. Output requirements

Prefer one complete editable SVG image with viewBox="0 0 1536 1024" (landscape 3:2). Optionally render a matching 1536 × 1024 PNG preview. In the SVG, place each semantic entity in its own named <g> group when possible. Show only the final composite illustration, not separated/exploded layers. No text, captions, labels, watermarks, frame, layer numbers, construction guides, or displayed segmentation masks.

## 8. Final check

Before output, verify that the image contains exactly one recognizable main subject, no extra objects, at most 2–4 semantic layers including the background, only flat filled shapes, no outlines, no shadows, no gradients, no texture, and no fine decorative details. If not, simplify or redesign before rendering.

A single cartoon cow is grazing on a flat patch of grass.
```
