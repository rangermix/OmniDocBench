"""Download the public, pinned benchmark inputs and local inference models."""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('.agent/local-data'))
    parser.add_argument('--dataset', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    os.environ['HF_HOME'] = str(root / 'hf-cache')
    from huggingface_hub import HfApi, snapshot_download
    from docling.datamodel.pipeline_options import LayoutObjectDetectionOptions
    from docling.models.stages.ocr.easyocr_model import EasyOcrModel
    if args.dataset:
        snapshot_download('opendatalab/OmniDocBench', repo_type='dataset',
            revision='aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec',
            allow_patterns=['OmniDocBench.json', 'images/*'],
            local_dir=root / 'dataset', token=False, max_workers=8)
    models = root / 'models'
    models.mkdir(parents=True, exist_ok=True)
    layout = LayoutObjectDetectionOptions().model_spec
    requests = [
        (layout.repo_id, layout.revision),
        ('docling-project/docling-models', 'v2.3.0'),
        ('docling-project/CodeFormulaV2', 'main'),
        ('ibm-granite/granite-docling-258M', '982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe'),
        ('PaddlePaddle/PaddleOCR-VL-1.6', 'c5630abae1d940eafe0697512a0325494b02ab42'),
    ]
    lock_path = root / 'models.lock.json'
    bundled_lock = Path(__file__).with_name('models.lock.json')
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
    elif bundled_lock.exists():
        lock = json.loads(bundled_lock.read_text())
        lock_path.write_text(json.dumps(lock, indent=2), encoding='utf-8')
    else:
        api = HfApi(token=False)
        lock = {'models': [{'repo_id': repo, 'revision': api.model_info(repo, revision=rev).sha}
                           for repo, rev in requests]}
        lock_path.write_text(json.dumps(lock, indent=2), encoding='utf-8')
    for spec in lock['models']:
        print('Downloading', spec, flush=True)
        snapshot_download(**spec, local_dir=models / spec['repo_id'].replace('/', '--'),
                          token=False, max_workers=4)
    EasyOcrModel.download_models(local_dir=models / 'EasyOcr',
                                recognition_models=['zh_sim_g2'], progress=False)
    hashes = {}
    for path in sorted(models.rglob('*')):
        if path.is_file() and '.cache' not in path.parts:
            hashes[str(path.relative_to(models)).replace('\\', '/')] = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    if lock.get('sha256') and hashes != lock['sha256']:
        raise RuntimeError('Downloaded model files do not match the pinned file hashes')
    lock['sha256'] = hashes
    lock_path.write_text(json.dumps(lock, indent=2), encoding='utf-8')
    print('MODEL_PREPARATION_COMPLETE', len(hashes), flush=True)

if __name__ == '__main__':
    main()
