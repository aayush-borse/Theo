from __future__ import annotations
import csv, hashlib, io, json, mimetypes, uuid, os, zipfile
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, BackgroundTasks, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text
from app.core.database import get_db, SessionLocal
from app.core.config import UPLOAD_DIR, EXPORT_DIR, MAX_UPLOAD_MB, ROOT, ALLOWED_ORIGINS
from app.domain.models import Dataset, Sample, Annotation, AuditEvent, DatasetRelease, ProcessingJob, ReviewDecision, User, GoldLabel, EvaluationRun, now
from app.services.evaluation import classification_metrics, expected_calibration_error, cohen_kappa, krippendorff_alpha_nominal, subgroup_audit
from app.services.validation import validate_annotation
from app.security.passwords import hash_password, verify_password
from app.security.tokens import issue_token, verify_token
from app.providers.registry import PROVIDERS
from app.services.quality import report

if os.getenv("THEO_AUTO_MIGRATE","true").lower()=="true":
    from alembic import command
    from alembic.config import Config
    alembic_config=Config(str(Path(__file__).resolve().parents[1]/"alembic.ini"))
    command.upgrade(alembic_config,"head")

app=FastAPI(title="THEO API", version="1.1.0", description="Trusted Evidence-based Annotation & Quality Orchestration for multimodal datasets.")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=False, allow_methods=["GET","POST","PATCH","DELETE"], allow_headers=["Content-Type","X-Request-ID"])

@app.middleware("http")
async def optional_authentication_gate(request, call_next):
    """Set THEO_AUTH_REQUIRED=true in deployed environments to protect every API route."""
    path=request.url.path
    if os.getenv("THEO_AUTH_REQUIRED","false").lower()=="true" and request.method!="OPTIONS" and path.startswith("/api/") and path not in ("/api/health","/api/auth/login","/api/auth/register"):
        from starlette.responses import JSONResponse
        header=request.headers.get("authorization","")
        if not header.startswith("Bearer "):
            return JSONResponse({"detail":"Authentication required"},status_code=401)
        try: claims=verify_token(header[7:])
        except ValueError as exc:
            return JSONResponse({"detail":str(exc)},status_code=401)
        auth_db=SessionLocal()
        try:
            account=auth_db.query(User).filter_by(username=claims.get("sub"),active=True).first()
            if not account: return JSONResponse({"detail":"Account is inactive or no longer exists"},status_code=401)
            role=account.role
        finally: auth_db.close()
        if request.method in ("POST","PATCH","DELETE") and role not in ("admin","reviewer"):
            return JSONResponse({"detail":"Reviewer or administrator role required"},status_code=403)
        if request.method=="DELETE" and role!="admin":
            return JSONResponse({"detail":"Administrator role required for deletion"},status_code=403)
        if path.endswith("/releases") and request.method=="POST" and role!="admin":
            return JSONResponse({"detail":"Administrator role required to publish dataset releases"},status_code=403)
    return await call_next(request)

class DatasetCreate(BaseModel):
    name: str=Field(min_length=2,max_length=160)
    description: str=Field(default="",max_length=4000)
    modality: str
    task: str=Field(default="general",max_length=60)
    annotation_schema: dict[str,Any]=Field(default_factory=dict, alias="schema_json")
    model_config = {"populate_by_name": True}
class DatasetUpdate(BaseModel):
    name: str|None=Field(default=None,min_length=2,max_length=160)
    description: str|None=Field(default=None,max_length=4000)
    task: str|None=Field(default=None,max_length=60)
    annotation_schema: dict[str,Any]|None=Field(default=None, alias="schema_json")
    model_config = {"populate_by_name": True}
class ReviewUpdate(BaseModel):
    status: str
    label: dict | None=None
    reviewer: str=Field(default="reviewer",max_length=120)
    note: str=Field(default="",max_length=4000)

class Credentials(BaseModel):
    username: str=Field(min_length=3,max_length=80,pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str=Field(min_length=12,max_length=200)

class EvaluationRequest(BaseModel):
    y_true: list[str]=Field(min_length=1,max_length=100000)
    y_pred: list[str]=Field(min_length=1,max_length=100000)

class CalibrationRequest(BaseModel):
    confidences: list[float]=Field(min_length=1,max_length=100000)
    correct: list[bool]=Field(min_length=1,max_length=100000)
    bins: int=Field(default=10,ge=2,le=100)

class AgreementRequest(BaseModel):
    rater_a: list[str|None]
    rater_b: list[str|None]

class MultiRaterRequest(BaseModel):
    ratings: list[list[str|None]]

class BiasAuditRequest(BaseModel):
    labels: list[str]
    outcomes: list[bool]
    groups: list[str]

class GoldLabelCreate(BaseModel):
    sample_id: int
    task: str=Field(min_length=2,max_length=80)
    label: dict[str,Any]
    verified_by: str=Field(min_length=2,max_length=120)
    guideline_version: str=Field(default="1",max_length=80)

class GoldEvaluationRequest(BaseModel):
    task: str=Field(default="classification",max_length=60)
    label_key: str=Field(default="label",max_length=80)
    reference_version: str=Field(default="1",max_length=80)

def current_user(authorization: str|None=Header(default=None), db:Session=Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401,"Bearer token required")
    try: claims=verify_token(authorization[7:])
    except ValueError as exc: raise HTTPException(401,str(exc))
    user=db.query(User).filter_by(username=claims.get("sub"),active=True).first()
    if not user: raise HTTPException(401,"Account is inactive or no longer exists")
    return {**claims,"role":user.role}

def require_role(*roles):
    def dependency(user=Depends(current_user)):
        if user.get("role") not in roles: raise HTTPException(403,"Insufficient role")
        return user
    return dependency

@app.get("/api/health")
def health(): return {"status":"ok","service":"theo","version":"1.1.0","providers":list(PROVIDERS),"auth_required":os.getenv("THEO_AUTH_REQUIRED","false").lower()=="true","queue":"celery" if os.getenv("THEO_USE_CELERY","false").lower()=="true" else "in-process"}

@app.get("/api/health/ready")
def readiness(db:Session=Depends(get_db)):
    try: db.execute(text("SELECT 1"))
    except Exception as exc: raise HTTPException(503,f"Database readiness check failed: {str(exc)[:200]}")
    return {"status":"ready","database":"reachable","providers":list(PROVIDERS)}

@app.post("/api/auth/register")
def register(payload:Credentials, db:Session=Depends(get_db)):
    """Bootstrap the first administrator; subsequent accounts require an admin token."""
    count=db.query(User).count()
    if count and not os.getenv("THEO_ALLOW_SELF_REGISTER","false").lower()=="true":
        raise HTTPException(403,"Public registration is disabled. Ask an administrator to provision an account.")
    if count and not os.getenv("THEO_ALLOW_SELF_REGISTER","false").lower()=="true": raise HTTPException(403,"Registration disabled")
    if db.query(User).filter_by(username=payload.username).first(): raise HTTPException(409,"Username already exists")
    user=User(username=payload.username,password_hash=hash_password(payload.password),role="admin" if count==0 else "reviewer")
    db.add(user); db.commit(); db.refresh(user)
    return {"id":user.id,"username":user.username,"role":user.role,"message":"First account is administrator." if user.role=="admin" else "Account created."}

@app.post("/api/auth/login")
def login(payload:Credentials, db:Session=Depends(get_db)):
    user=db.query(User).filter_by(username=payload.username,active=True).first()
    if not user or not verify_password(payload.password,user.password_hash): raise HTTPException(401,"Invalid credentials")
    try: token=issue_token(user.username,user.role)
    except ValueError as exc: raise HTTPException(503,str(exc))
    return {"access_token":token,"token_type":"bearer","expires_in":3600,"user":{"username":user.username,"role":user.role}}

@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user

@app.post("/api/auth/users")
def create_user(payload:Credentials, role:str="reviewer", admin=Depends(require_role("admin")), db:Session=Depends(get_db)):
    if role not in ("admin","reviewer","viewer"): raise HTTPException(422,"Role must be admin, reviewer or viewer")
    if db.query(User).filter_by(username=payload.username).first(): raise HTTPException(409,"Username already exists")
    user=User(username=payload.username,password_hash=hash_password(payload.password),role=role)
    db.add(user); db.commit(); db.refresh(user)
    return {"id":user.id,"username":user.username,"role":user.role}

@app.get("/api/capabilities")
def capabilities():
    return {"modalities":{"text":{"extensions":[".txt",".md",".json",".jsonl"],"tasks":["text_inventory","optional_transformers_sentiment","optional_transformers_ner"]},"image":{"extensions":[".jpg",".jpeg",".png",".webp",".gif",".bmp"],"tasks":["integrity_metadata","optional_yolo_object_detection","optional_transformers_classification"]},"document":{"extensions":[".pdf"],"tasks":["pdf_text_extraction","pdf_table_extraction","optional_tesseract_ocr"]},"tabular":{"extensions":[".csv"],"tasks":["schema_inference","missingness","duplicates","iqr_outlier_flags"]},"audio":{"extensions":[".wav",".mp3",".m4a",".flac",".ogg"],"tasks":["metadata","optional_faster_whisper_transcription","optional_pyannote_diarization"]},"video":{"extensions":[".mp4",".mov",".mkv",".avi",".webm"],"tasks":["metadata","temporal_frame_sampling","optional_yolo_object_tracking"]}},"quality":{"classification_metrics":True,"confidence_calibration":True,"cohen_kappa":True,"krippendorff_alpha_nominal":True,"descriptive_subgroup_audit":True},"workflow":["ingest","annotate","validate","human_review","adjudicate","release","export"],"principles":["Reported confidence is not accuracy.","Predictions are proposals, never ground truth by default.","Sensitive group attributes are never inferred; subgroup audits use explicit supplied data.","Optional model integrations require separately installed dependencies and configured model references."]}

@app.get("/api/overview")
def overview(db:Session=Depends(get_db)):
    datasets=db.query(Dataset).all(); samples=db.query(Sample).count(); annotations=db.query(Annotation).count()
    pending=db.query(Annotation).filter(Annotation.status=="REVIEW_REQUIRED").count()
    return {"datasets":len(datasets),"samples":samples,"annotations":annotations,"pending_reviews":pending,"approved":db.query(Annotation).filter(Annotation.status=="APPROVED").count(),"modalities":{m:sum(1 for d in datasets if d.modality==m) for m in PROVIDERS}}

@app.get("/api/datasets")
def list_datasets(q:str|None=None, modality:str|None=None, limit:int=Query(100,ge=1,le=500), offset:int=Query(0,ge=0), db:Session=Depends(get_db)):
    query=db.query(Dataset)
    if q: query=query.filter(Dataset.name.ilike(f"%{q[:120]}%"))
    if modality: query=query.filter(Dataset.modality==modality)
    rows=query.order_by(Dataset.created_at.desc()).offset(offset).limit(limit).all()
    return [_dataset_dict(d) for d in rows]

@app.post("/api/datasets")
def create_dataset(payload:DatasetCreate, db:Session=Depends(get_db)):
    if payload.modality not in PROVIDERS: raise HTTPException(400,"Unsupported modality. Choose image, text, document, tabular, audio or video.")
    values=payload.model_dump(exclude={"annotation_schema"}); values["schema_json"]=payload.annotation_schema
    d=Dataset(**values); db.add(d); db.flush(); _audit(db,"dataset",d.id,"created",{"modality":d.modality}); db.commit(); db.refresh(d)
    return _dataset_dict(d)

@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id:int, db:Session=Depends(get_db)):
    d=db.query(Dataset).options(joinedload(Dataset.samples).joinedload(Sample.annotations)).filter(Dataset.id==dataset_id).first()
    if not d: raise HTTPException(404,"Dataset not found")
    return _dataset_dict(d,True)

@app.patch("/api/datasets/{dataset_id}")
def update_dataset(dataset_id:int,payload:DatasetUpdate,db:Session=Depends(get_db)):
    d=db.get(Dataset,dataset_id)
    if not d: raise HTTPException(404,"Dataset not found")
    if db.query(DatasetRelease).filter_by(dataset_id=d.id).first(): raise HTTPException(409,"Released dataset metadata is immutable. Clone the dataset before editing.")
    changes=payload.model_dump(exclude_unset=True,exclude={"annotation_schema"})
    if payload.annotation_schema is not None: changes["schema_json"]=payload.annotation_schema
    for k,v in changes.items(): setattr(d,k,v)
    _audit(db,"dataset",d.id,"updated",changes); db.commit(); db.refresh(d); return _dataset_dict(d)

@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id:int, db:Session=Depends(get_db)):
    d=db.get(Dataset,dataset_id)
    if not d: raise HTTPException(404,"Dataset not found")
    if db.query(DatasetRelease).filter_by(dataset_id=d.id).first(): raise HTTPException(409,"Released datasets cannot be deleted through the application API.")
    paths=[s.storage_path for s in d.samples]
    db.delete(d); db.commit()
    for raw_path in set(paths):
        if db.query(Sample).filter_by(storage_path=raw_path).count()==0:
            try: Path(raw_path).unlink(missing_ok=True)
            except OSError: pass
    return {"deleted":dataset_id}

ALLOWED={"text":{".txt",".md",".json",".jsonl"},"image":{".jpg",".jpeg",".png",".webp",".gif",".bmp"},"document":{".pdf"},"tabular":{".csv"},"audio":{".wav",".mp3",".m4a",".flac",".ogg"},"video":{".mp4",".mov",".mkv",".avi",".webm"}}
@app.post("/api/datasets/{dataset_id}/samples")
async def upload_samples(dataset_id:int, files:list[UploadFile]=File(...), db:Session=Depends(get_db)):
    d=db.get(Dataset,dataset_id)
    if not d: raise HTTPException(404,"Dataset not found")
    if db.query(DatasetRelease).filter_by(dataset_id=d.id).first(): raise HTTPException(409,"Dataset is frozen after release. Clone it to create a new working version.")
    if not files: raise HTTPException(400,"Choose at least one file")
    created=[]
    for upload in files:
        raw=await upload.read(MAX_UPLOAD_MB*1024*1024+1)
        safe=Path(upload.filename or "upload.bin").name
        if len(raw)>MAX_UPLOAD_MB*1024*1024: raise HTTPException(413,f"{safe} exceeds {MAX_UPLOAD_MB} MB limit")
        if not raw: continue
        suffix=Path(safe).suffix.lower()
        if suffix not in ALLOWED[d.modality]: raise HTTPException(415,f"File type {suffix or '(no extension)'} is not supported for {d.modality} datasets")
        digest=hashlib.sha256(raw).hexdigest()
        # Prevent accidental duplicate ingestion within one dataset.
        if db.query(Sample).filter_by(dataset_id=d.id,sha256=digest).first(): continue
        path=UPLOAD_DIR/f"{digest[:16]}_{uuid.uuid4().hex[:10]}_{safe}"; path.write_bytes(raw)
        sample=Sample(dataset_id=d.id,filename=safe,content_type=upload.content_type or mimetypes.guess_type(safe)[0] or "application/octet-stream",storage_path=str(path),size_bytes=len(raw),sha256=digest)
        if d.modality=="text": sample.extracted_text=raw.decode("utf-8",errors="replace")[:500000]
        elif d.modality=="tabular": sample.extracted_text=raw.decode("utf-8-sig",errors="replace")[:500000]
        db.add(sample); db.flush(); created.append(_sample_dict(sample)); _audit(db,"sample",sample.id,"uploaded",{"sha256":digest,"size_bytes":len(raw)})
    db.commit(); return {"uploaded":len(created),"duplicates_skipped":len(files)-len(created),"samples":created}

@app.get("/api/samples/{sample_id}")
def get_sample(sample_id:int,db:Session=Depends(get_db)):
    s=db.query(Sample).options(joinedload(Sample.annotations)).filter(Sample.id==sample_id).first()
    if not s: raise HTTPException(404,"Sample not found")
    return {**_sample_dict(s),"dataset_id":s.dataset_id,"metadata":s.metadata_json,"extracted_text_preview":s.extracted_text[:5000],"annotations":[_annotation_dict(a) for a in s.annotations]}

@app.delete("/api/samples/{sample_id}")
def delete_sample(sample_id:int,db:Session=Depends(get_db)):
    s=db.get(Sample,sample_id)
    if not s: raise HTTPException(404,"Sample not found")
    if db.query(DatasetRelease).filter_by(dataset_id=s.dataset_id).first(): raise HTTPException(409,"Released dataset samples are immutable. Clone the dataset before editing.")
    raw_path=s.storage_path; _audit(db,"sample",s.id,"deleted",{"sha256":s.sha256}); db.delete(s); db.commit()
    if db.query(Sample).filter_by(storage_path=raw_path).count()==0: Path(raw_path).unlink(missing_ok=True)
    return {"deleted":sample_id}

@app.post("/api/datasets/{dataset_id}/annotate")
def annotate_dataset(dataset_id:int,background:BackgroundTasks,db:Session=Depends(get_db)):
    d=db.get(Dataset,dataset_id)
    if not d: raise HTTPException(404,"Dataset not found")
    samples=db.query(Sample).filter_by(dataset_id=d.id).count()
    if samples==0: raise HTTPException(409,"Upload samples before running annotation")
    job=ProcessingJob(id=str(uuid.uuid4()),dataset_id=d.id,kind="ANNOTATION",status="QUEUED",total=samples)
    db.add(job); db.commit()
    if os.getenv("THEO_USE_CELERY","false").lower()=="true":
        try:
            from app.workers.tasks import annotate_dataset_task
            annotate_dataset_task.delay(job.id)
        except Exception as exc:
            job.status="FAILED"; job.error=f"Queue dispatch failed: {str(exc)[:500]}"; db.commit()
            raise HTTPException(503,"Distributed queue unavailable; start Redis and a THEO Celery worker or disable THEO_USE_CELERY.")
    else:
        background.add_task(_run_annotation_job,job.id)
    return {"job_id":job.id,"status":"QUEUED","total":samples,"queue":"celery" if os.getenv("THEO_USE_CELERY","false").lower()=="true" else "in-process","message":"Annotation job queued. All generated proposals require human review."}

@app.get("/api/jobs")
def list_jobs(limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    return [_job_dict(j) for j in db.query(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(limit).all()]
@app.get("/api/jobs/{job_id}")
def get_job(job_id:str,db:Session=Depends(get_db)):
    j=db.get(ProcessingJob,job_id)
    if not j: raise HTTPException(404,"Job not found")
    return _job_dict(j)

def _run_annotation_job(job_id:str):
    db=SessionLocal()
    try:
        job=db.get(ProcessingJob,job_id)
        if not job:return
        job.status="RUNNING"; job.started_at=now(); db.commit()
        dataset=db.get(Dataset,job.dataset_id); provider=PROVIDERS[dataset.modality]
        samples=db.query(Sample).filter_by(dataset_id=dataset.id).order_by(Sample.id).all(); created=0; skipped=0; failed=0
        for index,sample in enumerate(samples,1):
            existing=db.query(Annotation).filter_by(sample_id=sample.id).first()
            if existing: skipped+=1
            else:
                try:
                    proposal=provider.annotate(sample,Path(sample.storage_path))
                    validation=validate_annotation(sample,proposal.label,dataset.schema_json or {})
                    evidence={**(proposal.evidence or {}),"structural_validation":validation}
                    a=Annotation(sample_id=sample.id,status=proposal.status,label=proposal.label,original_label=proposal.label,provider=proposal.provider,confidence=proposal.confidence,evidence=evidence)
                    db.add(a); db.flush(); _audit(db,"annotation",a.id,"proposed",{"provider":proposal.provider,"status":proposal.status}); created+=1
                except Exception as exc:
                    failed+=1
                    _audit(db,"sample",sample.id,"annotation_failed",{"error":str(exc)[:500]})
            job.progress=index; db.commit()
        job.status="PARTIAL" if failed else "SUCCEEDED"; job.result={"created":created,"skipped":skipped,"failed":failed,"provider":provider.name}; job.finished_at=now(); db.commit()
    except Exception as exc:
        db.rollback(); job=db.get(ProcessingJob,job_id)
        if job: job.status="FAILED"; job.error=str(exc)[:2000]; job.finished_at=now(); db.commit()
    finally: db.close()

@app.get("/api/datasets/{dataset_id}/quality")
def quality(dataset_id:int, db:Session=Depends(get_db)):
    d=db.query(Dataset).options(joinedload(Dataset.samples).joinedload(Sample.annotations)).filter(Dataset.id==dataset_id).first()
    if not d: raise HTTPException(404,"Dataset not found")
    return report(d)

@app.get("/api/annotations")
def list_annotations(status:str|None=None,dataset_id:int|None=None,limit:int=Query(500,ge=1,le=1000),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    q=db.query(Annotation).options(joinedload(Annotation.sample).joinedload(Sample.dataset))
    if status:q=q.filter(Annotation.status==status.upper())
    if dataset_id:q=q.join(Sample).filter(Sample.dataset_id==dataset_id)
    return [_annotation_dict(a) for a in q.order_by(Annotation.updated_at.desc()).offset(offset).limit(limit).all()]

@app.patch("/api/annotations/{annotation_id}")
def review_annotation(annotation_id:int,payload:ReviewUpdate,db:Session=Depends(get_db)):
    if payload.status not in ("APPROVED","REJECTED","REVIEW_REQUIRED"): raise HTTPException(400,"Status must be APPROVED, REJECTED or REVIEW_REQUIRED")
    a=db.get(Annotation,annotation_id)
    if not a: raise HTTPException(404,"Annotation not found")
    if payload.label is not None: a.label=payload.label
    dataset=db.get(Dataset,a.sample.dataset_id)
    validation=validate_annotation(a.sample,a.label,dataset.schema_json or {})
    a.evidence={**(a.evidence or {}),"structural_validation":validation}
    if payload.status=="APPROVED" and not validation["passed"]:
        raise HTTPException(409,"Annotation cannot be approved: structural validation failed. Correct the label or schema first.")
    a.status=payload.status; a.reviewed_by=payload.reviewer; a.reviewer_note=payload.note; a.reviewed_at=now()
    db.add(ReviewDecision(annotation_id=a.id,reviewer=payload.reviewer,decision=payload.status,label=payload.label or a.label,note=payload.note))
    _audit(db,"annotation",a.id,"reviewed",{"status":a.status,"reviewer":a.reviewed_by,"corrected":payload.label is not None})
    db.commit(); db.refresh(a); return _annotation_dict(a)

@app.get("/api/annotations/{annotation_id}/decisions")
def annotation_decisions(annotation_id:int,db:Session=Depends(get_db)):
    if not db.get(Annotation,annotation_id): raise HTTPException(404,"Annotation not found")
    return [{"id":d.id,"reviewer":d.reviewer,"decision":d.decision,"label":d.label,"note":d.note,"created_at":d.created_at.isoformat()} for d in db.query(ReviewDecision).filter_by(annotation_id=annotation_id).order_by(ReviewDecision.created_at).all()]

@app.post("/api/annotations/{annotation_id}/adjudicate")
def adjudicate(annotation_id:int,payload:ReviewUpdate,db:Session=Depends(get_db)):
    if payload.status not in ("APPROVED","REJECTED"): raise HTTPException(400,"Adjudication must APPROVE or REJECT")
    a=db.get(Annotation,annotation_id)
    if not a: raise HTTPException(404,"Annotation not found")
    if db.query(DatasetRelease).filter_by(dataset_id=a.sample.dataset_id).first(): raise HTTPException(409,"Released annotations are immutable. Clone the dataset to create a new working version.")
    prior=db.query(ReviewDecision).filter_by(annotation_id=annotation_id).all()
    if len({item.reviewer for item in prior})<2: raise HTTPException(409,"Adjudication requires decisions from at least two distinct reviewers")
    disagreement=len({(item.decision,json.dumps(item.label,sort_keys=True)) for item in prior})>1
    if not disagreement: raise HTTPException(409,"No disagreement exists to adjudicate")
    decision=ReviewDecision(annotation_id=annotation_id,reviewer=payload.reviewer,decision=payload.status,label=payload.label or a.label,note=payload.note)
    db.add(decision); a.status=payload.status; a.label=payload.label or a.label; a.reviewed_by=payload.reviewer; a.reviewer_note=payload.note; a.reviewed_at=now()
    _audit(db,"annotation",a.id,"adjudicated",{"status":a.status,"reviewer":payload.reviewer,"prior_decisions":len(prior)})
    db.commit(); db.refresh(a); return {"annotation":_annotation_dict(a),"decision_count":len(prior)+1}

@app.post("/api/datasets/{dataset_id}/gold-labels")
def create_gold_label(dataset_id:int,payload:GoldLabelCreate,db:Session=Depends(get_db)):
    dataset=db.get(Dataset,dataset_id)
    if not dataset: raise HTTPException(404,"Dataset not found")
    if db.query(DatasetRelease).filter_by(dataset_id=dataset_id).first(): raise HTTPException(409,"Gold labels are immutable after release. Clone the dataset to create a new working version.")
    sample=db.get(Sample,payload.sample_id)
    if not sample or sample.dataset_id!=dataset_id: raise HTTPException(404,"Sample does not belong to this dataset")
    existing=db.query(GoldLabel).filter_by(sample_id=sample.id,task=payload.task).first()
    if existing: raise HTTPException(409,"A gold label already exists for this sample and task")
    gold=GoldLabel(sample_id=sample.id,task=payload.task,label=payload.label,verified_by=payload.verified_by,guideline_version=payload.guideline_version)
    db.add(gold); db.flush(); _audit(db,"gold_label",gold.id,"verified_gold_label_added",{"sample_id":sample.id,"task":payload.task,"verified_by":payload.verified_by,"guideline_version":payload.guideline_version}); db.commit(); db.refresh(gold)
    return {"id":gold.id,"sample_id":gold.sample_id,"task":gold.task,"label":gold.label,"verified_by":gold.verified_by,"guideline_version":gold.guideline_version,"created_at":gold.created_at.isoformat()}

@app.get("/api/datasets/{dataset_id}/gold-labels")
def list_gold_labels(dataset_id:int,db:Session=Depends(get_db)):
    if not db.get(Dataset,dataset_id): raise HTTPException(404,"Dataset not found")
    rows=db.query(GoldLabel).join(Sample).filter(Sample.dataset_id==dataset_id).order_by(GoldLabel.created_at).all()
    return [{"id":g.id,"sample_id":g.sample_id,"task":g.task,"label":g.label,"verified_by":g.verified_by,"guideline_version":g.guideline_version} for g in rows]

@app.post("/api/datasets/{dataset_id}/evaluate-gold")
def evaluate_against_gold(dataset_id:int,payload:GoldEvaluationRequest,db:Session=Depends(get_db)):
    dataset=db.query(Dataset).options(joinedload(Dataset.samples).joinedload(Sample.annotations)).filter(Dataset.id==dataset_id).first()
    if not dataset: raise HTTPException(404,"Dataset not found")
    gold_rows=db.query(GoldLabel).join(Sample).filter(Sample.dataset_id==dataset_id,GoldLabel.task==payload.task).all()
    gold_by_sample={g.sample_id:g for g in gold_rows}; truth=[]; predictions=[]; excluded=[]
    for sample in dataset.samples:
        gold=gold_by_sample.get(sample.id)
        approved=next((a for a in sample.annotations if a.status=="APPROVED"),None)
        if not gold: excluded.append({"sample_id":sample.id,"reason":"missing_gold_label"}); continue
        if not approved: excluded.append({"sample_id":sample.id,"reason":"missing_approved_annotation"}); continue
        truth_value=gold.label.get(payload.label_key); prediction=approved.label.get(payload.label_key)
        if truth_value is None or prediction is None: excluded.append({"sample_id":sample.id,"reason":"label_key_missing"}); continue
        truth.append(str(truth_value)); predictions.append(str(prediction))
    if not truth: raise HTTPException(409,"No samples have both a verified gold label and an approved annotation for the selected label key")
    try: metrics=classification_metrics(truth,predictions)
    except ValueError as exc: raise HTTPException(422,str(exc))
    result={**metrics,"excluded_samples":excluded,"gold_label_count":len(gold_rows),"guideline_versions":sorted({g.guideline_version for g in gold_rows}),"interpretation":"Measured against explicitly verified gold labels. Results are only representative if the gold sample is representative and independently annotated."}
    run=EvaluationRun(dataset_id=dataset_id,evaluation_type="gold_classification",reference_version=payload.reference_version,parameters={"task":payload.task,"label_key":payload.label_key,"gold_label_ids":[g.id for g in gold_rows]},result=result)
    db.add(run); db.flush(); _audit(db,"evaluation_run",run.id,"gold_evaluation_completed",{"n":len(truth),"reference_version":payload.reference_version}); db.commit()
    return {"run_id":run.id,"dataset_id":dataset_id,"created_at":run.created_at.isoformat(),"result":result}

@app.get("/api/datasets/{dataset_id}/evaluation-runs")
def list_evaluation_runs(dataset_id:int,db:Session=Depends(get_db)):
    if not db.get(Dataset,dataset_id): raise HTTPException(404,"Dataset not found")
    return [{"id":r.id,"evaluation_type":r.evaluation_type,"reference_version":r.reference_version,"parameters":r.parameters,"result":r.result,"created_at":r.created_at.isoformat()} for r in db.query(EvaluationRun).filter_by(dataset_id=dataset_id).order_by(EvaluationRun.created_at.desc()).all()]

@app.post("/api/evaluation/classification")
def evaluate_classification(payload:EvaluationRequest):
    try: return classification_metrics(payload.y_true,payload.y_pred)
    except ValueError as exc: raise HTTPException(422,str(exc))

@app.post("/api/evaluation/calibration")
def evaluate_calibration(payload:CalibrationRequest):
    try: return expected_calibration_error(payload.confidences,payload.correct,payload.bins)
    except ValueError as exc: raise HTTPException(422,str(exc))

@app.post("/api/evaluation/cohen-kappa")
def evaluate_kappa(payload:AgreementRequest):
    try: return cohen_kappa(payload.rater_a,payload.rater_b)
    except ValueError as exc: raise HTTPException(422,str(exc))

@app.post("/api/evaluation/krippendorff-alpha")
def evaluate_alpha(payload:MultiRaterRequest):
    try: return krippendorff_alpha_nominal(payload.ratings)
    except ValueError as exc: raise HTTPException(422,str(exc))

@app.post("/api/evaluation/subgroup-audit")
def evaluate_subgroups(payload:BiasAuditRequest):
    try: return subgroup_audit(payload.labels,payload.outcomes,payload.groups)
    except ValueError as exc: raise HTTPException(422,str(exc))

@app.post("/api/datasets/{dataset_id}/clone")
def clone_dataset(dataset_id:int,db:Session=Depends(get_db)):
    source=db.get(Dataset,dataset_id)
    if not source: raise HTTPException(404,"Dataset not found")
    clone=Dataset(name=f"{source.name} — working copy",description=source.description,modality=source.modality,task=source.task,schema_json=source.schema_json)
    db.add(clone); db.flush()
    copied=0
    for sample in source.samples:
        new=Sample(dataset_id=clone.id,filename=sample.filename,content_type=sample.content_type,storage_path=sample.storage_path,size_bytes=sample.size_bytes,sha256=sample.sha256,extracted_text=sample.extracted_text,metadata_json=sample.metadata_json)
        db.add(new); db.flush()
        for ann in sample.annotations:
            db.add(Annotation(sample_id=new.id,status="REVIEW_REQUIRED",label=ann.label,original_label=ann.original_label,provider=ann.provider,provider_version=ann.provider_version,confidence=ann.confidence,evidence=ann.evidence))
        for gold in db.query(GoldLabel).filter_by(sample_id=sample.id).all():
            db.add(GoldLabel(sample_id=new.id,task=gold.task,label=gold.label,verified_by=gold.verified_by,guideline_version=gold.guideline_version))
        copied+=1
    _audit(db,"dataset",clone.id,"cloned",{"source_dataset_id":source.id,"samples":copied}); db.commit(); db.refresh(clone)
    return {"dataset":_dataset_dict(clone),"source_dataset_id":source.id,"copied_samples":copied,"note":"Annotations are reset to REVIEW_REQUIRED; source release remains immutable."}

@app.get("/api/datasets/{dataset_id}/releases")
def releases(dataset_id:int,db:Session=Depends(get_db)):
    if not db.get(Dataset,dataset_id): raise HTTPException(404,"Dataset not found")
    return [{"id":r.id,"version":r.version,"created_at":r.created_at.isoformat(),"manifest":r.manifest,"quality_report":r.quality_report,"content_hash":r.content_hash} for r in db.query(DatasetRelease).filter_by(dataset_id=dataset_id).order_by(DatasetRelease.version.desc()).all()]

@app.post("/api/datasets/{dataset_id}/releases")
def create_release(dataset_id:int,db:Session=Depends(get_db)):
    d=db.query(Dataset).options(joinedload(Dataset.samples).joinedload(Sample.annotations)).filter(Dataset.id==dataset_id).first()
    if not d: raise HTTPException(404,"Dataset not found")
    q=report(d)
    if q["missing_annotations"] or q["status_counts"].get("REVIEW_REQUIRED",0) or q["status_counts"].get("REJECTED",0) or q.get("structural_validation_failed_count",0): raise HTTPException(409,"Release blocked: annotate every sample, resolve review decisions, and correct structural validation failures first.")
    version=(db.query(DatasetRelease).filter_by(dataset_id=d.id).count()+1)
    manifest={"schema_version":"1.0","dataset_id":d.id,"name":d.name,"modality":d.modality,"task":d.task,"version":version,"created_at":now().isoformat(),"samples":[{"id":s.id,"filename":s.filename,"sha256":s.sha256,"size_bytes":s.size_bytes,"annotations":[{"id":a.id,"status":a.status,"label":a.label,"original_label":a.original_label,"provider":a.provider,"provider_version":a.provider_version,"reported_confidence":a.confidence,"evidence":a.evidence,"reviewed_by":a.reviewed_by,"reviewed_at":a.reviewed_at.isoformat() if a.reviewed_at else None} for a in s.annotations],"gold_labels":[{"task":g.task,"label":g.label,"verified_by":g.verified_by,"guideline_version":g.guideline_version} for g in db.query(GoldLabel).filter_by(sample_id=s.id).all()]} for s in d.samples]}
    content_hash=hashlib.sha256(json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    r=DatasetRelease(dataset_id=d.id,version=version,manifest=manifest,quality_report=q,content_hash=content_hash); db.add(r); db.flush(); _audit(db,"release",r.id,"created",{"version":version,"content_hash":content_hash}); db.commit(); db.refresh(r)
    return {"id":r.id,"version":version,"manifest":manifest,"quality_report":q,"content_hash":content_hash}

@app.get("/api/datasets/{dataset_id}/export/{fmt}")
def export_dataset(dataset_id:int,fmt:str,db:Session=Depends(get_db)):
    d=db.query(Dataset).options(joinedload(Dataset.samples).joinedload(Sample.annotations)).filter(Dataset.id==dataset_id).first()
    if not d: raise HTTPException(404,"Dataset not found")
    if fmt not in ("jsonl","csv","manifest","coco","yolo","sentinelml"): raise HTTPException(400,"Supported formats: jsonl, csv, manifest, coco, yolo, sentinelml")
    if fmt in ("coco","yolo") and d.modality!="image": raise HTTPException(400,f"{fmt.upper()} export is only available for image datasets")
    records=[]
    for sample in d.samples:
        annotation=next((x for x in sample.annotations if x.status=="APPROVED"),None)
        records.append({"sample_id":sample.id,"filename":sample.filename,"modality":d.modality,"sha256":sample.sha256,"label":annotation.label if annotation else None,"annotation_status":annotation.status if annotation else "UNANNOTATED","provider":annotation.provider if annotation else None,"evidence":annotation.evidence if annotation else None,"storage_path":sample.storage_path})
    if fmt=="sentinelml":
        release=db.query(DatasetRelease).filter_by(dataset_id=d.id).order_by(DatasetRelease.version.desc()).first()
        if not release: raise HTTPException(409,"Create a validated immutable release before exporting the SentinelML handoff bundle")
        path=EXPORT_DIR/f"theo_dataset_{d.id}_sentinelml_v{release.version}.zip"
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json",json.dumps({"contract":"theo.sentinelml.dataset.v1","release_id":release.id,"release_version":release.version,"release_hash":release.content_hash,"dataset":release.manifest.get("name"),"modality":d.modality,"task":d.task,"quality_report":release.quality_report},indent=2,ensure_ascii=False))
            lines=[]
            for rec in records:
                if rec["annotation_status"]!="APPROVED": continue
                lines.append(json.dumps({k:v for k,v in rec.items() if k!="storage_path"},ensure_ascii=False))
                source=Path(rec["storage_path"])
                if source.exists(): archive.write(source,f"assets/{rec['sample_id']}_{Path(rec['filename']).name}")
            archive.writestr("records.jsonl","\n".join(lines))
            archive.writestr("quality_report.json",json.dumps(release.quality_report,indent=2,ensure_ascii=False))
        return FileResponse(path,filename=path.name,media_type="application/zip")
    if fmt=="coco":
        images=[]; annotations=[]; categories={}; ann_id=1
        for rec in records:
            label=rec["label"] or {}; img=label.get("image",{}); image_id=rec["sample_id"]
            images.append({"id":image_id,"file_name":rec["filename"],"width":img.get("width"),"height":img.get("height")})
            for det in label.get("detections",[]):
                name=str(det.get("label",det.get("class_id","unknown"))); cat_id=int(det.get("class_id",len(categories)+1)); categories[cat_id]={"id":cat_id,"name":name}
                x1,y1,x2,y2=det.get("xyxy",[0,0,0,0]); bbox=[x1,y1,max(0,x2-x1),max(0,y2-y1)]
                annotations.append({"id":ann_id,"image_id":image_id,"category_id":cat_id,"bbox":bbox,"area":bbox[2]*bbox[3],"iscrowd":0,"score":det.get("confidence")}); ann_id+=1
        payload={"info":{"description":d.name,"version":"1.0","source":"THEO approved annotations"},"images":images,"annotations":annotations,"categories":[categories[k] for k in sorted(categories)]}
        content=json.dumps(payload,indent=2,ensure_ascii=False); suffix="json"; media="application/json"
    elif fmt=="yolo":
        path=EXPORT_DIR/f"theo_dataset_{d.id}_yolo.zip"; class_names=set()
        for rec in records:
            for det in (rec["label"] or {}).get("detections",[]): class_names.add(str(det.get("label",det.get("class_id","unknown"))))
        names=sorted(class_names); class_ids={name:i for i,name in enumerate(names)}
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("dataset.yaml",f"path: .\ntrain: images\nval: images\nnames: {json.dumps(names,ensure_ascii=False)}\n")
            for rec in records:
                source=Path(rec["storage_path"]); stem=f"{rec['sample_id']}_{Path(rec['filename']).stem}"; image_name=f"images/{stem}{source.suffix.lower()}"
                if source.exists(): archive.write(source,image_name)
                label_data=rec["label"] or {}; meta=label_data.get("image",{}); width=meta.get("width") or 0; height=meta.get("height") or 0; lines=[]
                if width and height:
                    for det in label_data.get("detections",[]):
                        x1,y1,x2,y2=det.get("xyxy",[0,0,0,0]); xc=((x1+x2)/2)/width; yc=((y1+y2)/2)/height; bw=(x2-x1)/width; bh=(y2-y1)/height
                        lines.append(f"{class_ids[str(det.get('label',det.get('class_id','unknown')))]} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
                archive.writestr(f"labels/{stem}.txt","\n".join(lines))
        return FileResponse(path,filename=path.name,media_type="application/zip")
    elif fmt=="jsonl": content="\n".join(json.dumps({k:v for k,v in r.items() if k!="storage_path"},ensure_ascii=False) for r in records); suffix="jsonl"; media="application/x-ndjson"
    elif fmt=="csv":
        out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=["sample_id","filename","modality","sha256","label","annotation_status","provider"]); writer.writeheader()
        for rec in records: writer.writerow({**{k:v for k,v in rec.items() if k!="storage_path"},"label":json.dumps(rec["label"],ensure_ascii=False) if rec["label"] is not None else ""})
        content=out.getvalue(); suffix="csv"; media="text/csv"
    else: content=json.dumps({"schema_version":"1.0","dataset":{"id":d.id,"name":d.name,"modality":d.modality},"records":[{k:v for k,v in r.items() if k!="storage_path"} for r in records]},indent=2,ensure_ascii=False); suffix="json"; media="application/json"
    path=EXPORT_DIR/f"theo_dataset_{d.id}_{fmt}.{suffix}"; path.write_text(content,encoding="utf-8")
    return FileResponse(path,filename=path.name,media_type=media)

@app.get("/api/audit")
def audit(limit:int=Query(200,ge=1,le=1000),db:Session=Depends(get_db)):
    return [{"id":e.id,"entity_type":e.entity_type,"entity_id":e.entity_id,"action":e.action,"actor":e.actor,"detail":e.detail,"created_at":e.created_at.isoformat()} for e in db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit).all()]

def _audit(db,typ,eid,action,detail): db.add(AuditEvent(entity_type=typ,entity_id=eid,action=action,detail=detail))
def _sample_dict(s): return {"id":s.id,"filename":s.filename,"content_type":s.content_type,"size_bytes":s.size_bytes,"sha256":s.sha256,"created_at":s.created_at.isoformat()}
def _annotation_dict(a): return {"id":a.id,"sample_id":a.sample_id,"filename":a.sample.filename,"dataset_id":a.sample.dataset_id,"dataset_name":a.sample.dataset.name,"modality":a.sample.dataset.modality,"status":a.status,"label":a.label,"original_label":a.original_label,"provider":a.provider,"provider_version":a.provider_version,"confidence":a.confidence,"evidence":a.evidence,"reviewer_note":a.reviewer_note,"reviewed_by":a.reviewed_by,"reviewed_at":a.reviewed_at.isoformat() if a.reviewed_at else None,"created_at":a.created_at.isoformat()}
def _dataset_dict(d,include_samples=False):
    result={"id":d.id,"name":d.name,"description":d.description,"modality":d.modality,"task":d.task,"schema_json":d.schema_json,"sample_count":len(d.samples),"created_at":d.created_at.isoformat(),"updated_at":d.updated_at.isoformat()}
    if include_samples:result["samples"]=[{**_sample_dict(s),"annotations":[_annotation_dict(a) for a in s.annotations]} for s in d.samples]
    return result
def _job_dict(j):return {"id":j.id,"dataset_id":j.dataset_id,"kind":j.kind,"status":j.status,"progress":j.progress,"total":j.total,"result":j.result,"error":j.error,"created_at":j.created_at.isoformat(),"started_at":j.started_at.isoformat() if j.started_at else None,"finished_at":j.finished_at.isoformat() if j.finished_at else None}

frontend=ROOT/"frontend"
if frontend.exists(): app.mount("/",StaticFiles(directory=frontend,html=True),name="frontend")
