# CS1: AUTOSAR HLD Document Analysis Assistant

Student: Mukund Pradip Fegade | PRN: 123B1B197

Programme: Final Year Btech Computer Engineering 2027

## Start on the prepared computer

Double-click `START_PROJECT.bat` in the Desktop `techpulse-project` folder (or the launcher in this Code folder). Keep the terminal open. Once READY appears, open http://127.0.0.1:8765.

- Analyst: `student` / `student-demo`
- Reviewer: `reviewer` / `reviewer-demo`

These are public demonstration credentials for a loopback-only synthetic-data application. They are not production authentication. No external API key is required. Press Ctrl+C in the terminal to stop both servers.

## Another Windows computer

Keep all eight submission folders together. Run Code/SETUP_WINDOWS.bat once with internet access. It installs a portable Python runtime and the pinned libraries, downloads the recorded llama.cpp release, and verifies the supplied Qwen model checksum. It creates a sibling runtime folder; it does not require a system Python installation. Model weights and ONNX embedding files are supplied in Model_Prompts_Config/models. Then run Code/START_PROJECT.bat. The prepared Desktop installation has already been installed and tested; the secondary bootstrap script is provided for reproduction.

## Demonstrate

1. Sign in, view the indexed version 1.0 and 2.0 PDFs under Documents.
2. Ask which component decides door lock state; check the source filename, version and page.
3. Compare the DoorInput period in version 1.0 and 2.0.
4. Open Architecture to see components, interfaces, signals, ports, dependencies and flows, plus three candidate inconsistencies in version 2.0.
5. Compare revisions 1.0 and 2.0.
6. Sign in as reviewer, record a decision on an answer ID, inspect the audit log and download JSON.

The 5-minute narration and exact screen actions are in Video.

## Reproduce checks

With the app running, execute from the submission's parent folder:

    runtime\python\python.exe PCCOE_Mukund_Pradip_Fegade_PRN_123B1B197_AIML\Code\test_live.py
    runtime\python\python.exe PCCOE_Mukund_Pradip_Fegade_PRN_123B1B197_AIML\Code\evaluate.py

Results are written to Evaluation_Results. The integration checks upload the supplied DOCX and scanned PDF under separate test version labels. They do not replace the two baseline PDF versions. Generated answers can vary by runtime and hardware; report the results of your own rerun accurately.

## Files and methods

- core.py: PDF/DOCX/text ingestion, local OCR, 384-dimensional MiniLM embeddings, persistent Chroma retrieval, local Qwen generation, deterministic extraction and checks, SQLite records.
- app.py: FastAPI, cookie sessions, project authorization, review roles and exports.
- run.py: starts the local inference server and API, indexes default PDFs if needed.
- index.html: the browser interface.
- generate_sample_data.py: original synthetic fixture generator (uses Arial on Windows for its scanned page).
- evaluate.py / test_live.py: retrieval/generation measurements and integration checks.
- settings.py: resolves all paths relative to the submission; runtime state is outside the deliverable folder.

The sample record grammar is `KIND | name=value | field=value`. The inventory parser recognises COMPONENT, INTERFACE, PORT, SIGNAL, DEPENDENCY and FLOW. It is deliberately deterministic for this documented grammar; it is not a universal parser for arbitrary industrial HLDs or AUTOSAR ARXML. Arbitrary supported documents can still be uploaded and searched.

## Limits

The 13-question development set is synthetic. Threshold 0.25 was calibrated on it; the initial 0.34 results are retained. The final saved run passed 12/13 answer checks; one generated answer returned a footer rather than the component. Extraction matched 48 fixture records and detected three planted issues. These are not industrial accuracy or compliance claims.

The app uses local HTTP on loopback, a small quantised model, simple role checks and local audit storage. It does not provide enterprise identity, TLS, encryption at rest, automatic architecture approval, source-document rewriting or industrial deployment validation. Review generated text against the evidence. Requests and responses are stored locally for audit, so use only approved or synthetic data.

No Docker execution is claimed. MLOps evidence consists of pinned versions, downloaded model revision/checksum, source hashes, versioned HLDs, saved evaluation runs and review/audit records.
