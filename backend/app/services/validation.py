"""Structural validation for annotation payloads; it never claims semantic correctness."""
from __future__ import annotations
import math
from typing import Any


def validate_annotation(sample, label: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    errors=[]; checks=[]; modality=sample.dataset.modality
    if schema:
        try:
            from jsonschema import Draft202012Validator
            Draft202012Validator.check_schema(schema)
            validator=Draft202012Validator(schema)
            errors.extend(f"JSON Schema: {e.message}" for e in validator.iter_errors(label))
            checks.append({"name":"json_schema","passed":not errors,"schema_draft":"2020-12"})
        except Exception as exc:
            errors.append(f"Invalid or unavailable JSON Schema: {str(exc)[:200]}")
            checks.append({"name":"json_schema","passed":False})
    if modality=="image":
        image=label.get("image",{}); width=image.get("width"); height=image.get("height")
        for i,det in enumerate(label.get("detections",[])):
            box=det.get("xyxy")
            valid=isinstance(box,list) and len(box)==4 and all(_finite(v) for v in box)
            if valid and width and height:
                x1,y1,x2,y2=box; valid=0<=x1<=x2<=width and 0<=y1<=y2<=height
            if not valid: errors.append(f"Detection {i} has invalid xyxy coordinates or lies outside image bounds")
        checks.append({"name":"image_detection_geometry","passed":not any(x.startswith("Detection ") for x in errors)})
    elif modality=="text":
        text=sample.extracted_text or ""
        for i,entity in enumerate(label.get("model_predictions",{}).get("entities",[])):
            start,end=entity.get("start"),entity.get("end")
            if not isinstance(start,int) or not isinstance(end,int) or start<0 or end<start or end>len(text): errors.append(f"Entity {i} has invalid character offsets")
        checks.append({"name":"text_span_offsets","passed":not any(x.startswith("Entity ") for x in errors)})
    elif modality=="document":
        pages=label.get("pages",[]); total=label.get("metadata",{}).get("page_count")
        for page in pages:
            number=page.get("page")
            if not isinstance(number,int) or number<1 or (total and number>total): errors.append("Document contains an invalid page reference")
        checks.append({"name":"document_page_references","passed":not errors})
    elif modality=="audio":
        for i,segment in enumerate(label.get("transcript_segments") or []):
            if not _finite(segment.get("start")) or not _finite(segment.get("end")) or segment["start"]<0 or segment["end"]<segment["start"]: errors.append(f"Audio segment {i} has invalid timestamps")
        checks.append({"name":"audio_timestamps","passed":not any(x.startswith("Audio segment ") for x in errors)})
    elif modality=="video":
        meta=label.get("metadata",{}); width=meta.get("width"); height=meta.get("height")
        for i,obj in enumerate(label.get("tracked_objects",[])):
            box=obj.get("xyxy")
            valid=isinstance(box,list) and len(box)==4 and all(_finite(v) for v in box)
            if valid and width and height:
                x1,y1,x2,y2=box; valid=0<=x1<=x2<=width and 0<=y1<=y2<=height
            if not valid: errors.append(f"Video track detection {i} has invalid box geometry")
        checks.append({"name":"video_detection_geometry","passed":not any(x.startswith("Video track") for x in errors)})
    return {"passed":not errors,"checks":checks,"errors":errors,"scope":"Structural validation only; does not establish semantic correctness."}


def _finite(value):
    try: return math.isfinite(float(value))
    except (TypeError,ValueError): return False
