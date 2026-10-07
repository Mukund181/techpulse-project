"""Document ingestion, local semantic retrieval, RAG, extraction and review storage."""
import csv, hashlib, io, json, re, sqlite3, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx
import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from settings import CONFIG, PROMPT, RUNTIME, STATE, SUBMISSION, MODELS

def now(): return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self):
        self.dbpath=STATE/'project.sqlite3'
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, project TEXT, version TEXT, name TEXT, sha256 TEXT, pages INTEGER, method TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, document_id TEXT, project TEXT, version TEXT, page INTEGER, section TEXT, text TEXT);
            CREATE TABLE IF NOT EXISTS answers(id TEXT PRIMARY KEY, project TEXT, version TEXT, question TEXT, answer TEXT, mode TEXT, citations TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, artifact_id TEXT, reviewer TEXT, decision TEXT, note TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, detail TEXT, created TEXT);
            ''')
        ONNXMiniLM_L6_V2.DOWNLOAD_PATH=MODELS/'all-MiniLM-L6-v2'
        self.embedding=ONNXMiniLM_L6_V2(preferred_providers=['CPUExecutionProvider'])
        self.client=chromadb.PersistentClient(path=str(STATE/'chroma'), settings=Settings(anonymized_telemetry=False))
        self.lock=threading.RLock()

    def db(self):
        db=sqlite3.connect(self.dbpath);db.row_factory=sqlite3.Row;return db

    def audit(self,actor,action,detail):
        with self.db() as db: db.execute('INSERT INTO audit(actor,action,detail,created) VALUES(?,?,?,?)',(actor,action,json.dumps(detail),now()))

    def collection(self,project):
        if not re.fullmatch(r'[a-z][a-z0-9-]{2,39}',project):raise ValueError('Invalid project ID')
        return self.client.get_or_create_collection('hld-'+project,embedding_function=self.embedding,metadata={'hnsw:space':'cosine'})

    def extract_pages(self,path):
        suffix=path.suffix.lower()
        if suffix=='.pdf':
            from pypdf import PdfReader
            reader=PdfReader(path)
            if reader.is_encrypted:raise ValueError('Encrypted PDFs are not supported.')
            pages=[p.extract_text() or '' for p in reader.pages]
            method='PDF text'
            if any(len(p.strip())<30 for p in pages):
                import pypdfium2 as pdfium
                import numpy as np
                from rapidocr_onnxruntime import RapidOCR
                ocr=RapidOCR();pdf=pdfium.PdfDocument(path)
                for i,text in enumerate(pages):
                    if len(text.strip())>=30:continue
                    page=pdf[i];bitmap=page.render(scale=2);img=bitmap.to_pil();result,_=ocr(np.asarray(img));pages[i]='\n'.join(item[1] for item in result or []);bitmap.close();page.close()
                pdf.close();method='PDF text + OCR'
            return pages,method
        if suffix=='.docx':
            from docx import Document
            doc=Document(path)
            from docx.oxml.ns import qn
            pages=[''];page=0
            for element in doc.element.body:
                if element.tag==qn('w:p'):
                    text=''.join(element.itertext()) if False else ''.join(t.text or '' for t in element.iter(qn('w:t')))
                    pages[page]+=text+'\n'
                    if any(br.get(qn('w:type'))=='page' for br in element.iter(qn('w:br'))):pages.append('');page+=1
                elif element.tag==qn('w:tbl'):
                    for row in element.iter(qn('w:tr')):
                        cells=[' '.join(t.text or '' for t in cell.iter(qn('w:t'))) for cell in row.findall(qn('w:tc'))]
                        pages[page]+=' | '.join(cells)+'\n'
            return [p for p in pages if p.strip()],'DOCX logical pages'
        if suffix in ('.md','.txt'):return [path.read_text(encoding='utf-8')],'UTF-8 text'
        raise ValueError('Supported formats: PDF, DOCX, TXT and Markdown.')

    def ingest(self,path,project,version,actor='student'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,24}',version):raise ValueError('Use a short version label such as 2.0.')
        data=path.read_bytes()
        if len(data)>CONFIG['max_upload_bytes']:raise ValueError('File exceeds 5 MB.')
        digest=hashlib.sha256(data).hexdigest()
        docid=hashlib.sha256((project+'|'+version+'|'+digest).encode()).hexdigest()[:16]
        with self.db() as db:
            if db.execute('SELECT id FROM documents WHERE id=?',(docid,)).fetchone():return {'id':docid,'already_indexed':True}
        pages,method=self.extract_pages(path); chunks=[]
        for page_no,text in enumerate(pages,1):
            text=re.sub(r'[ \t]+',' ',text).strip()
            if not text:continue
            # Each sample page is one HLD section. Longer uploads are split into 160-word windows with 30-word overlap.
            words=text.split();section=text.splitlines()[0][:100]
            for j,start in enumerate(range(0,len(words),130)):
                chunk=text if len(words)<=190 else ' '.join(words[start:start+160])
                chunks.append({'id':f'{docid}-p{page_no}-c{j+1}','text':chunk,'page':page_no,'section':section})
                if len(words)<=190 or start+160>=len(words):break
        if not chunks:raise ValueError('No readable text was found.')
        metas=[{'document_id':docid,'name':path.name,'version':version,'page':c['page'],'section':c['section'],'project':project} for c in chunks]
        with self.lock:
            self.collection(project).upsert(ids=[c['id'] for c in chunks],documents=[c['text'] for c in chunks],metadatas=metas)
            with self.db() as db:
                db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?)',(docid,project,version,path.name,digest,len(pages),method,now()))
                db.executemany('INSERT INTO chunks VALUES(?,?,?,?,?,?,?)',[(c['id'],docid,project,version,c['page'],c['section'],c['text']) for c in chunks])
        self.audit(actor,'document_ingested',{'document_id':docid,'name':path.name,'version':version,'chunks':len(chunks),'method':method})
        return {'id':docid,'pages':len(pages),'chunks':len(chunks),'method':method,'sha256':digest}

    def documents(self,project):
        with self.db() as db:return [dict(r) for r in db.execute('SELECT * FROM documents WHERE project=? ORDER BY version,name',(project,))]

    def search(self,question,project,version):
        collection=self.collection(project)
        if not collection.count():return []
        result=collection.query(query_texts=[question],n_results=min(CONFIG['top_k'],collection.count()),where={'version':version},include=['documents','metadatas','distances'])
        return [{'id':i,'text':t,'score':round(max(0,1-dist),4),**meta} for i,t,meta,dist in zip(result['ids'][0],result['documents'][0],result['metadatas'][0],result['distances'][0])]

    def ask(self,question,project,version,actor='student'):
        question=question.strip()
        if not question or len(question)>CONFIG['max_question_chars']:raise ValueError('Enter a question between 1 and 500 characters.')
        start=time.perf_counter();hits=self.search(question,project,version);retrieval_ms=(time.perf_counter()-start)*1000
        guarded=bool(re.search(r'ignore (all |previous |the )?instructions|reveal (the )?(system|password)|system prompt',question,re.I))
        accepted=hits and hits[0]['score']>=CONFIG['minimum_similarity'] and not guarded
        mode='abstained';answer='The selected HLD does not provide sufficient evidence for this question.';llm_ms=0;warning=None
        citations=[]
        if accepted:
            citations=[h for h in hits if h['score']>=CONFIG['minimum_similarity']]
            context='\n\n'.join(f'SOURCE {i+1}: {h["name"]}, version {h["version"]}, page {h["page"]}\n{h["text"]}' for i,h in enumerate(citations))
            request={'model':'local-qwen','temperature':CONFIG['temperature'],'seed':CONFIG['seed'],'max_tokens':CONFIG['max_tokens'],'messages':[{'role':'system','content':PROMPT},{'role':'user','content':f'<evidence>\n{context}\n</evidence>\nQuestion: {question}\nGive the direct answer using only the evidence.'}]}
            try:
                t=time.perf_counter()
                with httpx.Client(timeout=120,trust_env=False) as client:r=client.post(CONFIG['llm_url'],json=request);r.raise_for_status()
                answer=r.json()['choices'][0]['message']['content'].strip();llm_ms=(time.perf_counter()-t)*1000;mode='local_llm'
                if not answer:raise ValueError('Empty model answer')
                # Detect unsupported numeric claims; do not silently accept them.
                if set(re.findall(r'\b\d+(?:\.\d+)?\b',answer))-set(re.findall(r'\b\d+(?:\.\d+)?\b',context+' '+question)):
                    warning='The generated draft contains a number not present in the retrieved evidence. Review it before use.'
            except (httpx.HTTPError,ValueError,KeyError,IndexError) as exc:
                answer=citations[0]['text'];mode='evidence_only';warning='Local model unavailable: showing the retrieved evidence only. No generated answer is claimed.'
        identifier=uuid.uuid4().hex[:16]
        response={'id':identifier,'question':question,'answer':answer,'mode':mode,'citations':citations,'retrieved':hits,'retrieval_ms':round(retrieval_ms,2),'generation_ms':round(llm_ms,2),'total_ms':round((time.perf_counter()-start)*1000,2),'warning':warning,'review_status':'Pending review','version':version}
        with self.db() as db:db.execute('INSERT INTO answers VALUES(?,?,?,?,?,?,?,?)',(identifier,project,version,question,answer,mode,json.dumps(citations),now()))
        self.audit(actor,'question_answered',{'answer_id':identifier,'mode':mode,'version':version,'source_ids':[c['id'] for c in citations]})
        return response

    def inventory(self,project,version):
        with self.db() as db:chunks=[dict(r) for r in db.execute('SELECT * FROM chunks WHERE project=? AND version=? ORDER BY page',(project,version))]
        entities=[];seen=set()
        # The supported synthetic record format is explicit and deterministic; no claim of universal AUTOSAR parsing.
        pattern=r'\b(COMPONENT|INTERFACE|PORT|SIGNAL|DEPENDENCY|FLOW)\s*\|\s*([^\n]+)'
        for c in chunks:
            for match in re.finditer(pattern,c['text']):
                fields={}
                for item in match[2].split('|'):
                    if '=' in item:
                        k,v=item.split('=',1);fields[k.strip()]=v.strip()
                key=(match[1],fields.get('name',''),fields.get('component',''))
                if key in seen:continue
                seen.add(key);entities.append({'kind':match[1],**fields,'source_id':c['id'],'page':c['page']})
        return entities

    def findings(self,project,version):
        entities=self.inventory(project,version);interfaces={e['name']:e for e in entities if e['kind']=='INTERFACE'};components={e['name'] for e in entities if e['kind']=='COMPONENT'};findings=[]
        for e in entities:
            if e['kind']=='PORT':
                it=interfaces.get(e.get('interface'))
                if not it:findings.append({'rule':'UNDEFINED_INTERFACE','message':f"Port {e['name']} references missing interface {e.get('interface')}.",'source_id':e['source_id'],'page':e['page']})
                elif e.get('type')!=it.get('type'):findings.append({'rule':'TYPE_MISMATCH','message':f"Port {e['name']} uses {e.get('type')}, while {it['name']} specifies {it.get('type')}.",'source_id':e['source_id'],'related_source_id':it['source_id'],'page':e['page']})
            if e['kind']=='DEPENDENCY':
                missing=[e[k] for k in ['from','to'] if e.get(k) not in components]
                if missing:findings.append({'rule':'UNKNOWN_COMPONENT','message':'Dependency '+e.get('name','')+' references unknown component(s): '+', '.join(missing)+'.','source_id':e['source_id'],'page':e['page']})
        return [{'id':f'{version}-{i+1}','status':'Candidate finding; human review required',**f} for i,f in enumerate(findings)]

    def compare(self,project,old,new):
        def mapping(version):return {(x['kind'],x.get('name',''),x.get('component','')):x for x in self.inventory(project,version)}
        a,b=mapping(old),mapping(new);changes=[]
        for key in sorted(set(a)|set(b)):
            if key not in a:changes.append({'kind':key[0],'name':key[1],'change':'Added','before':None,'after':b[key]})
            elif key not in b:changes.append({'kind':key[0],'name':key[1],'change':'Removed','before':a[key],'after':None})
            else:
                before={k:v for k,v in a[key].items() if k not in ['source_id','page']};after={k:v for k,v in b[key].items() if k not in ['source_id','page']}
                if before!=after:changes.append({'kind':key[0],'name':key[1],'change':'Modified','before':a[key],'after':b[key]})
        return changes

    def review(self,artifact,decision,note,actor,project):
        if decision not in ['Accepted','Rejected','Needs correction']:raise ValueError('Invalid decision')
        with self.db() as db:
            if not db.execute('SELECT id FROM answers WHERE id=? AND project=?',(artifact,project)).fetchone():raise ValueError('Answer not found in this project')
            db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,artifact,actor,decision,note[:1000],now()))
        self.audit(actor,'review_recorded',{'answer_id':artifact,'decision':decision})
        return {'status':decision,'reviewer':actor,'note':note[:1000]}

    def export(self,project,version):
        with self.db() as db:
            answers=[dict(r) for r in db.execute('SELECT * FROM answers WHERE project=? AND version=?',(project,version))]
            reviews=[dict(r) for r in db.execute('SELECT r.* FROM reviews r JOIN answers a ON a.id=r.artifact_id WHERE a.project=? AND a.version=?',(project,version))]
        return {'project':project,'version':version,'created':now(),'documents':self.documents(project),'inventory':self.inventory(project,version),'findings':self.findings(project,version),'answers':answers,'reviews':reviews}
