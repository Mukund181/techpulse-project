import hashlib, hmac, json, secrets, uuid
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from core import Store
from settings import CODE, CONFIG, STATE

app=FastAPI(title='TechPulse CS1 HLD Assistant',version='1.0.0')
secret_file=STATE/'session.key'
if not secret_file.exists():secret_file.write_text(secrets.token_hex(32))
app.add_middleware(SessionMiddleware,secret_key=secret_file.read_text(),same_site='strict',max_age=3600)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
store=Store()
# Deliberately public demonstration accounts, for this loopback-only synthetic-data pilot.
ACCOUNTS={'student':{'password':'student-demo','role':'analyst','projects':['body-comfort']},'reviewer':{'password':'reviewer-demo','role':'reviewer','projects':['body-comfort']}}

def user(request,project='body-comfort',reviewer=False):
    name=request.session.get('user');account=ACCOUNTS.get(name)
    if not account:raise HTTPException(401,'Sign in first.')
    if project not in account['projects']:raise HTTPException(403,'No access to this project.')
    if reviewer and account['role']!='reviewer':raise HTTPException(403,'Reviewer role required.')
    return name,account

@app.middleware('http')
async def headers(request,call_next):
    origin=request.headers.get('origin')
    if request.method in ['POST','PUT','DELETE'] and origin and origin not in ['http://127.0.0.1:8765','http://localhost:8765']:
        return JSONResponse({'detail':'Cross-origin writes are not allowed.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)

@app.get('/',response_class=HTMLResponse)
def home():return (CODE/'index.html').read_text(encoding='utf-8')

@app.get('/api/health')
def health():return {'status':'ok','case_study':'CS1','model':CONFIG['model'],'embedding':CONFIG['embedding']}

@app.post('/api/login')
async def login(request:Request):
    data=await request.json();name=data.get('username','');account=ACCOUNTS.get(name)
    if not account or not hmac.compare_digest(str(data.get('password','')),account['password']):raise HTTPException(401,'Incorrect demonstration credentials.')
    request.session.clear();request.session['user']=name;store.audit(name,'login',{'role':account['role']})
    return {'user':name,'role':account['role']}

@app.post('/api/logout')
def logout(request:Request):request.session.clear();return {'status':'signed out'}

@app.get('/api/session')
def session(request:Request):
    name,account=user(request);return {'user':name,'role':account['role'],'project':'body-comfort'}

@app.get('/api/documents')
def documents(request:Request,project:str='body-comfort'):
    user(request,project);return store.documents(project)

@app.post('/api/ingest')
def ingest(request:Request,file:UploadFile=File(...),version:str=Form(...),project:str=Form('body-comfort')):
    name,_=user(request,project)
    filename=Path(file.filename or '').name
    if Path(filename).suffix.lower() not in ['.pdf','.docx','.txt','.md']:raise HTTPException(400,'Unsupported file type.')
    content=file.file.read(CONFIG['max_upload_bytes']+1)
    if len(content)>CONFIG['max_upload_bytes']:raise HTTPException(400,'File exceeds 5 MB.')
    folder=STATE/'uploads'/uuid.uuid4().hex;folder.mkdir(parents=True)
    path=folder/filename;path.write_bytes(content)
    return store.ingest(path,project,version,name)

@app.post('/api/ask')
async def ask(request:Request):
    data=await request.json();project=data.get('project','body-comfort');name,_=user(request,project)
    if not isinstance(data.get('question'),str):raise ValueError('Question must be text.')
    # This pilot serves one generation at a time. The inference server is local.
    import asyncio
    return await asyncio.to_thread(store.ask,data['question'],project,data.get('version','2.0'),name)

@app.get('/api/inventory')
def inventory(request:Request,version:str='2.0',project:str='body-comfort'):
    user(request,project);return {'entities':store.inventory(project,version),'findings':store.findings(project,version)}

@app.get('/api/compare')
def compare(request:Request,old:str='1.0',new:str='2.0',project:str='body-comfort'):
    user(request,project);return store.compare(project,old,new)

@app.post('/api/review')
async def review(request:Request):
    data=await request.json();project=data.get('project','body-comfort');name,_=user(request,project,reviewer=True)
    return store.review(data.get('answer_id',''),data.get('decision',''),str(data.get('note','')),name,project)

@app.get('/api/export')
def export(request:Request,version:str='2.0',project:str='body-comfort'):
    name,_=user(request,project);data=store.export(project,version);store.audit(name,'export',{'version':version})
    return Response(json.dumps(data,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="HLD_review_{version}.json"'})

@app.get('/api/audit')
def audit(request:Request):
    user(request,reviewer=True)
    with store.db() as db:return [dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 40')]

