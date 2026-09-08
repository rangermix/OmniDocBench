"""Local Docling / Granite / Paddle region benchmark. No GT content enters inference.

Infer from a filename-only manifest prepared separately from ground truth. Each
page gets an atomic prediction and record; failures remain in the denominator.
"""
import argparse
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import random
import time
import traceback

ARMS = ('docling_enriched', 'docling_granite', 'docling_paddle16')

def paddle_table_html(text):
    if '<fcel>' not in text and '<ecel>' not in text:
        return text
    if __package__:
        from .paddle_otsl import convert_otsl_to_html
    else:
        from paddle_otsl import convert_otsl_to_html
    return convert_otsl_to_html(text)

def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)

def configure_environment(root):
    os.environ['HF_HOME'] = str(root / 'hf-cache')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'

def make_converter(arm, models):
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (PdfPipelineOptions, VlmPipelineOptions,
        EasyOcrOptions, TableFormerMode, CodeFormulaVlmOptions, VlmConvertOptions)
    from docling.datamodel.vlm_engine_options import TransformersVlmEngineOptions
    from docling.document_converter import DocumentConverter, ImageFormatOption
    from docling.pipeline.vlm_pipeline import VlmPipeline
    device = AcceleratorOptions(device=AcceleratorDevice.CUDA, num_threads=8)
    engine = TransformersVlmEngineOptions(device=AcceleratorDevice.CUDA,
        load_in_8bit=False, torch_dtype='bfloat16', compile_model=False)
    lock_path = models.parent / 'models.lock.json'
    revisions = {x['repo_id']: x['revision'] for x in
                 json.loads(lock_path.read_text())['models']} if lock_path.exists() else {}
    if arm == 'docling_granite':
        vlm = VlmConvertOptions.from_preset('granite_docling', engine_options=engine)
        vlm.model_spec.revision = revisions.get(vlm.model_spec.default_repo_id, vlm.model_spec.revision)
        options = VlmPipelineOptions(artifacts_path=models, accelerator_options=device,
            vlm_options=vlm, document_timeout=600)
        format_option = ImageFormatOption(pipeline_cls=VlmPipeline, pipeline_options=options)
    else:
        options = PdfPipelineOptions(artifacts_path=models, accelerator_options=device,
            do_ocr=True, do_table_structure=arm == 'docling_enriched',
            do_code_enrichment=arm == 'docling_enriched',
            do_formula_enrichment=arm == 'docling_enriched',
            do_picture_description=False, do_picture_classification=False,
            generate_page_images=True, images_scale=1.0, document_timeout=600,
            ocr_options=EasyOcrOptions(lang=['ch_sim', 'en'], force_full_page_ocr=True,
                                     download_enabled=False))
        options.table_structure_options.mode = TableFormerMode.ACCURATE
        options.code_formula_options = CodeFormulaVlmOptions.from_preset('codeformulav2', engine_options=engine)
        spec = options.code_formula_options.model_spec
        spec.revision = revisions.get(spec.default_repo_id, spec.revision)
        if arm == 'docling_paddle16':
            options.layout_options.keep_empty_clusters = True
        format_option = ImageFormatOption(pipeline_options=options)
    return DocumentConverter(allowed_formats=[InputFormat.IMAGE],
        format_options={InputFormat.IMAGE: format_option}), options.model_dump(mode='json')

def export_markdown(doc, table_outputs=None):
    """Keep HTML row/col spans for TEDS in every arm, preserve Docling ordering."""
    from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownTableSerializer
    from docling_core.transforms.serializer.common import create_ser_result
    from docling_core.transforms.serializer.markdown import MarkdownParams
    from docling_core.types.doc import ImageRefMode
    class HtmlTables(MarkdownTableSerializer):
        def serialize(self, *, item, doc_serializer, doc, **kwargs):
            caption = doc_serializer.serialize_captions(item=item, **kwargs).text
            body = (table_outputs or {}).get(item.self_ref)
            if body is None:
                body = item.export_to_html(doc=doc, add_caption=False)
            return create_ser_result(text='\n\n'.join(x for x in [caption, body] if x), span_source=item)
    return MarkdownDocSerializer(doc=doc, table_serializer=HtmlTables(),
        params=MarkdownParams(image_mode=ImageRefMode.PLACEHOLDER,
                              escape_underscores=False, escape_html=False)).serialize().text

class PaddleRegions:
    def __init__(self, models):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
        self.torch = torch
        path = models / 'PaddlePaddle--PaddleOCR-VL-1.6'
        self.processor = AutoProcessor.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForImageTextToText.from_pretrained(path, dtype=torch.bfloat16,
            attn_implementation='sdpa', local_files_only=True).to('cuda').eval()
        self.processor.tokenizer.padding_side = 'left'

    def __call__(self, doc):
        from docling_core.types.doc import TextItem, TableItem, DocItemLabel
        candidates, tables, evidence = [], {}, []
        for item, _ in doc.iterate_items():
            if not isinstance(item, (TextItem, TableItem)):
                continue
            crop = item.get_image(doc)
            if crop is None or min(crop.size) <= 0:
                raise RuntimeError(f'Missing region image: {item.self_ref}')
            task = ('table' if isinstance(item, TableItem) else
                    'formula' if item.label == DocItemLabel.FORMULA else 'ocr')
            candidates.append((item, crop.convert('RGB'), task))
        prompts = {'ocr': 'OCR:', 'table': 'Table Recognition:', 'formula': 'Formula Recognition:'}
        # A common, finite generation cap; truncations are explicitly recorded.
        for start in range(0, len(candidates), 4):
            batch = candidates[start:start + 4]
            chats = [[{'role': 'user', 'content': [
                {'type': 'image', 'image': crop}, {'type': 'text', 'text': prompts[task]}]}]
                for _, crop, task in batch]
            inputs = self.processor.apply_chat_template(chats, add_generation_prompt=True,
                tokenize=True, return_dict=True, return_tensors='pt', padding=True).to(self.model.device)
            with self.torch.inference_mode():
                outputs = self.model.generate(**inputs, max_new_tokens=4096, do_sample=False)
            generated = outputs[:, inputs['input_ids'].shape[1]:]
            texts = self.processor.batch_decode(generated, skip_special_tokens=True)
            for (item, crop, task), tokens, text in zip(batch, generated, texts):
                ids = tokens.tolist()
                eos = self.model.generation_config.eos_token_id
                eos_ids = eos if isinstance(eos, list) else [eos]
                evidence.append({'ref': item.self_ref, 'task': task, 'crop_size': crop.size,
                    'hit_token_limit': len(ids) >= 4096 and not any(x in ids for x in eos_ids), 'text': text})
                if task == 'table':
                    try:
                        tables[item.self_ref] = paddle_table_html(text)
                    except Exception:
                        evidence[-1]['table_format_error'] = traceback.format_exc()
                        tables[item.self_ref] = ''
                else:
                    if task == 'formula':
                        text = text.strip()
                        if text.startswith('$$') and text.endswith('$$'):
                            text = text[2:-2].strip()
                        elif text.startswith('\\[') and text.endswith('\\]'):
                            text = text[2:-2].strip()
                    item.text = text
                    item.orig = text
        return export_markdown(doc, tables), evidence

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=ARMS, required=True)
    parser.add_argument('--root', type=Path, default=Path('.agent/local-data'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    configure_environment(root)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; refusing silent CPU fallback')
    random.seed(42)
    torch.manual_seed(42)
    torch.set_num_threads(8)
    # Observe actual stage inputs and outputs; never alter generation or scores.
    from docling.models.inference_engines.vlm.transformers_engine import TransformersVlmEngine
    original_predict = TransformersVlmEngine.predict_batch
    stage_events = []
    def observed_predict(engine, batch):
        try:
            outputs = original_predict(engine, batch)
        except Exception:
            stage_events.append({'error': traceback.format_exc()})
            raise
        for request, output in zip(batch, outputs):
            count = output.metadata.get('num_tokens')
            stage_events.append({'prompt': request.prompt, 'max_new_tokens': request.max_new_tokens,
                'num_tokens': count, 'stop_reason': output.stop_reason,
                'hit_token_limit': count is not None and count >= request.max_new_tokens,
                'text': output.text})
        return outputs
    TransformersVlmEngine.predict_batch = observed_predict
    pages = json.loads(args.manifest.read_text(encoding='utf-8'))
    if args.limit:
        pages = pages[:args.limit]
    out.mkdir(parents=True, exist_ok=True)
    converter, options = make_converter(args.arm, root / 'models')
    binding = {'arm': args.arm, 'options': options,
        'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'paddle_otsl_sha256': hashlib.sha256(Path(__file__).with_name('paddle_otsl.py').read_bytes()).hexdigest(),
        'model_lock_sha256': hashlib.sha256((root / 'models.lock.json').read_bytes()).hexdigest(),
        'packages': {p: importlib.metadata.version(p) for p in
            ['docling', 'docling-core', 'docling-ibm-models', 'transformers', 'torch', 'torchvision', 'easyocr']},
        'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda}
    binding_file = out / 'binding.json'
    if binding_file.exists() and json.loads(binding_file.read_text()) != binding:
        raise RuntimeError('Run binding changed. Use a new output directory.')
    atomic_text(binding_file, json.dumps(binding, indent=2))
    paddle = PaddleRegions(root / 'models') if args.arm == 'docling_paddle16' else None
    for index, page in enumerate(pages):
        image = root / 'dataset' / 'images' / page['image']
        if hashlib.sha256(image.read_bytes()).hexdigest() != page['sha256']:
            raise RuntimeError(f'Input image changed: {page["image"]}')
        name = Path(page['image']).stem
        prediction = out / 'markdown' / (name + '.md')
        record_path = out / 'records' / (name + '.json')
        if record_path.exists() and prediction.exists():
            record = json.loads(record_path.read_text(encoding='utf-8'))
            if hashlib.sha256(prediction.read_bytes()).hexdigest() == record['prediction_sha256']:
                continue
            raise RuntimeError(f'Prediction/record mismatch: {name}')
        started = time.perf_counter()
        stage_events.clear()
        torch.cuda.reset_peak_memory_stats()
        record = {'image': page['image'], 'index': index, 'status': 'failed'}
        md = ''
        try:
            result = converter.convert(image, raises_on_error=False)
            record['conversion_status'] = str(result.status)
            if result.document is None or str(result.status) not in ['success', 'ConversionStatus.SUCCESS']:
                raise RuntimeError(f'Docling conversion status: {result.status}; {result.errors}')
            if paddle:
                md, regions = paddle(result.document)
                atomic_text(out / 'regions' / (name + '.json'), json.dumps(regions, ensure_ascii=False))
                record['truncated_regions'] = sum(r['hit_token_limit'] for r in regions)
                record['table_format_errors'] = sum('table_format_error' in r for r in regions)
            else:
                md = export_markdown(result.document)
            # Source document JSON retains coordinates and the model's raw content.
            atomic_text(out / 'documents' / (name + '.json'), result.document.model_dump_json())
            record['status'] = 'success' if md.strip() else 'empty'
            if record.get('table_format_errors') and record['status'] == 'success':
                record['status'] = 'partial_table_format_error'
        except Exception:
            record['error'] = traceback.format_exc()
            print(record['error'], flush=True)
        if stage_events:
            atomic_text(out / 'generations' / (name + '.json'), json.dumps(stage_events, ensure_ascii=False))
            record['generation_errors'] = sum('error' in e for e in stage_events)
            record['generation_token_limit_hits'] = sum(e.get('hit_token_limit', False) for e in stage_events)
            if record['generation_errors'] and record['status'] == 'success':
                record['status'] = 'partial_enrichment_error'
        torch.cuda.synchronize()
        record['seconds'] = time.perf_counter() - started
        record['peak_gpu_allocated_bytes'] = torch.cuda.max_memory_allocated()
        record['prediction_sha256'] = hashlib.sha256(md.encode()).hexdigest()
        atomic_text(prediction, md)
        atomic_text(record_path, json.dumps(record, ensure_ascii=False, indent=2))
        print(json.dumps({'arm': args.arm, 'page': index + 1, 'total': len(pages),
            'status': record['status'], 'seconds': round(record['seconds'], 2)}, ensure_ascii=False), flush=True)
        if record['status'] == 'failed' and index < 3:
            raise RuntimeError('Early inference failure; fix before proceeding through the dataset')
    print('INFERENCE_COMPLETE', args.arm, len(pages), flush=True)

if __name__ == '__main__':
    main()
