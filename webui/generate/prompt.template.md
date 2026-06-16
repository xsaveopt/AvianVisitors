# Bird illustration prompt

The prompt used by FLUX for every render.

Three placeholders get replaced per render:

- `{sci_name}` is the binomial Latin name, e.g. `Calypte anna`
- `{com_name}` is the English common name, e.g. `Anna's Hummingbird`
- `{pose}` is either `perched` (pose 1) or `in flight with wings spread` (pose 2)
- `{anti_ref_line}` is a short per-species clause that forbids a famous look-alike, empty for most species

Keep this short. FLUX runs the prompt through CLIP, which only reads the first 77 tokens and collapses them into a single pooled vector that carries the overall style, so a long prompt with many clauses muddies the style and the tail is discarded outright. One tight style-first sentence renders a far cleaner kachō-e look than a paragraph of negations.

---

## Prompt

A {pose} {com_name} ({sci_name}) as a flat Edo-period Japanese kachō-e ukiyo-e woodblock print. Bold sumi-e ink outlines, flat unshaded color, minimal detail, plain warm cream paper background. Not a photo, no shading, no 3D. Accurate {com_name} breeding plumage. {anti_ref_line}
