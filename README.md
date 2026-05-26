# Moire Animations

Printable moire animation generators and generated reference assets.

This repo has two separate tools:

- `main.py`: linear slit scanimation / barrier-grid generator.
- `radial_numbers/radial_moire_numbers.py`: radial number-clock generator.

## Slit Scanimation

`main.py` creates a classic barrier-grid animation from a folder of source
frames. It writes:

- `output/interlaced_base.png`: print on paper.
- `output/barrier_mask.png`: print on transparent film.

Example:

```powershell
python .\main.py --folder running --stripe-mm 1 --output output
```

Print at 100% scale. Slide the transparency by one stripe width to advance one
animation frame.

![Slit scanimation demo](running/ezgif-3178bb43e9693af1.gif)

## Radial Number Clock

`radial_numbers/radial_moire_numbers.py` creates a radial moire base and a
rotating transparency mask. In encoder-ring clock mode, the mask reveals numbers
`1` through `12` at 30-degree increments, so one full mask rotation acts like a
12-hour clock.

Generate the final encoder-ring version:

```powershell
python .\radial_numbers\radial_moire_numbers.py --mode encoder-ring-clock --preview-angles-deg 0,1,29,30,31 --output radial_numbers/output_encoder_ring_clock
```

Final radial files:

- `radial_numbers/output/`: original radial scanline/repeating output.
- `radial_numbers/output_encoder_ring_clock/radial_interlaced_base.png`: print on paper.
- `radial_numbers/output_encoder_ring_clock/radial_barrier_mask.png`: print on transparency.
- `radial_numbers/output_encoder_ring_clock/previews/contact_sheet.png`: all 12 reveal states.
- `radial_numbers/output_encoder_ring_clock/previews/angle_diagnostics.png`: stability check at 0, 1, 29, 30, and 31 degrees.
- `radial_numbers/output_encoder_ring_clock/rotation_360_slow_in_pause_numbers.gif`: encoder-ring animation.
- `radial_numbers/output_encoder_ring_clock/rotation_360_slow_in_pause_numbers_inverted.gif`: inverted encoder-ring animation.

![Radial encoder ring animation](radial_numbers/output_encoder_ring_clock/rotation_360_slow_in_pause_numbers.gif)

![Radial 12-number contact sheet](radial_numbers/output_encoder_ring_clock/previews/contact_sheet.png)

## Radial Options

Useful options for `radial_moire_numbers.py`:

- `--deadzone-mm`: black center radius; `0` keeps the pattern all the way to the center.
- `--invert`: invert base, mask display colors, and previews while preserving mask transparency.
- `--rings`: number of concentric encoder rings.
- `--encoder-angular-cells`: angular cell count; must be divisible by `--numbers`.
- `--clock-hold-deg`: angular stability window around each 30-degree target.
- `--preview-angles-deg`: extra physical mask rotations to render as previews.

More radial details are in `radial_numbers/README.md`.

## Install

```bash
pip install -r requirements.txt
```
