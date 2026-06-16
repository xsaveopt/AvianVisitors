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

A {pose} {com_name} ({sci_name}) rendered as an Edo-period Japanese kachō-e woodblock print. The bird is painted with VERY FEW MARKS: the body is essentially 2-4 flat color zones with sharp boundaries, almost no internal texture, no feather-by-feather rendering, no stippling, no gradient shading. It looks painted with maybe 30 brush strokes total - a few flat color zones, a few confident outline strokes, an accent stroke or two for major wing or tail markings, and nothing more.

Confident sumi-e ink linework with soft watercolor washes. Earthy, restrained palette: burnt umber, ochre, indigo, vermillion, muted greens. The body looks like flat painted paper, not a textured surface or a shaded volume. Subtle plumage variation (streaking, mottling, fine barring) is ABSTRACTED into 2-3 broad zones rather than rendered literally. Eye, beak, and feet are drawn with crisp dark ink - the only places confident dark line belongs.

The bird sits on a CONSISTENT WARM CREAM background, like aged Japanese mulberry paper, a soft warm buff cream that fills the entire frame. This is the only background element: NO branch, NO twig, NO perch, NO leaves, NO foliage, NO substrate, NO scenery, NO sky, NO moon, NO water - only the bird floating against the cream paper ground. The perch is purely implied by toe posture and is NEVER drawn. NO border, NO frame, NO text, NO signature.

Composition: the bird occupies one-third to one-half of the frame with generous cream negative space around it. The image feels sparse and confident, not packed with detail.

The ENTIRE bird fits within the frame: head, both wings (fully extended for the flight pose), full tail, both legs, both feet, beak. Do NOT crop any body part at the edge. Leave generous padding on all sides.

### Species accuracy

- Match the proportions, head color, throat, wing pattern, back color, tail pattern, and leg color of a {com_name}. Render the brightest BREEDING (adult-summer) plumage, the most diagnostic and recognizable version of the species.
{anti_ref_line}
- Pay attention to species-specific patterns. Do NOT default to generic markings: a uniformly dark head gets NO white face mask, solid wings get NO white wingbars, a crestless species gets NO crest.
- For close relatives (multiple goldfinch, jay, or sparrow species) render the diagnostic differences clearly so the species stay visibly distinguishable.

### Anatomy

- EXACTLY TWO wings (one left, one right). EXACTLY TWO legs. EXACTLY ONE head. EXACTLY ONE beak. EXACTLY ONE tail.
- BOTH FEET visible at the bottom of the body.
- Songbird feet are SMALL relative to the body. Tarsi are roughly 10-15% of body height for finches/sparrows/warblers/chickadees, 15-20% for jays/thrushes/mockingbirds, and under 25% for larger birds. Slim tarsi, small delicate toes. Do NOT exaggerate feet or claws.

### Pose

- PERCHED (pose 1): one wing folded against the body, the other tucked behind. Both feet visible at the bottom, toes curled gently forward as if grasping a thin perch - but the perch itself is NOT drawn. The bird floats in space, posture suggesting it is perched.
- IN FLIGHT (pose 2): both wings fully extended in a natural flapping position. Legs and feet either tucked tight against the belly with toes folded out of sight, or extended straight back along the line of the tail. Do NOT dangle the feet below the body with toes splayed.

### Output

A single bird on the flat warm cream ground. No shadow, no paper texture, no caption, no border.
