"""
Barrier-grid / slit scanimation generator for printing.

Outputs:
- interlaced_base.png: print on paper
- barrier_mask.png: print on transparency

For N frames:
  slit_width = stripe_width
  bar_width = (N - 1) * stripe_width
  period = N * stripe_width
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def mm_to_px(mm: float, dpi: int) -> int:
    return max(1, round(mm * dpi / 25.4))


def create_barrier_mask_rgba(width, height, stripe_px, n_frames):
    bar_px = (n_frames - 1) * stripe_px
    period_px = n_frames * stripe_px

    print("Mask geometry (scanimation-correct):")
    print(f"  Frames (N):          {n_frames}")
    print(f"  Stripe/slit width:   {stripe_px}px")
    print(f"  Opaque bar width:    {bar_px}px")
    print(f"  Period:              {period_px}px")
    print("Mask canvas:")
    print(f"  Size:                {width} x {height}px")

    mask = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)

    x = 0
    while x < width:
        bar_x0 = x + stripe_px
        bar_x1 = bar_x0 + bar_px - 1
        if bar_x0 < width and bar_px > 0:
            draw.rectangle(
                (bar_x0, 0, min(bar_x1, width - 1), height - 1),
                fill=(0, 0, 0, 255),
            )
        x += period_px

    return mask, period_px, stripe_px, bar_px


def create_interlaced_base(frames, stripe_px):
    w, h = frames[0].size
    n = len(frames)
    base = Image.new("RGB", (w, h), (0, 0, 0))

    for x in range(0, w, stripe_px):
        i = (x // stripe_px) % n
        x2 = min(x + stripe_px, w)
        strip = frames[i].crop((x, 0, x2, h))
        base.paste(strip, (x, 0))

    return base


def main():
    parser = argparse.ArgumentParser(description="Printable scanimation barrier-grid files")
    parser.add_argument("--folder", required=True, help="Folder with your frames")
    parser.add_argument("--dpi", type=int, default=400)
    parser.add_argument(
        "--stripe-mm",
        type=float,
        default=1.0,
        help="Width of one frame stripe / transparent slit in mm.",
    )
    parser.add_argument(
        "--mask-width-mult",
        type=int,
        default=4,
        help="Multiply only the barrier mask width.",
    )
    parser.add_argument("--output", default="output")

    args = parser.parse_args()

    paths = sorted(Path(args.folder).glob("*.[jpJP][pnPN][gG]*"))
    if not paths:
        print("No images found in folder")
        return

    frames = [Image.open(p).convert("RGB") for p in paths]
    w, h = frames[0].size

    for idx, frame in enumerate(frames):
        if frame.size != (w, h):
            raise ValueError(f"Frame {paths[idx].name} size {frame.size} != first frame size {(w, h)}")

    n_frames = len(frames)
    stripe_px = mm_to_px(args.stripe_mm, args.dpi)

    base = create_interlaced_base(frames, stripe_px)

    mask_w = w * max(1, int(args.mask_width_mult))
    mask_h = h
    mask, _period_px, _slit_px, _bar_px = create_barrier_mask_rgba(mask_w, mask_h, stripe_px, n_frames)

    out = Path(args.output)
    out.mkdir(exist_ok=True)

    mask_path = out / "barrier_mask.png"
    base_path = out / "interlaced_base.png"

    mask.save(mask_path, dpi=(args.dpi, args.dpi))
    base.save(base_path, dpi=(args.dpi, args.dpi))

    print("\nCreated:")
    print(f"  {base_path}: print on paper, base width = {w}px")
    print(f"  {mask_path}: print on transparency, mask width = {mask_w}px")
    print("\nHow it should behave:")
    print("  Only one frame is visible at a time.")
    print(f"  Sliding mask by {args.stripe_mm}mm, about {stripe_px}px, switches to next frame.")


if __name__ == "__main__":
    main()
