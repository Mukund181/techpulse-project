"""Meaningful integration checks against the locally running service."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import httpx
from settings import SUBMISSION
BASE='http://127.0.0.1:8765'

class LiveTests(unittest.TestCase):
    def setUp(self):
        self.client=httpx.Client(base_url=BASE,timeout=180,trust_env=False)
        self.client.post('/api/login',json={'username':'student','password':'student-demo'}).raise_for_status()
    def tearDown(self):self.client.close()
    def test_unauthenticated_access_denied(self):
        with httpx.Client(base_url=BASE,trust_env=False) as c:self.assertEqual(c.get('/api/documents').status_code,401)
    def test_project_isolation(self):self.assertEqual(self.client.get('/api/documents?project=unrelated-project').status_code,403)
    def test_analyst_cannot_approve(self):self.assertEqual(self.client.post('/api/review',json={'answer_id':'missing','decision':'Accepted','note':'test'}).status_code,403)
    def test_empty_question(self):self.assertEqual(self.client.post('/api/ask',json={'question':' '}).status_code,400)
    def test_question_length(self):self.assertEqual(self.client.post('/api/ask',json={'question':'x'*501}).status_code,400)
    def test_wrong_question_type(self):self.assertEqual(self.client.post('/api/ask',json={'question':123}).status_code,400)
    def test_cross_origin_write(self):self.assertEqual(self.client.post('/api/login',json={},headers={'origin':'https://example.com'}).status_code,403)
    def test_invalid_upload_type(self):self.assertEqual(self.client.post('/api/ingest',data={'version':'2.0'},files={'file':('sample.exe',b'not executable')}).status_code,400)
    def test_baseline_and_revised_findings(self):
        a=self.client.get('/api/inventory?version=1.0').json();b=self.client.get('/api/inventory?version=2.0').json()
        self.assertEqual(a['findings'],[]);self.assertEqual(sorted(x['rule'] for x in b['findings']),['TYPE_MISMATCH','UNDEFINED_INTERFACE','UNKNOWN_COMPONENT'])
    def test_revision_period_change(self):
        changes=self.client.get('/api/compare').json();x=next(x for x in changes if x['kind']=='COMPONENT' and x['name']=='DoorInput')
        self.assertEqual(x['before']['period_ms'],'10');self.assertEqual(x['after']['period_ms'],'20')
    def test_docx_ingestion(self):
        path=SUBMISSION/'Input_Data'/'BodyComfort_HLD_v1.0.docx'
        with path.open('rb') as f:r=self.client.post('/api/ingest',data={'version':'docx-test'},files={'file':(path.name,f)});r.raise_for_status()
        doc=next(x for x in self.client.get('/api/documents').json() if x['version']=='docx-test')
        self.assertEqual(doc['pages'],6);self.assertIn('DOCX',doc['method'])
    def test_scanned_pdf_ocr(self):
        path=SUBMISSION/'Input_Data'/'scanned_hld_sample.pdf'
        with path.open('rb') as f:r=self.client.post('/api/ingest',data={'version':'ocr-test'},files={'file':(path.name,f)});r.raise_for_status()
        doc=next(x for x in self.client.get('/api/documents').json() if x['version']=='ocr-test');self.assertIn('OCR',doc['method'])
    def test_reviewer_workflow(self):
        answer=self.client.post('/api/ask',json={'question':'A recipe for cake','version':'2.0'}).json()
        self.client.post('/api/login',json={'username':'reviewer','password':'reviewer-demo'}).raise_for_status()
        r=self.client.post('/api/review',json={'answer_id':answer['id'],'decision':'Accepted','note':'Automated workflow test: accepted the no-evidence response, not an engineering design.'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['status'],'Accepted')
        events=self.client.get('/api/audit').json();self.assertTrue(any(e['action']=='review_recorded' for e in events))

if __name__=='__main__':
    import io
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LiveTests));text=stream.getvalue()
    print(text);(SUBMISSION/'Evaluation_Results'/'integration_tests.txt').write_text(text,encoding='utf-8')
    (SUBMISSION/'Evaluation_Results'/'integration_summary.json').write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful()},indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
