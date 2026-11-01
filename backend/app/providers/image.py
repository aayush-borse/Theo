"""Image inspection plus optional real YOLO detection and SAM segmentation adapters."""
import os
from functools import lru_cache
from PIL import Image, UnidentifiedImageError
from .base import AnnotationProvider, Proposal

@lru_cache(maxsize=4)
def _image_classifier(model):
    from transformers import pipeline
    return pipeline("image-classification",model=model)

@lru_cache(maxsize=4)
def _yolo_model(model):
    from ultralytics import YOLO
    return YOLO(model)

class ImageProvider(AnnotationProvider):
    name="image-pipeline-v2"; supported_modalities=("image",)
    def annotate(self, sample, file_path):
        try:
            with Image.open(file_path) as im:
                im.verify()
            with Image.open(file_path) as im:
                metadata={"valid":True,"format":im.format,"width":im.width,"height":im.height,"mode":im.mode,"frames":getattr(im,"n_frames",1)}
        except (UnidentifiedImageError,OSError) as exc:
            return Proposal({"task":"image_validation","valid":False,"error":str(exc)[:300]},None,{"method":"Pillow decoder"},provider=self.name)
        classification={}; cls_model=os.getenv("THEO_IMAGE_CLASSIFIER_MODEL","")
        if cls_model:
            try:
                preds=_image_classifier(cls_model)(str(file_path))
                classification={"model":cls_model,"predictions":[{"label":x["label"],"score":float(x["score"])} for x in preds[:10]]}
            except Exception as exc: classification={"model":cls_model,"error":str(exc)[:240]}
        model=os.getenv("THEO_YOLO_MODEL","")
        if model:
            try:
                result=_yolo_model(model)(str(file_path),verbose=False)[0]
                names=result.names; boxes=[]
                for b in result.boxes:
                    xyxy=[round(float(x),2) for x in b.xyxy[0].tolist()]
                    boxes.append({"class_id":int(b.cls[0]),"label":names[int(b.cls[0])],"confidence":round(float(b.conf[0]),5),"xyxy":xyxy})
                masks=[]
                if result.masks is not None:
                    for mask in result.masks.data:
                        masks.append({"shape":list(mask.shape),"polygon_pixels":result.masks.xy[len(masks)].tolist()[:2000] if len(result.masks.xy)>len(masks) else []})
                return Proposal({"task":"object_detection_and_optional_segmentation","image":metadata,"detections":boxes,"classification":classification,"segmentation_masks":masks},None,{"method":"Ultralytics YOLO inference","model_reference":model,"coordinate_format":"pixel xyxy","warning":"Predictions are proposals, not verified ground truth. Segmentation is only returned when the configured checkpoint supports masks."},provider="ultralytics-yolo")
            except Exception as exc:
                return Proposal({"task":"image_validation","image":metadata,"inference_error":str(exc)[:300]},None,{"method":"Pillow + optional YOLO","warning":"YOLO model configured but inference failed; inspect logs and model compatibility."},provider=self.name)
        return Proposal({"task":"image_analysis","image":metadata,"classification":classification or None},None,{"method":"Pillow validation plus optional Transformers image classification","available_tasks":["object detection via THEO_YOLO_MODEL","segmentation via a YOLO segmentation checkpoint configured as THEO_YOLO_MODEL"],"warning":"No semantic labels are inferred unless a model provider is configured."},provider="transformers-image-classification" if classification else self.name)
