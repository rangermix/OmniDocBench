"""Produce a transparent partial/final comparison from saved evidence only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

ARMS = ('docling_enriched', 'docling_granite', 'docling_paddle16')

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def at(data, *keys):
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data

def collect(run, expected):
    result = []
    for arm in ARMS:
        records = [read(p) for p in (run / arm / 'records').glob('*.json')]
        records.sort(key=lambda x: x['index'])
        metrics_dir = run / 'evaluation' / arm
        metric_files = list(metrics_dir.glob('*_metric_result.json'))
        entry = {'arm': arm, 'completed_pages': len(records), 'expected_pages': expected,
                 'inference_statuses': dict(Counter(r['status'] for r in records)),
                 'total_inference_seconds': sum(r['seconds'] for r in records),
                 'first_page_seconds': records[0]['seconds'] if records else None,
                 'warm_median_seconds': statistics.median(r['seconds'] for r in records[1:]) if len(records)>1 else None,
                 'warm_mean_seconds': statistics.mean(r['seconds'] for r in records[1:]) if len(records)>1 else None,
                 'token_limit_hits': sum(r.get('generation_token_limit_hits', 0) + r.get('truncated_regions', 0) for r in records),
                 'table_format_errors': sum(r.get('table_format_errors', 0) for r in records),
                 'peak_torch_gpu_allocated_bytes': max((r['peak_gpu_allocated_bytes'] for r in records), default=0),
                 'scores': None, 'evaluation_valid': False}
        if metric_files:
            metric = read(metric_files[0])
            stage_files = list(metrics_dir.glob('*_stage_execution.json'))
            stage = read(stage_files[0]) if stage_files else {}
            text = at(metric, 'text_block','all','Edit_dist','ALL_page_avg')
            cdm = at(metric, 'display_formula','page','CDM','ALL')
            teds = at(metric, 'table','page','TEDS','ALL')
            entry['scores'] = {
                'Overall': ((1-text)+cdm+teds)*100/3 if all(v is not None for v in [text,cdm,teds]) else None,
                'Text_Edit': text,
                'Formula_CDM': cdm*100 if cdm is not None else None,
                'Table_TEDS': teds*100 if teds is not None else None,
                'Table_TEDS_S': (at(metric,'table','page','TEDS_structure_only','ALL') or 0)*100,
                'Reading_Order_Edit': at(metric,'reading_order','all','Edit_dist','ALL_page_avg')}
            entry['evaluation_stage'] = stage
            counters = [at(stage,'metrics',category,name,field)
                        for category,name in [('display_formula','CDM'),('table','TEDS')]
                        for field in ['timeout_case_count','error_case_count','exception_case_count']]
            entry['evaluation_valid'] = (len(records)==expected and
                at(stage,'page_match','page_count')==expected and all(x==0 for x in counters))
        result.append(entry)
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--published',type=Path)
    args=p.parse_args()
    rows=collect(args.run,len(read(args.manifest)))
    complete=all(r['evaluation_valid'] for r in rows)
    payload={'updated_at':datetime.now(timezone.utc).isoformat(),
             'status':'complete' if complete else 'incomplete','measured':rows}
    published=read(args.published) if args.published else None
    if published: payload['published']=published
    (args.run/'comparison.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Docling / Granite / PaddleOCR-VL-1.6 benchmark', '',
           f"Status: **{payload['status']}**. Updated {payload['updated_at']}", '',
           '## Local measurements', '',
           '| Arm | Pages | Overall ↑ | Text Edit ↓ | Formula CDM ↑ | Table TEDS ↑ | Order Edit ↓ | Valid evaluation |',
           '|---|---:|---:|---:|---:|---:|---:|---|']
    def fmt(v): return f'{v:.4f}' if v is not None else 'pending'
    for r in rows:
        s=r['scores'] or {}
        lines.append(f"| {r['arm']} | {r['completed_pages']}/{r['expected_pages']} | "+
                     ' | '.join(fmt(s.get(k)) for k in ['Overall','Text_Edit','Formula_CDM','Table_TEDS','Reading_Order_Edit'])+
                     f" | {r['evaluation_valid']} |")
    lines += ['', '## Performance and coverage', '',
              '| Arm | Total hours | First page seconds | Warm mean seconds | Warm median seconds | Token limit hits | Inference statuses |',
              '|---|---:|---:|---:|---:|---:|---|']
    for r in rows:
        lines.append(f"| {r['arm']} | {r['total_inference_seconds']/3600:.2f} | {fmt(r['first_page_seconds'])} | {fmt(r['warm_mean_seconds'])} | {fmt(r['warm_median_seconds'])} | {r['token_limit_hits']} | {r['inference_statuses']} |")
    lines += ['', 'All 1,651 official page images are retained in the evaluation denominator. Failed predictions remain empty files.',
              'Generation limit hits are retained, not repaired or excluded. Separate standard-pipeline OCR/enrichment switches do not apply to Granite whole-page inference.',
              'The Paddle hybrid uses Docling regions/order and is not the official Paddle pipeline. Ground-truth regions/text never enter inference.',
              'Timings are measured on a shared Windows RTX 4090 host, using local Transformers. First-page Docling loading is included; Paddle model initialization precedes page timing. Torch allocated memory is not total VRAM.',
              'Evaluation validation requires the expected page count and zero CDM/TEDS timeout/error/exception counters. Scores with invalid evaluation remain provisional.', '']
    if published:
        lines += ['## Published reference results (not locally rerun)', '',
                  f"Source: [pinned OmniDocBench v1.6_full leaderboard]({published['source']}). Software, prompts and hardware can differ from this run.", '',
                  '| Method | Overall ↑ | Text Edit ↓ | Formula CDM ↑ | Table TEDS ↑ | Order Edit ↓ |',
                  '|---|---:|---:|---:|---:|---:|']
        for r in published['rows'][1:]:
            if len(r)==9:
                lines.append('| '+' | '.join(r[i] for i in [0,3,4,5,6,8])+' |')
    (args.run/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'status':payload['status'],'coverage':{r['arm']:r['completed_pages'] for r in rows}}))

if __name__=='__main__': main()
