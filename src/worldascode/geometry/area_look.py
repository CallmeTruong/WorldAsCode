"""Styles: how observed facts are rendered.

Observation says what each building is: its masses, its two facade tones, how
much of it is glazing, whether it reads as floor bands or vertical fins, its
roof tone, and the tones of the ground. A style is a small set of rules that
turns those facts into the colours, proportions and light of one rendering.
Changing the style changes every object consistently and never touches the
measured geometry. The scene stays procedural: the same recipes run with
different parameters.

A style is plain JSON, so it can be written by hand or by an agent.
"""

import colorsys
import copy
import math
import re

HEX = re.compile(r"#[0-9a-fA-F]{6}")

STYLES = {
    # As observed, with the capture's shadow lifted a little.
    "faithful": {
        "colour": {"saturation": 1.1, "value_floor": 0.12, "value_gain": 1.05},
        "glass": {"saturation": 1.0, "value_gain": 0.95},
        "window_scale": 1.0,
        "light": {
            "background": "#b9cad8",
            "ground": "#6b7075",
            "sun": 2.6,
            "sky": 1.3,
            "exposure": 0.95,
        },
    },
    # Clean, bright, slightly saturated: an illustrated city map.
    "illustrated": {
        "colour": {"saturation": 1.5, "value_floor": 0.42, "value_gain": 0.62},
        "glass": {
            "saturation": 1.7,
            "value_floor": 0.38,
            "value_gain": 0.6,
            "tint": "#4fa3c7",
            "tint_strength": 0.35,
        },
        "window_scale": 1.1,
        "ground": {"green": "#8cc56a", "water": "#6fb4cf", "leaf": "#79b85a"},
        "light": {
            "background": "#dff0f7",
            "ground": "#d9dccf",
            "sun": 3.0,
            "sky": 1.8,
            "exposure": 1.0,
        },
    },
    # Soft low-contrast model with a warm tint.
    "pastel": {
        "colour": {
            "saturation": 0.55,
            "value_floor": 0.62,
            "value_gain": 0.36,
            "tint": "#f3d9c4",
            "tint_strength": 0.3,
        },
        "glass": {
            "saturation": 0.6,
            "value_floor": 0.5,
            "value_gain": 0.4,
            "tint": "#9fc3d6",
            "tint_strength": 0.45,
        },
        "window_scale": 0.9,
        "ground": {"green": "#b9d8a6", "water": "#a9d1de", "leaf": "#a8cf95"},
        "light": {
            "background": "#f6eee6",
            "ground": "#ebe3d8",
            "sun": 2.4,
            "sky": 2.0,
            "exposure": 1.05,
        },
    },
    # Dark city with glowing glazing; meant to be viewed at night.
    "neon-night": {
        "colour": {
            "saturation": 0.7,
            "value_floor": 0.06,
            "value_gain": 0.3,
            "tint": "#1c2440",
            "tint_strength": 0.5,
        },
        "glass": {
            "saturation": 2.0,
            "value_floor": 0.35,
            "value_gain": 0.5,
            "tint": "#19d3ff",
            "tint_strength": 0.55,
        },
        "window_scale": 1.15,
        "glow": "#59e0ff",
        "ground": {
            "green": "#1f3a34",
            "water": "#12304a",
            "leaf": "#2f6b52",
            "road": "#181b24",
            "sidewalk": "#2a2e3a",
        },
        "light": {
            "background": "#0b1020",
            "ground": "#11141d",
            "sun": 0.5,
            "sky": 0.5,
            "exposure": 1.1,
        },
        "hour": 21,
    },
    # Untextured study model.
    "clay": {
        "colour": {
            "saturation": 0.0,
            "value_floor": 0.7,
            "value_gain": 0.22,
            "tint": "#e8e1d6",
            "tint_strength": 0.35,
        },
        "glass": {"saturation": 0.0, "value_floor": 0.5, "value_gain": 0.2},
        "window_scale": 0.85,
        "ground": {"green": "#cfd3c6", "water": "#c5cdd3", "leaf": "#bfc6b5"},
        "light": {
            "background": "#f2efea",
            "ground": "#e2ded6",
            "sun": 3.2,
            "sky": 1.6,
            "exposure": 1.0,
        },
    },
}


def to_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(v)))) for v in rgb)


def from_hex(text):
    return [int(text[i : i + 2], 16) for i in (1, 3, 5)]


def render(rgb, rule):
    """Apply one colour rule to an observed colour."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))
    s = min(1.0, s * rule.get("saturation", 1.0))
    v = min(1.0, rule.get("value_floor", 0.0) + v * rule.get("value_gain", 1.0))
    out = [c * 255 for c in colorsys.hsv_to_rgb(h, s, v)]
    if rule.get("tint"):
        tint, k = from_hex(rule["tint"]), rule.get("tint_strength", 0.2)
        out = [a * (1 - k) + b * k for a, b in zip(out, tint)]
    return to_hex(out)


def lighten(colour, amount):
    return to_hex([c + (255 - c) * amount for c in from_hex(colour)])


def validate(style):
    allowed = {
        "colour",
        "glass",
        "window_scale",
        "ground",
        "light",
        "glow",
        "hour",
        "name",
        "facade_mode",
        "relief_m",
        "bay_scale",
        "roof_detail",
        "tree_detail",
        "projection",
    }
    if not isinstance(style, dict) or set(style) - allowed:
        raise ValueError("AREA_STYLE_UNKNOWN_KEYS")
    for section in ("colour", "glass"):
        rule = style.get(section, {})
        if not isinstance(rule, dict):
            raise ValueError("AREA_STYLE_INVALID_COLOUR_RULE")
        if set(rule) - {
            "saturation",
            "value_floor",
            "value_gain",
            "tint",
            "tint_strength",
        }:
            raise ValueError("AREA_STYLE_UNKNOWN_COLOUR_RULE")
        if "tint" in rule and not HEX.fullmatch(str(rule["tint"])):
            raise ValueError("AREA_STYLE_INVALID_TINT")
        if any(
            isinstance(rule[k], bool)
            or not isinstance(rule[k], (int, float))
            or not math.isfinite(rule[k])
            or not 0 <= rule[k] <= (1 if k == "tint_strength" else 4)
            for k in rule
            if k != "tint"
        ):
            raise ValueError("AREA_STYLE_INVALID_NUMBER")
    if not isinstance(style.get("ground", {}), dict) or not isinstance(
        style.get("light", {}), dict
    ):
        raise ValueError("AREA_STYLE_INVALID_SECTION")
    if set(style.get("ground", {})) - {
        "road",
        "sidewalk",
        "rail_bed",
        "green",
        "water",
        "plaza",
        "leaf",
    }:
        raise ValueError("AREA_STYLE_UNKNOWN_GROUND_KEY")
    if set(style.get("light", {})) - {"background", "ground", "sun", "sky", "exposure"}:
        raise ValueError("AREA_STYLE_UNKNOWN_LIGHT_KEY")
    for key, value in {
        **style.get("ground", {}),
        **{
            k: v
            for k, v in style.get("light", {}).items()
            if k in ("background", "ground")
        },
    }.items():
        if not HEX.fullmatch(str(value)):
            raise ValueError("AREA_STYLE_INVALID_COLOUR: " + key)
    for key, low, high, default in (
        ("window_scale", 0.5, 1.5, 1),
        ("relief_m", 0, 0.8, 0.12),
        ("bay_scale", 0.5, 3, 1),
        ("hour", 0, 24, 13),
        ("tree_detail", 0, 2, 1),
    ):
        value = style.get(key, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not low <= value <= high
        ):
            raise ValueError("AREA_STYLE_NUMBER_OUT_OF_RANGE: " + key)
    for key, high in (("sun", 8), ("sky", 5), ("exposure", 2)):
        value = style.get("light", {}).get(key, 1)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= high
        ):
            raise ValueError("AREA_STYLE_INVALID_LIGHT: " + key)
    if style.get("facade_mode", "texture") not in ("texture", "relief"):
        raise ValueError("AREA_STYLE_INVALID_FACADE_MODE")
    if style.get("projection", "orthographic") not in ("orthographic", "perspective"):
        raise ValueError("AREA_STYLE_INVALID_PROJECTION")
    if not isinstance(style.get("roof_detail", True), bool) or not isinstance(
        style.get("tree_detail", 1), int
    ):
        raise ValueError("AREA_STYLE_INVALID_DETAIL")
    if style.get("glow") is not None and not HEX.fullmatch(str(style["glow"])):
        raise ValueError("AREA_STYLE_INVALID_GLOW")
    if (
        not isinstance(style.get("name", "custom"), str)
        or not style.get("name", "custom").strip()
    ):
        raise ValueError("AREA_STYLE_INVALID_NAME")
    return style


def resolve(style):
    """A preset name or a style dict (optionally extending a preset via ``name``)."""
    if isinstance(style, str):
        if style not in STYLES:
            raise ValueError("AREA_STYLE_UNKNOWN_PRESET: " + style)
        style = {"name": style}
    if not isinstance(style, dict):
        raise ValueError("AREA_STYLE_INVALID_PROFILE")
    name = style.get("name", "custom")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("AREA_STYLE_INVALID_NAME")
    base = copy.deepcopy(STYLES.get(name, STYLES["faithful"]))
    base.update(
        {
            "facade_mode": "relief" if name == "illustrated" else "texture",
            "relief_m": 0.18 if name == "illustrated" else 0.08,
            "bay_scale": 1.4 if name == "clay" else 1,
            "roof_detail": name != "clay",
            "tree_detail": 0 if name == "clay" else 1,
            "projection": "orthographic",
            "name": name,
        }
    )
    for key, value in style.items():
        base[key] = (
            {**base.get(key, {}), **value}
            if key in ("colour", "glass", "light", "ground") and isinstance(value, dict)
            else copy.deepcopy(value)
        )
    return validate(base)


def facade(observed, storey_m, style):
    """Window proportions and rhythm from how much glazing was seen and how it is arranged."""
    fraction = observed.get("glass_fraction")
    rhythm = observed.get("rhythm", "grid")
    glazing = 0.38 if fraction is None else min(0.82, max(0.18, fraction))
    glazing = min(0.86, glazing * style.get("window_scale", 1.0))
    if rhythm == "bands":  # ribbon glazing: wide panes, floor line visible
        w, h = 0.94, min(0.84, glazing / 0.94)
        bay, mullions, course = 2.0, [1, 1], True
    elif rhythm == "fins":  # vertical piers: tall narrow panes
        h = 0.86
        w, bay, mullions, course = min(0.8, glazing / h), 1.8, [1, 2], False
    else:
        side = glazing**0.5
        w, h, bay, mullions, course = (
            min(0.86, side * 1.05),
            min(0.84, side * 0.95),
            3.0,
            [2, 1],
            glazing < 0.45,
        )
    return {
        "bay": bay * style.get("bay_scale", 1),
        "w": round(w, 2),
        "h": round(h, 2),
        "sill": round(max(0.06, (1 - h) / 2), 2),
        "mullions": mullions,
        "course": course,
        "glassy": glazing >= 0.55,
        "rhythm": rhythm,
        "glazing": round(glazing, 2),
        "storey_m": storey_m,
    }


def apply(area, style):
    """Replace class-palette appearance with observed facts rendered in ``style``."""
    style = resolve(style)
    rule, glass_rule = style["colour"], style["glass"]
    overrides = style.get("ground", {})
    walls = [
        b["observed"]["wall_rgb"]
        for b in area["buildings"]
        if b.get("observed", {}).get("wall_rgb")
    ]
    fallback_wall = (
        [int(sum(c[i] for c in walls) / len(walls)) for i in range(3)]
        if walls
        else [150, 152, 156]
    )
    for building in area["buildings"]:
        observed = building.get("observed", {})
        seen = bool(observed.get("wall_rgb"))
        wall = observed.get("wall_rgb") or fallback_wall
        glass = observed.get("glass_rgb") or [int(c * 0.55) for c in wall]
        roof = observed.get("roof_rgb") or [int(c * 0.9) for c in wall]
        storey = building["height_m"] / max(1, building["storeys"])
        appearance = building["appearance"]
        wall_hex = render(wall, rule)
        appearance.update(
            {
                "wall": wall_hex,
                "glass": render(glass, glass_rule),
                "roof": render(roof, rule),
                "trim": lighten(wall_hex, 0.35),
                "frame": lighten(wall_hex, 0.22),
                "plant": render([int(c * 0.85 + 30) for c in roof], rule),
                "facade": facade(observed, storey, style),
                "glow": style.get("glow"),
                "basis": (
                    "observed two-tone facade, glazing share and rhythm"
                    if seen
                    else "walls not seen in any view: area average tone"
                )
                + f"; style {style['name']}",
            }
        )
        if appearance["class"] not in ("canopy", "raised"):
            building["recipe_family"] = "observed"
    for tree in area.get("detected_trees", []):
        if "colour" in tree:
            tree["render_colour"] = overrides.get("leaf") or render(
                tree["colour"], rule
            )
    ground = area.get("observed_ground", {})
    palette = dict(area["palette"])
    for key in ("road", "sidewalk", "rail_bed", "green", "water", "plaza"):
        if key in overrides:
            palette[key] = overrides[key]
        elif ground.get(key):
            # Capture skylight tints shadowed paving blue. Avoid amplifying that cast
            # into a saturated road; explicit user ground overrides still take priority.
            ground_rule = (
                {**rule, "saturation": min(rule.get("saturation", 1), 0.35)}
                if key in ("road", "sidewalk", "rail_bed", "plaza")
                else rule
            )
            palette[key] = render(ground[key], ground_rule)
    leaf = overrides.get("leaf") or (
        render(ground["leaf"], rule) if ground.get("leaf") else None
    )
    if leaf:
        palette["leaf"] = [
            leaf,
            lighten(leaf, 0.12),
            render(from_hex(leaf), {"value_gain": 0.88}),
        ]
    palette["marking"] = lighten(palette["road"], 0.75)
    palette["background"] = style["light"]["background"]
    palette["ground"] = style["light"]["ground"]
    area["palette"] = palette
    area["style"] = style
    return area
