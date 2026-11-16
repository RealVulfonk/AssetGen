"""Map an asset category to its output group under ``out/``.

Kept dependency-free so the CLI, the Blender test scripts and plain system
Python can all import it without pulling in argparse or a Blender runtime.
"""

GROUPS = ("interiors", "exteriors", "environment")

# Порядок важен: проверяется первый подходящий префикс.
_GROUP_RULES = (
    ("flora/understory", "environment"),
    ("flora/trees", "exteriors"),
    ("crypt", "exteriors"),
    ("structure", "exteriors"),
    ("architecture", "interiors"),
    ("doors", "interiors"),
    ("furniture", "interiors"),
    ("props", "interiors"),
    ("remains", "interiors"),
)

DEFAULT_GROUP = "interiors"


def asset_group(category):
    """Output group for a spec category; unknown categories fall back to props."""
    if not category:
        return DEFAULT_GROUP
    for prefix, group in _GROUP_RULES:
        if category == prefix or category.startswith(prefix + "/"):
            return group
    return DEFAULT_GROUP


def output_dir(out_root, name, category):
    """``out/<group>/<name>`` for the given asset."""
    return out_root / asset_group(category) / name
