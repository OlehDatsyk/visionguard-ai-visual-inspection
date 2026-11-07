"""Inspection categories: which implemented checks run, and which checks the system cannot do."""

UNSUPPORTED = {
    "dents": "Dents are depth changes. A single 2D photo does not measure depth, and no dent model is installed.",
    "missing_components": (
        "Detecting a missing part needs a reference of the complete item. Use Image Comparison against a "
        "known-good image; differences it reports still need human interpretation."
    ),
    "structural_integrity": "Structural safety cannot be judged from surface appearance. Consult a qualified engineer.",
    "internal_damage": "Only visible surfaces are analysed. Internal or hidden damage cannot be assessed.",
    "mechanical_function": "Whether machinery operates correctly cannot be determined from a still image.",
    "shape_irregularity": (
        "No trained model for shape irregularities is installed. Large irregular regions may appear as "
        "surface anomalies, but shape conformity is not measured."
    ),
    "functional_defects": "Whether a product works or meets its specification cannot be determined from an image.",
}

ALL_MODULES = ("linear", "surface_anomaly", "discolouration", "corrosion")

CATEGORIES: dict[str, dict] = {
    "manufacturing_qc": {
        "label": "Manufacturing quality control",
        "modules": ("linear", "surface_anomaly", "discolouration"),
        "unsupported": ("dents", "missing_components", "shape_irregularity", "functional_defects"),
    },
    "product_component": {
        "label": "Product and component inspection",
        "modules": ("linear", "surface_anomaly", "discolouration"),
        "unsupported": ("missing_components", "shape_irregularity", "functional_defects"),
    },
    "building_property": {
        "label": "Building and property inspection",
        "modules": ("linear", "discolouration", "corrosion"),
        "unsupported": ("structural_integrity", "internal_damage"),
    },
    "equipment_machinery": {
        "label": "Equipment and machinery inspection",
        "modules": ALL_MODULES,
        "unsupported": ("mechanical_function", "internal_damage", "missing_components"),
    },
    "vehicle_damage": {
        "label": "Vehicle damage assessment",
        "modules": ("linear", "discolouration", "corrosion"),
        "unsupported": ("dents", "structural_integrity", "mechanical_function"),
    },
    "surface_material": {
        "label": "Surface and material defects",
        "modules": ALL_MODULES,
        "unsupported": ("dents", "internal_damage"),
    },
    "object_recognition": {
        "label": "General object recognition",
        "modules": (),
        "unsupported": (),
    },
}

MODULE_INFO = {
    "linear": {
        "name": "Linear feature analysis",
        "reports": ["crack_like", "scratch_like"],
        "technique": "Morphological top-hat and black-hat filters, connected components, shape measures",
    },
    "surface_anomaly": {
        "name": "Local surface anomaly scoring",
        "reports": ["surface_anomaly"],
        "technique": "Background-subtracted intensity and local texture, scored by robust z-score (median and MAD)",
    },
    "discolouration": {
        "name": "Colour deviation analysis",
        "reports": ["discolouration"],
        "technique": "CIE LAB distance from the image's robust median colour",
    },
    "corrosion": {
        "name": "Corrosion-like pattern heuristic",
        "reports": ["corrosion_like"],
        "technique": "HSV rust-colour range combined with local texture",
    },
}


def unsupported_for(category: str) -> list[dict]:
    return [{"check": key, "reason": UNSUPPORTED[key]} for key in CATEGORIES[category]["unsupported"]]
