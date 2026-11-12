"""Synthetic capability fixture; never presented as reconstruction of Tokyo."""

from .ir import World


def demo_world():
    materials = [
        {"id": "stone", "color": "#b7afa1", "roughness": 0.88},
        {"id": "roof", "color": "#555c60", "roughness": 0.78},
        {"id": "frame", "color": "#d7cebc", "roughness": 0.7},
        {
            "id": "glass",
            "color": "#36494c",
            "roughness": 0.27,
            "metalness": 0.15,
            "emission": "#f7bd71",
            "emissive_at_night": True,
        },
        {"id": "tree", "color": "#566c39", "roughness": 0.93},
        {"id": "metal", "color": "#4b5356", "metalness": 0.7, "roughness": 0.43},
        {"id": "asphalt", "color": "#67696a", "roughness": 0.95},
        {"id": "paint", "color": "#d1cabb", "roughness": 0.9},
    ]

    def part(id, kind, size, pos, material, **kw):
        return {
            "id": id,
            "kind": kind,
            "size": size,
            "position": pos,
            "material": material,
            **kw,
        }

    parts = [
        part("hall", "box", [18, 7, 10], [0, 3.5, 0], "stone"),
        part("roof", "gable_roof", [19, 3, 11], [0, 8.45, 0], "roof"),
        part("plinth", "box", [18.4, 0.5, 10.4], [0, 0.25, 0], "frame"),
    ]
    for side in [-1, 1]:
        for floor in [2.1, 5.1]:
            for column in range(9):
                x = -8 + column * 2
                prefix = f"w-{side}-{floor}-{column}"
                parts.extend(
                    [
                        part(
                            prefix + "-glass",
                            "box",
                            [1.1, 1.8, 0.06],
                            [x, floor, side * 5.035],
                            "glass",
                        ),
                        part(
                            prefix + "-frame",
                            "window_frame",
                            [1.32, 2.02, 0.14],
                            [x, floor, side * 5.09],
                            "frame",
                            wall_thickness=0.09,
                        ),
                    ]
                )
        parts.append(
            part(
                "cornice-" + str(side),
                "box",
                [18.8, 0.22, 0.3],
                [0, 6.8, side * 5.1],
                "frame",
            )
        )
    # Separate ventilation test piece: no roof/body is silently left blocking its air channel.
    parts.append(
        part(
            "flue-test",
            "hollow_shaft",
            [1.4, 4, 1.4],
            [12, 2.5, -2],
            "stone",
            wall_thickness=0.22,
            semantic_requirements=["air_path"],
        )
    )
    for z in [-8, 8]:
        parts.append(
            part("walkway" + str(z), "box", [30, 0.16, 2], [0, 0.08, z], "frame")
        )
        for x in [-13, -6, 6, 13]:
            parts.append(
                part(
                    f"tree-{x}-{z}",
                    "tree",
                    [3.8, 6, 3.8],
                    [x, 3, z],
                    "tree",
                    allow_shape_variation=True,
                )
            )
        for x in [-10, 0, 10]:
            parts.append(
                part(f"lamp-{x}-{z}", "lamp", [0.9, 5, 0.35], [x, 2.5, z], "metal")
            )
    parts.append(part("road", "road_strip", [34, 0.12, 6], [0, -0.03, 13], "asphalt"))
    for i in range(15):
        parts.append(
            part(
                "lane-" + str(i),
                "box",
                [1.2, 0.015, 0.11],
                [-16 + i * 2.25, 0.045, 13],
                "paint",
            )
        )
    world = {
        "blueprints": [
            {
                "id": "capability-fixture",
                "tier": "kit",
                "components": parts,
                "materials": materials,
            }
        ],
        "instances": [
            {"id": "fixture", "blueprint": "capability-fixture", "anchor": [0, 0, 0]}
        ],
    }
    return World.model_validate(world).model_dump()
