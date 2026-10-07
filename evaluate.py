"""Exercise the running local app and save measured results; python evaluate.py."""
from pathlib import Path
import sys,json,time,csv,statistics,platform
sys.path.insert(0,str(Path(__file__).resolve().parent))
import httpx
from settings import SUBMISSION,CONFIG
OUT=SUBMISSION/'Evaluation_Results'
client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=180,trust_env=False)
client.post('/api/login',json={'username':'student','password':'student-demo'}).raise_for_status()
cases=json.loads((OUT/'test_questions.json').read_text());rows=[]
for case in cases:
    r=client.post('/api/ask',json={'question':case['question'],'version':case['version']});r.raise_for_status();answer=r.json()
    page=case['expected_page'];hits=[x['page'] for x in answer['retrieved']];cited=[x['page'] for x in answer['citations']]
    keyword_pass=all(t.lower() in answer['answer'].lower() for t in case['expected_terms'])
    passed=(answer['mode']=='abstained') if page is None else (answer['mode']=='local_llm' and page in cited and keyword_pass)
    row={**case,**answer,'id':case['id'],'answer_id':answer['id'],'expected_keyword_check':keyword_pass,'retrieval_hit_at_3':page in hits if page else None,'pass':passed};rows.append(row)
    print(case['id'],answer['mode'],'PASS' if passed else 'FAIL',round(answer['total_ms']/1000,2),'s',flush=True)
gold=json.loads((SUBMISSION/'Input_Data'/'ground_truth_entities.json').read_text());entity_results={};finding_results={}
for version in ['1.0','2.0']:
    data=client.get('/api/inventory',params={'version':version}).json()
    clean=lambda entity:{k:v for k,v in entity.items() if k not in ['source_id','page']}
    expected={json.dumps({k:str(v) for k,v in x.items()},sort_keys=True) for x in gold[version]['entities']}
    actual={json.dumps(clean(x),sort_keys=True) for x in data['entities']}
    entity_results[version]={'expected':len(expected),'actual':len(actual),'true_positive':len(expected&actual),'missing':[json.loads(x) for x in expected-actual],'extra':[json.loads(x) for x in actual-expected]}
    actual_rules=sorted(x['rule'] for x in data['findings']);expected_rules=sorted(gold[version]['expected_rules'])
    finding_results[version]={'actual':actual_rules,'expected':expected_rules,'pass':actual_rules==expected_rules}
positive=[r for r in rows if r['expected_page']];negative=[r for r in rows if r['expected_page'] is None]
summary={'python':platform.python_version(),'platform':platform.platform(),'total_questions':len(rows),'passed':sum(x['pass'] for x in rows),'answerable':len(positive),'answerable_passed':sum(x['pass'] for x in positive),'retrieval_hits_at_3':sum(x['retrieval_hit_at_3'] for x in positive),'unanswerable':len(negative),'correct_abstentions':sum(x['pass'] for x in negative),'local_llm_answers':sum(x['mode']=='local_llm' for x in rows),'median_total_ms':round(statistics.median(x['total_ms'] for x in positive),2),'median_retrieval_ms':round(statistics.median(x['retrieval_ms'] for x in rows),2),'entity_results':entity_results,'finding_results':finding_results,'limitations':'Synthetic development fixtures. Answer checks use expected keywords and source pages; they are not expert validation of every generated claim. Timing includes retrieval and local model generation, excluding initial startup.'}
(OUT/'rag_results.json').write_text(json.dumps({'summary':summary,'results':rows},indent=2),encoding='utf-8')
with (OUT/'rag_results.csv').open('w',newline='',encoding='utf-8') as f:
    fields=['id','question','version','expected_page','mode','pass','retrieval_hit_at_3','expected_keyword_check','retrieval_ms','generation_ms','total_ms','answer'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
(OUT/'entity_and_finding_results.json').write_text(json.dumps({'entities':entity_results,'findings':finding_results},indent=2))
changes=client.get('/api/compare').json();(OUT/'revision_changes.json').write_text(json.dumps(changes,indent=2))
export=client.get('/api/export').json();(OUT/'sample_project_export.json').write_text(json.dumps(export,indent=2))
print(json.dumps(summary,indent=2),flush=True)
