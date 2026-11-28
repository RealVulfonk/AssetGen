#!/usr/bin/env python3
"""Create a review-only seam candidate from an existing split PBR set."""
import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from split_pbr_sheet import NAME, PANELS, publication_lock


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edge_metric(image):
    w, h = image.size
    def mean(a, b):
        return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3
    return {'horizontal': mean(image.crop((0, 0, 1, h)), image.crop((w-1, 0, w, h))),
            'vertical': mean(image.crop((0, 0, w, 1)), image.crop((0, h-1, w, h)))}


def repeat(image, path):
    w, h = image.size
    canvas = Image.new('RGB', (w * 2, h * 2))
    for x in (0, w):
        for y in (0, h):
            canvas.paste(image, (x, y))
    canvas.save(path)


def normal_diagnostics(image):
    minimum, maximum, near_zero, non_unit, negative_z = float('inf'), 0.0, 0, 0, 0
    pixels = image.tobytes()
    for index in range(0, len(pixels), 3):
        r, g, b = pixels[index:index + 3]
        length = math.sqrt(sum((v / 127.5 - 1) ** 2 for v in (r, g, b)))
        minimum, maximum = min(minimum, length), max(maximum, length)
        near_zero += length < 0.02
        non_unit += abs(length - 1) > 0.03
        negative_z += b < 128
    return {'min_length': minimum, 'max_length': maximum, 'near_zero_pixels': near_zero,
            'non_unit_pixels': non_unit, 'negative_z_pixels': negative_z}


def process(image, kind, band):
    image = image.copy()
    pix = image.load()
    w, h = image.size
    def blend(a, b, weight):
        if kind == 'normal':
            av = [v / 127.5 - 1 for v in a]
            bv = [v / 127.5 - 1 for v in b]
            v = [(1-weight)*x + weight*y for x, y in zip(av, bv)]
            length = math.sqrt(sum(x*x for x in v))
            if length < 0.02:
                raise ValueError('opposed or zero normal vectors in seam')
            return tuple(max(0, min(255, round((x/length+1)*127.5))) for x in v)
        return tuple(round((1-weight)*x + weight*y) for x, y in zip(a, b))
    # Pair opposite edges symmetrically. Sequential axes share the same mask for all maps.
    for axis in (0, 1):
        span, other = (w, h) if axis == 0 else (h, w)
        for i in range(band):
            weight = 0.5 * (1 - i / band) ** 2
            for j in range(other):
                a = (i, j) if axis == 0 else (j, i)
                b = (span-1-i, j) if axis == 0 else (j, span-1-i)
                va, vb = pix[a], pix[b]
                pix[a], pix[b] = blend(va, vb, weight), blend(vb, va, weight)
    return image


def run(source, output, name, band):
    if not NAME.fullmatch(name):
        raise ValueError('name must be safe snake_case')
    if not output.is_dir():
        raise ValueError('output directory must exist')
    paths = {k: source / f'{name}_{k}.png' for k in PANELS}
    images = {}
    for kind, path in paths.items():
        with Image.open(path) as im:
            im.load()
            images[kind] = im.convert('RGB')
    size = images['base_color'].size
    if any(im.size != size for im in images.values()):
        raise ValueError('map dimensions differ')
    if band < 1 or band * 2 > min(size):
        raise ValueError('band must fit within half of each dimension')
    normal_before = normal_diagnostics(images['normal'])
    if normal_before['near_zero_pixels']:
        raise ValueError('normal map contains near-zero vectors')
    # The material samples the green channel; remove chroma from the candidate.
    destination = output / f'{name}_seam_candidate'
    with publication_lock(output, f'{name}_seam'):
        if destination.exists():
            raise ValueError(f'refusing to overwrite candidate: {destination}')
        with tempfile.TemporaryDirectory(prefix='.seam-', dir=output) as temp:
            stage = Path(temp) / 'candidate'
            stage.mkdir()
            report = {'status': 'needs_review', 'reason': 'visual and Godot A/B acceptance required; blending may damage structure',
                      'size': list(size), 'band_px': band, 'offset_px': [0, 0],
                      'roughness_conversion': 'green channel replicated to RGB across whole map', 'maps': {}}
            for kind in PANELS:
                before = images[kind]
                data = before.getchannel('G').convert('RGB') if kind == 'roughness' else before
                after = process(data, kind, band)
                target = stage / f'{name}_{kind}.png'
                after.save(target)
                repeat(before, stage / f'{kind}_before_repeat.png')
                repeat(after, stage / f'{kind}_after_repeat.png')
                report['maps'][kind] = {'source_sha256': digest(paths[kind]), 'candidate_sha256': digest(target),
                                        'before_edge_mae': edge_metric(before), 'after_edge_mae': edge_metric(after)}
                if kind == 'normal':
                    report['maps'][kind]['before_vectors'] = normal_before
                    report['maps'][kind]['after_vectors'] = normal_diagnostics(after)
            (stage / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            os.rename(stage, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='directory containing original split PNGs')
    parser.add_argument('--out', type=Path, required=True, help='existing directory for candidate')
    parser.add_argument('--name', required=True)
    parser.add_argument('--band', type=int, default=24, help='edge mask width in pixels')
    args = parser.parse_args()
    try:
        print(run(args.source, args.out, args.name, args.band))
    except (OSError, ValueError) as error:
        parser.exit(1, f'ERROR: {error}\n')


if __name__ == '__main__':
    main()

