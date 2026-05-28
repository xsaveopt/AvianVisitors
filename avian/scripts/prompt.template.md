# Bird illustration prompt

The prompt sent to Gemini for every illustration. Edit the body to change the style.

Three placeholders get replaced per request:

- `{sci_name}` is the binomial Latin name, e.g. `Calypte anna`
- `{com_name}` is the English common name, e.g. `Anna's Hummingbird`
- `{pose}` is either `perched` (pose 1) or `in flight with wings spread` (pose 2)

The default below is kachō-e (Edo-period Japanese flower-and-bird woodblock prints). Replace it with whatever style fits your apartment.

---

## Prompt

Generate a {pose} {com_name} ({sci_name}) in the style of an Edo-period Japanese kachō-e woodblock print. Confident sumi-e ink linework with soft watercolor washes. Earthy, restrained palette: burnt umber, ochre, indigo, vermillion, muted greens. Plumage details rendered with short directional brush strokes; eye, beak, and feet drawn with crisp ink. The bird is the only subject. NO background, NO branch unless the pose requires it (a single sparse twig is fine for perched), NO border or frame, NO text or signature.

Anatomy must be biologically accurate for the named species:

- Exactly two wings. Two legs. One head. One beak. One tail.
- Posture, color, markings, and body proportions matching {com_name} field-guide references.
- For perched poses: one wing folded against the body, the other tucked behind. For flight: both wings extended in a natural flapping position.

Render at high resolution on a fully transparent background. Cut the bird out cleanly. No shadow, no paper texture, no caption.
