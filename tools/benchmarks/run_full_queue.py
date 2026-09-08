"""Durable, sequential local inference -> official scoring -> comparison queue."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ARMS = ('docling_enriched', 'docling_granite', 'docling_paddle16')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--published',type=Path,required=True)
    args=p.parse_args()
    run, root, manifest, published = [x.resolve() for x in
        [args.run,args.root,args.manifest,args.published]]
    frozen=run/'frozen'
    if not (frozen/'docling_compare.py').is_file():
        raise RuntimeError('Freeze the reviewed scripts before launching the queue')
    status={'controller_pid':os.getpid(),'status':'running','started_at':datetime.now(timezone.utc).isoformat()}
    # Inhibit system sleep only while this queue is alive; do not change the
    # power plan or keep the display on. The OS also clears this on process exit.
    if os.name=='nt':
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    def save_status(**updates):
        status.update(updates)
        status['updated_at']=datetime.now(timezone.utc).isoformat()
        status['coverage']={arm:len(list((run/arm/'records').glob('*.json'))) for arm in ARMS}
        temporary=run/'status.json.partial'
        temporary.write_text(json.dumps(status,indent=2),encoding='utf-8')
        temporary.replace(run/'status.json')
    def execute(command, step):
        log=run/(step+'.controller.log')
        with log.open('a',encoding='utf-8') as stream:
            child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
            save_status(step=step,child_pid=child.pid,command=command,log=str(log))
            while child.poll() is None:
                save_status()
                time.sleep(30)
            save_status(last_exit_code=child.returncode)
            if child.returncode:
                raise RuntimeError(f'{step} exited {child.returncode}; inspect {log}')
    def summarize():
        subprocess.run([sys.executable,str(frozen/'summarize_docling.py'),'--run',str(run),
                        '--manifest',str(manifest),'--published',str(published)],check=True)
    try:
        save_status()
        summarize()
        for arm in ARMS:
            execute([sys.executable,str(frozen/'docling_compare.py'),'--arm',arm,
                     '--root',str(root),'--manifest',str(manifest),'--out',str(run/arm)],'infer-'+arm)
            summarize()
            eval_dir=run/'evaluation'/arm
            if eval_dir.exists():
                summary=json.loads((run/'comparison.json').read_text())
                prior=next(x for x in summary['measured'] if x['arm']==arm)
                if not prior['evaluation_valid']:
                    raise RuntimeError(f'Existing incomplete/invalid evaluation at {eval_dir}; preserve and review it')
            else:
                execute(['powershell','-NoProfile','-File',str(frozen/'evaluate_docling.ps1'),
                    '-GroundTruth',str(root/'dataset'/'OmniDocBench.json'),
                    '-PredictionDir',str(run/arm/'markdown'),'-OutputDir',str(eval_dir),
                    '-SourceRoot',str(frozen/'evaluator')],'eval-'+arm)
            summarize()
        summary=json.loads((run/'comparison.json').read_text())
        if summary['status']!='complete':
            raise RuntimeError('All commands ended, but metric validity checks did not pass')
        save_status(status='complete',step='complete',report=str(run/'REPORT.md'),child_pid=None)
    except Exception:
        save_status(status='needs_attention',error=traceback.format_exc())
        try: summarize()
        except Exception: pass
        raise
    finally:
        if os.name=='nt':
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

if __name__=='__main__': main()
