"""Create inference-only manifests and a fixed smoke GT without leaking annotations."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('.agent/local-data/dataset'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    gt_path = args.data / 'OmniDocBench.json'
    gt = json.loads(gt_path.read_text(encoding='utf-8'))
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for page in gt:
        name = Path(page['page_info']['image_path']).name
        path = args.data / 'images' / name
        manifest.append({'image': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if len({p['image'] for p in manifest}) != len(manifest):
        raise ValueError('Duplicate image names')
    # Deliberately cover English, Chinese, formulas, tables, and code for smoke testing.
    selected = []
    for category in ['code_txt', 'table', 'equation_isolated']:
        for language in ['english', 'simplified_chinese']:
            for i, page in enumerate(gt):
                attr = page['page_info']['page_attribute']
                if (i not in selected and attr.get('language') == language and
                    any(x['category_type'] == category for x in page['layout_dets'])):
                    selected.append(i)
                    break
    if len(selected) < 3:
        raise ValueError('Cannot build meaningful smoke sample')
    outputs = {'manifest.json': manifest,
               'smoke-manifest.json': [manifest[i] for i in selected],
               'smoke-gt.json': [gt[i] for i in selected],
               'dataset-summary.json': {
                    'dataset_revision': 'aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec',
                    'gt_sha256': hashlib.sha256(gt_path.read_bytes()).hexdigest(),
                    'pages': len(gt), 'smoke_indices': selected,
                    'language': dict(Counter(p['page_info']['page_attribute'].get('language') for p in gt)),
                    'source': dict(Counter(p['page_info']['page_attribute'].get('data_source') for p in gt))}}
    for name, data in outputs.items():
        (args.out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(outputs['dataset-summary.json'], ensure_ascii=False))

if __name__ == '__main__':
    main()
