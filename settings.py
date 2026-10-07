from pathlib import Path
import json, os

CODE = Path(__file__).resolve().parent
SUBMISSION = CODE.parent
ROOT = SUBMISSION.parent
RUNTIME = ROOT / 'runtime'
MODELS = SUBMISSION / 'Model_Prompts_Config' / 'models'
STATE = RUNTIME / 'state'
STATE.mkdir(parents=True, exist_ok=True)
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['HF_HOME'] = str(RUNTIME/'models'/'hf-cache')
CONFIG = json.loads((SUBMISSION/'Model_Prompts_Config'/'app_config.json').read_text())
PROMPT = (SUBMISSION/'Model_Prompts_Config'/'rag_system_prompt.txt').read_text()
