"""Start both local servers. All model and runtime paths stay inside the project folder."""
from pathlib import Path
import sys, subprocess, time, urllib.request, atexit, json
sys.path.insert(0,str(Path(__file__).resolve().parent))
from settings import ROOT,RUNTIME,SUBMISSION,MODELS

def ready(url):
    try:
        with urllib.request.urlopen(url,timeout=2) as r:return r.status==200
    except Exception:return False

if ready('http://127.0.0.1:8765/api/health'):
    print('The project is already running at http://127.0.0.1:8765',flush=True);sys.exit(0)
model=next(MODELS.glob('*.gguf'))
server=next((RUNTIME/'llama').rglob('llama-server.exe'))
proc=None
if not ready('http://127.0.0.1:8081/health'):
    log=(RUNTIME/'logs'/'llama-server.log').open('w',encoding='utf-8')
    proc=subprocess.Popen([str(server),'-m',str(model),'--host','127.0.0.1','--port','8081','-c','4096','-t','4','--parallel','1'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    def stop_model():
        if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=20)
    atexit.register(stop_model)
    print('Loading the local Qwen model...',flush=True)
    for _ in range(90):
        if ready('http://127.0.0.1:8081/health'):break
        if proc.poll() is not None:raise RuntimeError('Local model stopped. See runtime/logs/llama-server.log')
        time.sleep(1)
    else:raise RuntimeError('Local model did not become ready in 90 seconds.')
print('Loading local embeddings and project documents...',flush=True)
from app import app,store
for version in ['1.0','2.0']:
    store.ingest(SUBMISSION/'Input_Data'/f'BodyComfort_HLD_v{version}.pdf','body-comfort',version,'bootstrap')
print('READY: http://127.0.0.1:8765',flush=True)
print('Student login: student / student-demo',flush=True)
print('Reviewer login: reviewer / reviewer-demo',flush=True)
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=8765,log_level='info')
