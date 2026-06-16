# Bird illustration prompt

The prompt used by FLUX for every illustration.

Three text placeholders get replaced per render:

- `{sci_name}` is the binomial Latin name, e.g. `Calypte anna`
- `{com_name}` is the English common name, e.g. `Anna's Hummingbird`
- `{pose}` is either `perched` (pose 1) or `in flight with wings spread` (pose 2)

`pregen.py` also steers each render through FLUX.1 Redux image conditioning:

- A POSITIVE anatomy reference (Wikipedia photo of the target species) anchors species identity, markings, and plumage.
- A POSITIVE style reference (a real Edo-period kachō-e print by Ohara Koson or Hiroshi Yoshida) anchors the painting technique; its species is irrelevant.
- The anti-reference is text only. For genera where the model drifts toward a famous lookalike (a Blue Jay for small blue corvids, a Barn Swallow for other swallows) the `{anti_ref_line}` placeholder is rewritten per-species to forbid that lookalike's diagnostic features.

The reference photos are blended into the conditioning, not captioned, so the prompt body never refers to a numbered image.

---

## Prompt

Flat Edo-period Japanese kachō-e woodblock print of a {pose} {com_name} ({sci_name}). Ukiyo-e style: bold confident sumi-e ink outlines, flat unshaded color fills, very few marks, minimal internal detail. NOT a photo, NOT realistic, NOT 3D: no shading, no gradients, no feather texture, no depth. Restrained mineral palette of burnt umber, ochre, indigo, vermillion, and muted green. Accurate diagnostic breeding plumage and colors of the {com_name}. The single bird floats on a flat warm cream mulberry-paper ground filling the whole frame: no branch, no perch, no leaves, no scenery, no shadow, no border, no text. The entire bird is in frame with generous cream margin. {anti_ref_line}
