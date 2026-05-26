"""
Radial moire number generator.

Creates printable artwork where a rotating radial slit mask reveals one full
circle-sized number at a time.

Outputs:
  - radial_interlaced_base.png: print on paper
  - radial_barrier_mask.png: print on transparency
  - previews/reveal_01.png ... reveal_12.png: simulated mask rotations

Install:
  pip install pillow numpy
"""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


DEFAULT_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\ariblk.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\bahnschrift.ttf",
)


def mm_to_px(mm: float, dpi: int) -> int:
    return max(1, round(mm * dpi / 25.4))


def pick_font_path(requested: str | None) -> str | None:
    if requested:
        return requested

    for candidate in DEFAULT_FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate

    return None


def load_fitting_font(text: str, font_path: str | None, max_width: int, max_height: int) -> ImageFont.ImageFont:
    if not font_path:
        return ImageFont.load_default()

    lo = 1
    hi = max_width
    best = ImageFont.truetype(font_path, lo)
    probe = Image.new("L", (max_width, max_height), 0)
    draw = ImageDraw.Draw(probe)

    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, mid // 48))
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= max_width and height <= max_height:
            best = font
            lo = mid + 1
        else:
            hi = mid - 1

    return best


def make_number_frame(
    number: int,
    size_px: int,
    font_path: str | None,
    margin_ratio: float,
    supersample: int,
) -> Image.Image:
    work_size = size_px * supersample
    margin = int(work_size * margin_ratio)
    max_text = work_size - 2 * margin
    text = str(number)

    image = Image.new("L", (work_size, work_size), 0)
    draw = ImageDraw.Draw(image)

    font = load_fitting_font(text, font_path, max_text, max_text)
    stroke = max(2, work_size // 220)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (work_size - text_w) / 2 - bbox[0]
    y = (work_size - text_h) / 2 - bbox[1]

    draw.text((x, y), text, fill=255, font=font, stroke_width=stroke, stroke_fill=255)

    yy, xx = np.ogrid[:work_size, :work_size]
    center = (work_size - 1) / 2
    radius = work_size / 2 - 1
    outside_circle = (xx - center) ** 2 + (yy - center) ** 2 > radius**2
    arr = np.asarray(image).copy()
    arr[outside_circle] = 255

    return Image.fromarray(arr, "L").resize((size_px, size_px), Image.Resampling.LANCZOS).convert("RGB")


def make_angle_indices(
    size_px: int,
    n_frames: int,
    periods: int,
    rotation_steps: int = 0,
    deadzone_px: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = (size_px - 1) / 2
    y, x = np.indices((size_px, size_px))
    angles = (np.arctan2(y - center, x - center) + (2 * math.pi)) % (2 * math.pi)
    stripe_angle = (2 * math.pi) / (n_frames * periods)
    rotated_angles = (angles - rotation_steps * stripe_angle) % (2 * math.pi)
    stripe_indices = np.floor(rotated_angles / stripe_angle).astype(np.int32)
    frame_indices = stripe_indices % n_frames
    radius = size_px / 2 - 1
    distance_sq = (x - center) ** 2 + (y - center) ** 2
    inside_circle = distance_sq <= radius**2
    inside_deadzone = distance_sq <= deadzone_px**2
    return frame_indices, inside_circle, inside_deadzone


def make_polar_grids(size_px: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = (size_px - 1) / 2
    y, x = np.indices((size_px, size_px))
    angles_deg = (np.degrees(np.arctan2(y - center, x - center)) + 360.0) % 360.0
    radius_px = np.sqrt((x - center) ** 2 + (y - center) ** 2)
    return y, angles_deg, radius_px


def build_multi_ring_periods(n_rings: int, n_frames: int, first_period: int) -> list[int]:
    if n_rings < 1:
        raise ValueError("--rings must be at least 1")

    # Periods congruent to 1 modulo n_frames make a 360/n_frames degree physical
    # rotation advance the frame index by one in every ring.
    first_period = max(1, first_period)
    remainder = first_period % n_frames
    if remainder != 1:
        first_period += (1 - remainder) % n_frames

    center = (n_rings - 1) / 2
    periods = []
    for ring_index in range(n_rings):
        distance_from_center = abs(ring_index - center)
        period = first_period + int(round(distance_from_center)) * n_frames
        periods.append(period)
    return periods


def generate_multi_ring_spokes(
    n_rings: int,
    spokes_per_ring: int,
    n_frames: int,
    rotation_step_deg: float,
    hold_deg: float,
    seed: int,
) -> list[list[float]]:
    if spokes_per_ring < 1:
        raise ValueError("--ring-spokes must be at least 1")

    all_ring_spokes: list[list[float]] = []
    min_gap = hold_deg * 1.15
    residue_spacing = rotation_step_deg / spokes_per_ring
    if residue_spacing < min_gap:
        raise ValueError(
            "Too many --ring-spokes for the hold window. Lower --ring-spokes "
            "or --clock-hold-deg."
        )

    rng = random.Random(seed)
    global_offset = rng.random() * residue_spacing
    for ring_index in range(n_rings):
        ring_offset = ((ring_index + 0.5) / n_rings) * residue_spacing
        jitter = rng.uniform(-0.04, 0.04) * residue_spacing
        selected = [
            (
                (((ring_index * spokes_per_ring) + (segment_index * 5)) % n_frames) * rotation_step_deg
                + ((segment_index + 0.5) * residue_spacing + global_offset + ring_offset + jitter) % rotation_step_deg
            )
            % 360.0
            for segment_index in range(spokes_per_ring)
        ]
        all_ring_spokes.append(sorted(selected))

    return all_ring_spokes


def generate_encoder_ring_segments(
    n_rings: int,
    segments_per_ring: int,
    n_frames: int,
    rotation_step_deg: float,
    hold_deg: float,
    seed: int,
) -> list[list[float]]:
    return generate_multi_ring_spokes(
        n_rings,
        segments_per_ring,
        n_frames,
        rotation_step_deg,
        hold_deg,
        seed,
    )


def make_ring_indices(
    radius_px: np.ndarray,
    size_px: int,
    n_rings: int,
    deadzone_px: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    outer_radius = size_px / 2 - 1
    drawable_radius = max(1.0, outer_radius - deadzone_px)
    ring_width = drawable_radius / n_rings
    ring_indices = np.floor((radius_px - deadzone_px) / ring_width).astype(np.int32)
    ring_indices = np.clip(ring_indices, 0, n_rings - 1)
    inside_circle = radius_px <= outer_radius
    inside_deadzone = radius_px <= deadzone_px
    drawable_area = inside_circle & ~inside_deadzone
    return ring_indices, drawable_area, inside_deadzone


def ring_angle_matches(
    angles_deg: np.ndarray,
    target_angles: list[float],
    window_deg: float,
) -> np.ndarray:
    if not target_angles:
        return np.zeros(angles_deg.shape, dtype=bool)

    targets = np.asarray(sorted(angle % 360.0 for angle in target_angles), dtype=np.float32)
    flat_angles = angles_deg.ravel()
    insert_at = np.searchsorted(targets, flat_angles, side="left")
    previous_at = (insert_at - 1) % len(targets)
    next_at = insert_at % len(targets)
    previous_distance = angular_distance_deg(flat_angles, targets[previous_at])
    next_distance = angular_distance_deg(flat_angles, targets[next_at])
    return (np.minimum(previous_distance, next_distance).reshape(angles_deg.shape) <= window_deg / 2.0)


def angle_values_match(
    angle_values: np.ndarray,
    target_angles: list[float],
    window_deg: float,
) -> np.ndarray:
    if not target_angles:
        return np.zeros(angle_values.shape, dtype=bool)

    targets = np.asarray(sorted(angle % 360.0 for angle in target_angles), dtype=np.float32)
    insert_at = np.searchsorted(targets, angle_values, side="left")
    previous_at = (insert_at - 1) % len(targets)
    next_at = insert_at % len(targets)
    previous_distance = angular_distance_deg(angle_values, targets[previous_at])
    next_distance = angular_distance_deg(angle_values, targets[next_at])
    return np.minimum(previous_distance, next_distance) <= window_deg / 2.0


def angular_distance_deg(a: np.ndarray | float, b: float) -> np.ndarray | float:
    return np.abs((a - b + 180.0) % 360.0 - 180.0)


def generate_clock_spoke_angles(
    n_spokes: int,
    n_frames: int,
    rotation_step_deg: float,
    slit_angle_deg: float,
    seed: int,
) -> list[float]:
    rng = random.Random(seed)
    selected: list[float] = []
    occupied: list[float] = []
    min_gap = slit_angle_deg * 1.35

    # Greedy deterministic sampling. The selected mask is intentionally not
    # rotationally symmetric, so 30 degree turns can expose different frames.
    attempts = max(20000, n_spokes * 600)
    for _ in range(attempts):
        candidate = rng.random() * 360.0
        candidate_family = [
            (candidate + frame * rotation_step_deg) % 360.0
            for frame in range(n_frames)
        ]

        if all(
            angular_distance_deg(existing, family_angle) >= min_gap
            for existing in occupied
            for family_angle in candidate_family
        ):
            selected.append(candidate)
            occupied.extend(candidate_family)

        if len(selected) == n_spokes:
            return sorted(selected)

    raise ValueError(
        "Could not place non-overlapping clock spokes. Lower --clock-spokes, "
        "lower --clock-slit-angle-deg, or change --clock-seed."
    )


def make_clock_slit_area(
    size_px: int,
    spoke_angles: list[float],
    slit_angle_deg: float,
    rotation_deg: float,
    deadzone_px: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = (size_px - 1) / 2
    y, x = np.indices((size_px, size_px))
    angles = (np.degrees(np.arctan2(y - center, x - center)) + 360.0) % 360.0
    distance_sq = (x - center) ** 2 + (y - center) ** 2
    radius = size_px / 2 - 1
    inside_circle = distance_sq <= radius**2
    inside_deadzone = distance_sq <= deadzone_px**2

    targets = np.array(
        sorted((spoke_angle + rotation_deg) % 360.0 for spoke_angle in spoke_angles),
        dtype=np.float32,
    )
    flat_angles = angles.ravel()
    insert_at = np.searchsorted(targets, flat_angles, side="left")
    previous_at = (insert_at - 1) % len(targets)
    next_at = insert_at % len(targets)

    previous_distance = angular_distance_deg(flat_angles, targets[previous_at])
    next_distance = angular_distance_deg(flat_angles, targets[next_at])
    half_slit = slit_angle_deg / 2.0
    transparent_slits = np.minimum(previous_distance, next_distance).reshape((size_px, size_px)) <= half_slit
    transparent_slits &= inside_circle & ~inside_deadzone
    return transparent_slits, inside_circle, inside_deadzone


def create_interlaced_base(frames: list[Image.Image], periods: int, deadzone_px: int = 0) -> Image.Image:
    if not frames:
        raise ValueError("At least one frame is required.")

    size_px = frames[0].size[0]
    n_frames = len(frames)
    frame_indices, inside_circle, inside_deadzone = make_angle_indices(
        size_px,
        n_frames,
        periods,
        deadzone_px=deadzone_px,
    )
    drawable_area = inside_circle & ~inside_deadzone

    stacked = np.stack([np.asarray(frame.convert("RGB")) for frame in frames], axis=0)
    base = np.full((size_px, size_px, 3), 255, dtype=np.uint8)
    drawable_y, drawable_x = np.where(drawable_area)
    base[drawable_area] = stacked[frame_indices[drawable_area], drawable_y, drawable_x]
    base[inside_deadzone] = (0, 0, 0)
    return Image.fromarray(base, "RGB")


def create_clock_interlaced_base(
    frames: list[Image.Image],
    spoke_angles: list[float],
    base_window_deg: float,
    rotation_step_deg: float,
    deadzone_px: int = 0,
) -> Image.Image:
    if not frames:
        raise ValueError("At least one frame is required.")

    size_px = frames[0].size[0]
    base = np.full((size_px, size_px, 3), 255, dtype=np.uint8)
    inside_deadzone = None
    assigned = np.zeros((size_px, size_px), dtype=bool)

    for frame_index, frame in enumerate(frames):
        slit_area, _inside_circle, deadzone_area = make_clock_slit_area(
            size_px,
            spoke_angles,
            base_window_deg,
            frame_index * rotation_step_deg,
            deadzone_px,
        )
        frame_arr = np.asarray(frame.convert("RGB"))
        writable = slit_area & ~assigned
        base[writable] = frame_arr[writable]
        assigned |= writable
        inside_deadzone = deadzone_area

    if inside_deadzone is not None:
        base[inside_deadzone] = (0, 0, 0)

    return Image.fromarray(base, "RGB")


def create_multi_ring_clock_base(
    frames: list[Image.Image],
    ring_periods: list[int],
    deadzone_px: int = 0,
) -> Image.Image:
    if not frames:
        raise ValueError("At least one frame is required.")

    size_px = frames[0].size[0]
    n_frames = len(frames)
    y_indices, angles_deg, radius_px = make_polar_grids(size_px)
    ring_indices, drawable_area, inside_deadzone = make_ring_indices(
        radius_px,
        size_px,
        len(ring_periods),
        deadzone_px,
    )

    periods_by_pixel = np.take(np.asarray(ring_periods, dtype=np.float32), ring_indices)
    stripe_angle = 360.0 / (n_frames * periods_by_pixel)
    stripe_indices = np.floor(angles_deg / stripe_angle).astype(np.int32)
    frame_indices = stripe_indices % n_frames

    stacked = np.stack([np.asarray(frame.convert("RGB")) for frame in frames], axis=0)
    base = np.full((size_px, size_px, 3), 255, dtype=np.uint8)
    drawable_y, drawable_x = np.where(drawable_area)
    base[drawable_area] = stacked[frame_indices[drawable_area], drawable_y, drawable_x]
    base[inside_deadzone] = (0, 0, 0)
    return Image.fromarray(base, "RGB")


def create_held_multi_ring_clock_base(
    frames: list[Image.Image],
    ring_spokes: list[list[float]],
    hold_deg: float,
    rotation_step_deg: float,
    deadzone_px: int = 0,
) -> Image.Image:
    if not frames:
        raise ValueError("At least one frame is required.")

    size_px = frames[0].size[0]
    n_frames = len(frames)
    _y_indices, angles_deg, radius_px = make_polar_grids(size_px)
    ring_indices, drawable_area, inside_deadzone = make_ring_indices(
        radius_px,
        size_px,
        len(ring_spokes),
        deadzone_px,
    )

    stacked = np.stack([np.asarray(frame.convert("RGB")) for frame in frames], axis=0)
    base = np.full((size_px, size_px, 3), 255, dtype=np.uint8)

    for ring_index, spokes in enumerate(ring_spokes):
        ring_area = drawable_area & (ring_indices == ring_index)
        if not np.any(ring_area):
            continue
        ring_y, ring_x = np.where(ring_area)
        ring_angles = angles_deg[ring_y, ring_x]
        for frame_index in range(n_frames):
            target_angles = [
                (spoke + frame_index * rotation_step_deg) % 360.0
                for spoke in spokes
            ]
            matched = angle_values_match(ring_angles, target_angles, hold_deg)
            if np.any(matched):
                base[ring_y[matched], ring_x[matched]] = stacked[frame_index][ring_y[matched], ring_x[matched]]

    base[inside_deadzone] = (0, 0, 0)
    return Image.fromarray(base, "RGB")


def create_encoder_ring_clock_base(
    frames: list[Image.Image],
    ring_segments: list[list[float]],
    hold_deg: float,
    rotation_step_deg: float,
    deadzone_px: int = 0,
) -> Image.Image:
    return create_held_multi_ring_clock_base(
        frames,
        ring_segments,
        hold_deg,
        rotation_step_deg,
        deadzone_px,
    )


def create_radial_barrier_mask(
    size_px: int,
    n_frames: int,
    periods: int,
    rotation_steps: int = 0,
    deadzone_px: int = 0,
) -> Image.Image:
    frame_indices, inside_circle, inside_deadzone = make_angle_indices(
        size_px,
        n_frames,
        periods,
        rotation_steps,
        deadzone_px,
    )
    transparent_slits = (frame_indices == 0) & inside_circle & ~inside_deadzone

    mask = np.zeros((size_px, size_px, 4), dtype=np.uint8)
    mask[inside_circle] = (0, 0, 0, 255)
    mask[transparent_slits] = (0, 0, 0, 0)
    mask[inside_deadzone] = (0, 0, 0, 255)
    mask[~inside_circle] = (0, 0, 0, 0)

    return Image.fromarray(mask, "RGBA")


def create_clock_barrier_mask(
    size_px: int,
    spoke_angles: list[float],
    slit_angle_deg: float,
    rotation_deg: float = 0.0,
    deadzone_px: int = 0,
) -> Image.Image:
    transparent_slits, inside_circle, inside_deadzone = make_clock_slit_area(
        size_px,
        spoke_angles,
        slit_angle_deg,
        rotation_deg,
        deadzone_px,
    )

    mask = np.zeros((size_px, size_px, 4), dtype=np.uint8)
    mask[inside_circle] = (0, 0, 0, 255)
    mask[transparent_slits] = (0, 0, 0, 0)
    mask[inside_deadzone] = (0, 0, 0, 255)
    mask[~inside_circle] = (0, 0, 0, 0)
    return Image.fromarray(mask, "RGBA")


def create_multi_ring_clock_mask(
    size_px: int,
    n_frames: int,
    ring_periods: list[int],
    rotation_deg: float = 0.0,
    deadzone_px: int = 0,
) -> Image.Image:
    _y_indices, angles_deg, radius_px = make_polar_grids(size_px)
    ring_indices, drawable_area, inside_deadzone = make_ring_indices(
        radius_px,
        size_px,
        len(ring_periods),
        deadzone_px,
    )

    periods_by_pixel = np.take(np.asarray(ring_periods, dtype=np.float32), ring_indices)
    stripe_angle = 360.0 / (n_frames * periods_by_pixel)
    rotated_angles = (angles_deg - rotation_deg) % 360.0
    stripe_indices = np.floor(rotated_angles / stripe_angle).astype(np.int32)
    transparent_slits = (stripe_indices % n_frames == 0) & drawable_area

    inside_circle = drawable_area | inside_deadzone
    mask = np.zeros((size_px, size_px, 4), dtype=np.uint8)
    mask[inside_circle] = (0, 0, 0, 255)
    mask[transparent_slits] = (0, 0, 0, 0)
    mask[inside_deadzone] = (0, 0, 0, 255)
    mask[~inside_circle] = (0, 0, 0, 0)
    return Image.fromarray(mask, "RGBA")


def create_held_multi_ring_clock_mask(
    size_px: int,
    ring_spokes: list[list[float]],
    slit_angle_deg: float,
    rotation_deg: float = 0.0,
    deadzone_px: int = 0,
) -> Image.Image:
    _y_indices, angles_deg, radius_px = make_polar_grids(size_px)
    ring_indices, drawable_area, inside_deadzone = make_ring_indices(
        radius_px,
        size_px,
        len(ring_spokes),
        deadzone_px,
    )

    transparent_slits = np.zeros((size_px, size_px), dtype=bool)
    for ring_index, spokes in enumerate(ring_spokes):
        ring_area = drawable_area & (ring_indices == ring_index)
        if not np.any(ring_area):
            continue
        ring_y, ring_x = np.where(ring_area)
        ring_angles = angles_deg[ring_y, ring_x]
        target_angles = [(spoke + rotation_deg) % 360.0 for spoke in spokes]
        matched = angle_values_match(ring_angles, target_angles, slit_angle_deg)
        transparent_slits[ring_y[matched], ring_x[matched]] = True

    inside_circle = drawable_area | inside_deadzone
    mask = np.zeros((size_px, size_px, 4), dtype=np.uint8)
    mask[inside_circle] = (0, 0, 0, 255)
    mask[transparent_slits] = (0, 0, 0, 0)
    mask[inside_deadzone] = (0, 0, 0, 255)
    mask[~inside_circle] = (0, 0, 0, 0)
    return Image.fromarray(mask, "RGBA")


def create_encoder_ring_clock_mask(
    size_px: int,
    ring_segments: list[list[float]],
    slit_angle_deg: float,
    rotation_deg: float = 0.0,
    deadzone_px: int = 0,
) -> Image.Image:
    return create_held_multi_ring_clock_mask(
        size_px,
        ring_segments,
        slit_angle_deg,
        rotation_deg,
        deadzone_px,
    )


def make_polar_cell_indices(
    size_px: int,
    n_rings: int,
    angular_cells: int,
    deadzone_px: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    _y_indices, angles_deg, radius_px = make_polar_grids(size_px)
    ring_indices, drawable_area, inside_deadzone = make_ring_indices(
        radius_px,
        size_px,
        n_rings,
        deadzone_px,
    )
    angle_indices = np.floor(angles_deg / (360.0 / angular_cells)).astype(np.int32)
    angle_indices = np.clip(angle_indices, 0, angular_cells - 1)
    return ring_indices, angle_indices, drawable_area, inside_deadzone


def make_encoder_selector(
    n_rings: int,
    cells_per_hour: int,
    n_frames: int,
    seed: int,
    group_cells: int = 1,
) -> np.ndarray:
    rng = random.Random(seed)
    group_cells = max(1, group_cells)
    selector = np.zeros((n_rings, cells_per_hour), dtype=np.int32)
    for ring in range(n_rings):
        for group_start in range(0, cells_per_hour, group_cells):
            # Each ring/residue pair picks one of the 12 physical hour slots.
            # Randomizing by short residue groups avoids a strong spiral artifact
            # while keeping small rotations inside the same selected hour.
            selected = rng.randrange(n_frames)
            selector[ring, group_start : group_start + group_cells] = selected
    return selector


def create_polar_block_encoder_base(
    frames: list[Image.Image],
    n_rings: int,
    angular_cells: int,
    seed: int,
    hold_deg: float,
    deadzone_px: int = 0,
) -> Image.Image:
    if not frames:
        raise ValueError("At least one frame is required.")

    size_px = frames[0].size[0]
    n_frames = len(frames)
    if angular_cells % n_frames != 0:
        raise ValueError("--encoder-angular-cells must be divisible by --numbers")

    cells_per_hour = angular_cells // n_frames
    cell_angle_deg = 360.0 / angular_cells
    selector_group_cells = max(1, round(hold_deg / cell_angle_deg))
    selector = make_encoder_selector(n_rings, cells_per_hour, n_frames, seed, selector_group_cells)
    ring_indices, angle_indices, drawable_area, inside_deadzone = make_polar_cell_indices(
        size_px,
        n_rings,
        angular_cells,
        deadzone_px,
    )

    base = np.zeros((size_px, size_px, 3), dtype=np.uint8)
    stacked = np.stack([np.asarray(frame.convert("RGB")) for frame in frames], axis=0)
    for frame_index in range(n_frames):
        frame_luma = stacked[frame_index].mean(axis=2)
        source_angle_indices = (angle_indices - frame_index * cells_per_hour) % angular_cells
        source_residues = source_angle_indices % cells_per_hour
        source_hours = source_angle_indices // cells_per_hour
        selected_hour = selector[ring_indices, source_residues]
        frame_area = drawable_area & (source_hours == selected_hour)
        ink_area = frame_area & (frame_luma > 127)
        base[ink_area] = (255, 255, 255)

    base[~drawable_area & ~inside_deadzone] = (255, 255, 255)
    base[inside_deadzone] = (0, 0, 0)
    return Image.fromarray(base, "RGB")


def create_polar_block_encoder_mask(
    size_px: int,
    n_frames: int,
    n_rings: int,
    angular_cells: int,
    seed: int,
    hold_deg: float = 0.0,
    rotation_deg: float = 0.0,
    deadzone_px: int = 0,
) -> Image.Image:
    if angular_cells % n_frames != 0:
        raise ValueError("--encoder-angular-cells must be divisible by --numbers")

    cells_per_hour = angular_cells // n_frames
    cell_angle_deg = 360.0 / angular_cells
    selector_group_cells = max(1, round(hold_deg / cell_angle_deg))
    rotation_cells = round(rotation_deg / (360.0 / angular_cells))
    selector = make_encoder_selector(n_rings, cells_per_hour, n_frames, seed, selector_group_cells)
    ring_indices, angle_indices, drawable_area, inside_deadzone = make_polar_cell_indices(
        size_px,
        n_rings,
        angular_cells,
        deadzone_px,
    )

    unrotated_angle_indices = (angle_indices - rotation_cells) % angular_cells
    residues = unrotated_angle_indices % cells_per_hour
    hour_indices = unrotated_angle_indices // cells_per_hour
    transparent_cells = drawable_area & (hour_indices == selector[ring_indices, residues])

    inside_circle = drawable_area | inside_deadzone
    mask = np.zeros((size_px, size_px, 4), dtype=np.uint8)
    mask[inside_circle] = (0, 0, 0, 255)
    mask[transparent_cells] = (0, 0, 0, 0)
    mask[inside_deadzone] = (0, 0, 0, 255)
    mask[~inside_circle] = (0, 0, 0, 0)
    return Image.fromarray(mask, "RGBA")


def composite_preview(base: Image.Image, mask: Image.Image) -> Image.Image:
    preview = base.convert("RGBA")
    preview.alpha_composite(mask)
    return preview.convert("RGB")


def invert_image(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        rgb = ImageOps.invert(image.convert("RGB"))
        alpha = image.getchannel("A")
        inverted = rgb.convert("RGBA")
        inverted.putalpha(alpha)
        return inverted
    return ImageOps.invert(image.convert("RGB"))


def parse_preview_angles(value: str | None) -> list[float]:
    if not value:
        return []
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate radial moire artwork that reveals numbers 1-12.")
    parser.add_argument("--output", default="radial_numbers/output", help="Output folder")
    parser.add_argument("--diameter-mm", type=float, default=180.0, help="Printed circle diameter")
    parser.add_argument("--dpi", type=int, default=400, help="Output DPI")
    parser.add_argument("--numbers", type=int, default=12, help="How many numbers to generate")
    parser.add_argument(
        "--mode",
        choices=("stable-repeating", "clock-key", "multi-ring-clock", "encoder-ring-clock"),
        default=None,
        help=(
            "Generation mode. stable-repeating is the visually stable 96-period path; "
            "clock-key uses explicit angle reveals; encoder-ring-clock uses broken "
            "ring segments for 30-degree clock reveals."
        ),
    )
    parser.add_argument(
        "--stable-path",
        action="store_true",
        help="Shortcut for --mode stable-repeating --periods 96.",
    )
    parser.add_argument(
        "--periods",
        type=int,
        default=96,
        help="Repeated moire periods around the circle. Higher values create finer radial slits.",
    )
    parser.add_argument("--font", default=None, help="Optional path to a .ttf/.otf font")
    parser.add_argument("--margin-ratio", type=float, default=0.04, help="Text margin inside the circle")
    parser.add_argument("--deadzone-mm", type=float, default=0.0, help="Black center radius, in millimeters")
    parser.add_argument(
        "--rotation-step-deg",
        type=float,
        default=None,
        help="Use clock-key mode and reveal each next number after this many degrees. Use 30 for a 12-hour clock.",
    )
    parser.add_argument(
        "--clock-spokes",
        type=int,
        default=96,
        help="Clock-key mode only: number of transparent radial slits in the mask.",
    )
    parser.add_argument(
        "--clock-slit-angle-deg",
        type=float,
        default=1.0,
        help="Clock-key mode only: angular width of each transparent slit.",
    )
    parser.add_argument(
        "--clock-hold-deg",
        type=float,
        default=3.0,
        help="Clock modes: angular window where each number remains visible around its target angle.",
    )
    parser.add_argument("--clock-seed", type=int, default=1234, help="Clock-key mode only: deterministic mask layout seed.")
    parser.add_argument("--rings", type=int, default=120, help="Encoder-ring-clock only: number of concentric rings.")
    parser.add_argument(
        "--ring-spokes",
        type=int,
        default=8,
        help="Legacy encoder segment setting; polar block encoder does not use it.",
    )
    parser.add_argument(
        "--encoder-angular-cells",
        type=int,
        default=360,
        help="Encoder-ring-clock only: angular cell count. Must be divisible by --numbers.",
    )
    parser.add_argument("--supersample", type=int, default=3, help="Text rendering scale for smoother edges")
    parser.add_argument(
        "--invert",
        action="store_true",
        help="Invert generated base, mask display colors, and previews. RGBA transparency is preserved.",
    )
    parser.add_argument(
        "--preview-angles-deg",
        default=None,
        help="Comma-separated extra physical mask rotations to preview, e.g. 29,30,31.",
    )
    parser.add_argument("--no-previews", action="store_true", help="Skip simulated reveal preview images")
    args = parser.parse_args()
    preview_angles = parse_preview_angles(args.preview_angles_deg)

    if args.numbers < 2:
        raise ValueError("--numbers must be at least 2")
    if args.periods < 1:
        raise ValueError("--periods must be at least 1")
    if not 0 <= args.margin_ratio < 0.4:
        raise ValueError("--margin-ratio must be between 0 and 0.4")
    if args.deadzone_mm < 0:
        raise ValueError("--deadzone-mm must be 0 or greater")
    if args.deadzone_mm >= args.diameter_mm / 2:
        raise ValueError("--deadzone-mm must be smaller than the circle radius")
    if args.stable_path and args.mode in {"clock-key", "multi-ring-clock", "encoder-ring-clock"}:
        raise ValueError("--stable-path cannot be combined with clock modes")

    mode = args.mode
    if args.stable_path:
        mode = "stable-repeating"
        args.periods = 96
    elif mode is None:
        mode = "clock-key" if args.rotation_step_deg is not None else "stable-repeating"

    if mode in {"clock-key", "multi-ring-clock", "encoder-ring-clock"}:
        if args.rotation_step_deg is None:
            args.rotation_step_deg = 30.0
        if args.rotation_step_deg <= 0:
            raise ValueError("--rotation-step-deg must be greater than 0")
        expected_step = 360.0 / args.numbers
        if abs(args.rotation_step_deg - expected_step) > 1e-9 and mode in {"multi-ring-clock", "encoder-ring-clock"}:
            raise ValueError(f"--mode {mode} currently requires --rotation-step-deg {expected_step:g}")
    if mode == "clock-key":
        if args.clock_spokes < 1:
            raise ValueError("--clock-spokes must be at least 1")
        if args.clock_slit_angle_deg <= 0:
            raise ValueError("--clock-slit-angle-deg must be greater than 0")
        if args.clock_hold_deg < args.clock_slit_angle_deg:
            raise ValueError("--clock-hold-deg must be greater than or equal to --clock-slit-angle-deg")
        if args.clock_hold_deg >= args.rotation_step_deg:
            raise ValueError("--clock-hold-deg must be smaller than --rotation-step-deg")
    if mode in {"multi-ring-clock", "encoder-ring-clock"}:
        if args.rings < 1:
            raise ValueError("--rings must be at least 1")
        if mode == "encoder-ring-clock":
            if args.encoder_angular_cells < args.numbers:
                raise ValueError("--encoder-angular-cells must be at least --numbers")
            if args.encoder_angular_cells % args.numbers != 0:
                raise ValueError("--encoder-angular-cells must be divisible by --numbers")
        else:
            if args.ring_spokes < 1:
                raise ValueError("--ring-spokes must be at least 1")
            if args.clock_slit_angle_deg <= 0:
                raise ValueError("--clock-slit-angle-deg must be greater than 0")
            if args.clock_hold_deg < args.clock_slit_angle_deg:
                raise ValueError("--clock-hold-deg must be greater than or equal to --clock-slit-angle-deg")
            if args.clock_hold_deg >= args.rotation_step_deg:
                raise ValueError("--clock-hold-deg must be smaller than --rotation-step-deg")
    if mode == "stable-repeating" and args.rotation_step_deg is not None:
        raise ValueError("--rotation-step-deg only applies to clock modes")

    size_px = mm_to_px(args.diameter_mm, args.dpi)
    deadzone_px = 0 if args.deadzone_mm == 0 else mm_to_px(args.deadzone_mm, args.dpi)
    font_path = pick_font_path(args.font)

    frames = [
        make_number_frame(i, size_px, font_path, args.margin_ratio, max(1, args.supersample))
        for i in range(1, args.numbers + 1)
    ]
    clock_mode = mode == "clock-key"
    encoder_block_mode = mode == "encoder-ring-clock"
    multi_ring_mode = mode == "multi-ring-clock"
    spoke_angles = None
    ring_periods = None
    ring_spokes = None
    if clock_mode:
        spoke_angles = generate_clock_spoke_angles(
            args.clock_spokes,
            args.numbers,
            args.rotation_step_deg,
            args.clock_slit_angle_deg,
            args.clock_seed,
        )
        base = create_clock_interlaced_base(
            frames,
            spoke_angles,
            args.clock_hold_deg,
            args.rotation_step_deg,
            deadzone_px,
        )
        mask = create_clock_barrier_mask(
            size_px,
            spoke_angles,
            args.clock_slit_angle_deg,
            deadzone_px=deadzone_px,
        )
    elif encoder_block_mode:
        base = create_polar_block_encoder_base(
            frames,
            args.rings,
            args.encoder_angular_cells,
            args.clock_seed,
            args.clock_hold_deg,
            deadzone_px,
        )
        mask = create_polar_block_encoder_mask(
            size_px,
            args.numbers,
            args.rings,
            args.encoder_angular_cells,
            args.clock_seed,
            args.clock_hold_deg,
            deadzone_px=deadzone_px,
        )
    elif multi_ring_mode:
        ring_spokes = generate_encoder_ring_segments(
            args.rings,
            args.ring_spokes,
            args.numbers,
            args.rotation_step_deg,
            args.clock_hold_deg,
            args.clock_seed,
        )
        base = create_encoder_ring_clock_base(
            frames,
            ring_spokes,
            args.clock_hold_deg,
            args.rotation_step_deg,
            deadzone_px,
        )
        mask = create_encoder_ring_clock_mask(
            size_px,
            ring_spokes,
            args.clock_slit_angle_deg,
            deadzone_px=deadzone_px,
        )
    else:
        base = create_interlaced_base(frames, args.periods, deadzone_px)
        mask = create_radial_barrier_mask(size_px, args.numbers, args.periods, deadzone_px=deadzone_px)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    base_path = out_dir / "radial_interlaced_base.png"
    mask_path = out_dir / "radial_barrier_mask.png"
    output_base = invert_image(base) if args.invert else base
    output_mask = invert_image(mask) if args.invert else mask
    output_base.save(base_path, dpi=(args.dpi, args.dpi))
    output_mask.save(mask_path, dpi=(args.dpi, args.dpi))

    if not args.no_previews:
        preview_dir = out_dir / "previews"
        preview_dir.mkdir(exist_ok=True)
        for step in range(args.numbers):
            if clock_mode:
                rotated_mask = create_clock_barrier_mask(
                    size_px,
                    spoke_angles or [],
                    args.clock_slit_angle_deg,
                    rotation_deg=step * args.rotation_step_deg,
                    deadzone_px=deadzone_px,
                )
            elif encoder_block_mode:
                rotated_mask = create_polar_block_encoder_mask(
                    size_px,
                    args.numbers,
                    args.rings,
                    args.encoder_angular_cells,
                    args.clock_seed,
                    args.clock_hold_deg,
                    rotation_deg=step * args.rotation_step_deg,
                    deadzone_px=deadzone_px,
                )
            elif multi_ring_mode:
                rotated_mask = create_encoder_ring_clock_mask(
                    size_px,
                    ring_spokes or [],
                    args.clock_slit_angle_deg,
                    rotation_deg=step * args.rotation_step_deg,
                    deadzone_px=deadzone_px,
                )
            else:
                rotated_mask = create_radial_barrier_mask(
                    size_px,
                    args.numbers,
                    args.periods,
                    rotation_steps=step,
                    deadzone_px=deadzone_px,
                )
            preview = composite_preview(output_base, invert_image(rotated_mask) if args.invert else rotated_mask)
            preview.save(preview_dir / f"reveal_{step + 1:02d}.png", dpi=(args.dpi, args.dpi))
        for angle_deg in preview_angles:
            if clock_mode:
                rotated_mask = create_clock_barrier_mask(
                    size_px,
                    spoke_angles or [],
                    args.clock_slit_angle_deg,
                    rotation_deg=angle_deg,
                    deadzone_px=deadzone_px,
                )
            elif encoder_block_mode:
                rotated_mask = create_polar_block_encoder_mask(
                    size_px,
                    args.numbers,
                    args.rings,
                    args.encoder_angular_cells,
                    args.clock_seed,
                    args.clock_hold_deg,
                    rotation_deg=angle_deg,
                    deadzone_px=deadzone_px,
                )
            elif multi_ring_mode:
                rotated_mask = create_encoder_ring_clock_mask(
                    size_px,
                    ring_spokes or [],
                    args.clock_slit_angle_deg,
                    rotation_deg=angle_deg,
                    deadzone_px=deadzone_px,
                )
            else:
                step_angle = 360.0 / (args.numbers * args.periods)
                rotated_mask = create_radial_barrier_mask(
                    size_px,
                    args.numbers,
                    args.periods,
                    rotation_steps=round(angle_deg / step_angle),
                    deadzone_px=deadzone_px,
                )
            angle_label = f"{angle_deg:.3f}".replace("-", "neg_").replace(".", "p")
            preview = composite_preview(output_base, invert_image(rotated_mask) if args.invert else rotated_mask)
            preview.save(preview_dir / f"angle_{angle_label}.png", dpi=(args.dpi, args.dpi))

    if clock_mode:
        slit_angle = args.rotation_step_deg
        period_angle = args.rotation_step_deg * args.numbers
        outer_slit_width_mm = 2 * math.pi * (args.diameter_mm / 2) * (args.clock_slit_angle_deg / 360.0)
    elif encoder_block_mode:
        slit_angle = args.rotation_step_deg
        period_angle = 360.0
        outer_slit_width_mm = 2 * math.pi * (args.diameter_mm / 2) / args.encoder_angular_cells
    elif multi_ring_mode:
        slit_angle = args.rotation_step_deg
        period_angle = 360.0
        outer_slit_width_mm = 2 * math.pi * (args.diameter_mm / 2) * (args.clock_slit_angle_deg / 360.0)
    else:
        slit_angle = 360.0 / (args.numbers * args.periods)
        period_angle = 360.0 / args.periods
        outer_slit_width_mm = 2 * math.pi * (args.diameter_mm / 2) / (args.numbers * args.periods)

    print("Created radial moire files:")
    print(f"  Base: {base_path}")
    print(f"  Mask: {mask_path}")
    print()
    print("Geometry:")
    print(f"  Diameter: {args.diameter_mm:.2f} mm ({size_px}px at {args.dpi} DPI)")
    print(f"  Numbers: {args.numbers}")
    if clock_mode:
        print("  Mode: clock-key rotation")
        print(f"  Mask spokes: {args.clock_spokes}")
        print(f"  Clock slit angle: {args.clock_slit_angle_deg:.4f} degrees")
        print(f"  Clock hold window: {args.clock_hold_deg:.4f} degrees")
    elif encoder_block_mode:
        print("  Mode: encoder ring clock")
        print(f"  Rings: {args.rings}")
        print(f"  Angular cells: {args.encoder_angular_cells}")
        print(f"  Cells per 30-degree hour: {args.encoder_angular_cells // args.numbers}")
    elif multi_ring_mode:
        print("  Mode: multi-ring clock")
        print(f"  Rings: {args.rings}")
        print(f"  Encoder segments per ring: {args.ring_spokes}")
        print(f"  Clock slit angle: {args.clock_slit_angle_deg:.4f} degrees")
        print(f"  Clock hold window: {args.clock_hold_deg:.4f} degrees")
    else:
        print("  Mode: repeating radial scanimation")
        print(f"  Periods around circle: {args.periods}")
        if args.stable_path:
            print("  Stable path: enabled")
    print(f"  Center deadzone radius: {args.deadzone_mm:.2f} mm ({deadzone_px}px)")
    print(f"  Rotation per number: {slit_angle:.4f} degrees")
    print(f"  Pattern repeat angle: {period_angle:.4f} degrees")
    print(f"  Outer-edge transparent slit width: {outer_slit_width_mm:.3f} mm")
    if args.invert:
        print("  Invert: enabled")
    print()
    print("Print radial_interlaced_base.png on paper and radial_barrier_mask.png on transparency.")
    print("Rotate the transparency by one rotation-per-number step to reveal the next number.")


if __name__ == "__main__":
    main()
