"""
main.py — THE BACKEND.
Level 1 always runs (fast, free). Level 2 (Gemini) runs only when requested,
to protect the free-tier quota. Serves the frontend + follow-up Q&A.
Saves each brief to history (non-blocking — a DB hiccup never breaks the app).
"""
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from clinicaltrials import fetch_trials, TrialsFetchError
from ai import answer_question
from scoring import score_citations
from pipeline import generate_verified_brief
from pdf_export import build_pdf
from database import save_brief, get_recent_briefs

app = FastAPI(title="Cheiron Demo API")


class BriefRequest(BaseModel):
    query: str
    run_level2: bool = False     # deep verify with Gemini (on-demand)
    demo_flaw: str = ""          # "", "fake_id", or "unsupported" (demo mode)


class AskRequest(BaseModel):
    question: str
    trials: list[dict]
    history: list[dict]


class PdfRequest(BaseModel):
    query: str
    brief_markdown: str
    score: dict
    sources: list[dict]
    conversation: list[dict] = []   # the follow-up Q&A, sent from the browser


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/brief")
def create_brief(request: BriefRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        trials = fetch_trials(query)
    except TrialsFetchError as error:
        raise HTTPException(status_code=502, detail=f"Could not fetch trials: {error}")

    if not trials:
        raise HTTPException(status_code=404,
            detail=f"No trials found for '{query}'. Try a drug or condition name.")

    result = generate_verified_brief(
        query, trials,
        run_level2=request.run_level2,
        demo_flaw=request.demo_flaw,
    )

    sources = [
        {"nct_id": t["nct_id"], "title": t["title"], "url": t["url"]}
        for t in trials
    ]

    # Save to history — NON-BLOCKING. If the DB is down, we log and move on;
    # the user still gets their brief. Storage is a bonus, never a blocker.
    try:
        save_brief(query, result["brief_markdown"], result["score"])
    except Exception as db_error:
        print(f"[history] Could not save brief (non-fatal): {db_error}")

    return {
        "query": query,
        "brief_markdown": result["brief_markdown"],
        "score": result["score"],
        "judge_results": result["judge_results"],
        "level2_status": result["level2_status"],
        "attempts": result["attempts"],
        "retry_log": result["retry_log"],
        "passed": result["passed"],
        "note": result["note"],
        "sources": sources,
        "trials": trials,
    }


@app.get("/api/history")
def history():
    """Return recent briefs. If the DB is unreachable, return an empty list
    rather than erroring — history is a bonus feature, not critical."""
    try:
        return {"briefs": get_recent_briefs(limit=10)}
    except Exception as db_error:
        print(f"[history] Could not read history (non-fatal): {db_error}")
        return {"briefs": []}


@app.post("/api/ask")
def ask_question(request: AskRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if not request.trials:
        raise HTTPException(status_code=400, detail="No trials in context to answer from.")

    answer = answer_question(question, request.trials, request.history)
    score = score_citations(answer, request.trials)
    return {"answer_markdown": answer, "score": score}


@app.post("/api/pdf")
def download_pdf(request: PdfRequest):
    pdf_bytes = build_pdf(
        query=request.query,
        brief=request.brief_markdown,
        score=request.score,
        sources=request.sources,
        conversation=request.conversation,
    )
    filename = f"clinical-brief-{request.query or 'session'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home():
    return FileResponse("static/index.html")