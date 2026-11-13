"""One appearance scheme for a whole area.

Colour chaos comes from every object choosing its own colours. Here each
building is assigned a material class by rule, and its colours are drawn from
one palette shared by the area. Measured colour only steers the choice inside
that palette (warm or cool, which brick hue); it never sets raw pixel colour,
because captured facades are mostly shadow and sky reflection.

A style may replace the palette; the rules stay the same.
"""

import colorsys
import hashlib
import re

DEFAULT_PALETTE = {
    "glass": ["#7d9db5", "#8aa9bd", "#6f90aa", "#93b0c2", "#7f9fae"],
    "glass_frame": "#e4e9ec",
    "stone": ["#d8cebc", "#cfc5b3", "#e0d6c5", "#cbc1b0", "#d5ccbf"],
    "concrete": ["#c3c5c2", "#b8bbb9", "#cccdc8", "#bdbfbc"],
    "brick": ["#a6604f", "#9a594b", "#ae6954"],
    "trim": "#e9e2d3",
    "window": "#33485a",
    "roof_flat": ["#9a9e9f", "#a6a9a8", "#8f9496"],
    "roof_pitched": ["#5a6478", "#636d80", "#4f5a6e"],
    "roof_plant": "#b4b7b6",
    "canopy": "#dfe3e4",
    "ground": "#c9ccc5",
    "plaza": "#d6d2c6",
    "road": "#5f6368",
    "sidewalk": "#bfbdb4",
    "marking": "#f3f2ea",
    "rail_bed": "#8a8479",
    "rail": "#4a4d52",
    "deck": "#a9aba8",
    "green": "#86b565",
    "water": "#74a8bd",
    "leaf": ["#6fa04f", "#7dae58", "#5f9148", "#8ab860"],
    "bark": "#6d5a48",
    "metal": "#555b61",
    "background": "#dbe7ee",
}


def pick(options, key):
    """Stable choice from a list: the same object always gets the same colour."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return options[digest[0] % len(options)]


def hsv(rgb):
    return colorsys.rgb_to_hsv(*(v / 255.0 for v in rgb))


def classify(building):
    """Material class from tags, size and (weakly) measured colour."""
    height = building["height_m"] - building.get("min_height", 0)
    use = building.get("use") or ""
    material = (building.get("material_tag") or "").lower()
    wall = (building.get("colours_measured") or {}).get("wall_rgb")
    hue, saturation, _ = hsv(wall) if wall else (0, 0, 0)
    if use == "roof" or building["tags"].get("railway") == "platform":
        return "canopy"
    if building.get("min_height", 0) > 1:
        return "raised"
    if material == "brick" or (
        wall and (hue <= 0.07 or hue >= 0.96) and saturation >= 0.3 and height < 45
    ):
        return "brick"
    if height >= 45:
        if material in ("stone", "concrete", "sandstone", "limestone", "granite"):
            return "stone_tower"
        if material in ("glass", "metal") or not wall:
            return "glass_tower"
        return (
            "stone_tower"
            if 0.05 <= hue <= 0.17 and saturation >= 0.12
            else "glass_tower"
        )
    if height >= 14:
        return "midrise"
    return "lowrise"


def building_appearance(building, palette):
    kind = classify(building)
    key = building["id"]
    measured = building.get("colours_measured") or {}
    wall = measured.get("wall_rgb")
    warm = wall is not None and 0.03 <= hsv(wall)[0] <= 0.2 and hsv(wall)[1] >= 0.1
    pitched = building["roof"]["form"] != "flat"
    appearance = {
        "class": kind,
        "trim": palette["trim"],
        "glass": palette["window"],
        "roof": pick(palette["roof_pitched" if pitched else "roof_flat"], key + "roof"),
        "plant": palette["roof_plant"],
        "frame": palette["glass_frame"],
    }
    if kind == "glass_tower":
        appearance["wall"] = pick(palette["glass"], key)
    elif kind == "brick":
        appearance["wall"] = pick(palette["brick"], key)
    elif kind == "canopy":
        appearance["wall"] = palette["canopy"]
        appearance["roof"] = palette["canopy"]
    elif kind in ("stone_tower", "midrise", "lowrise", "raised"):
        appearance["wall"] = pick(
            palette["stone" if (warm or not wall) else "concrete"], key
        )
    appearance["basis"] = (
        "class from tags, height and measured wall hue; colour from the shared area palette"
        if wall
        else "class from tags and height; colour from the shared area palette (wall not seen)"
    )
    tag = building.get("colour_tag")
    if tag and re.fullmatch(r"#[0-9a-fA-F]{6}", tag):
        appearance["wall"], appearance["basis"] = tag, "map tag building:colour"
    roof_tag = building.get("roof_colour_tag")
    if roof_tag and re.fullmatch(r"#[0-9a-fA-F]{6}", roof_tag):
        appearance["roof"] = roof_tag
        appearance["roof_basis"] = "map tag roof:colour"
    return appearance


def apply(area, palette=None):
    palette = {} if palette is None else palette
    if not isinstance(palette, dict) or set(palette) - set(DEFAULT_PALETTE):
        raise ValueError("AREA_PALETTE_UNKNOWN_KEYS")
    for key, value in palette.items():
        colours = value if isinstance(DEFAULT_PALETTE[key], list) else [value]
        if (
            (isinstance(DEFAULT_PALETTE[key], list) and not isinstance(value, list))
            or not colours
            or any(
                not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c)
                for c in colours
            )
        ):
            raise ValueError("AREA_PALETTE_INVALID_COLOUR: " + key)
    palette = {**DEFAULT_PALETTE, **palette}
    for building in area["buildings"]:
        building["appearance"] = building_appearance(building, palette)
    area["palette"] = palette
    return area
