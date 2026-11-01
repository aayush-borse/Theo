"""Audio/video asset pipelines with optional Whisper transcription and sampled-frame detection."""
import os, wave
from functools import lru_cache
from pathlib import Path
from .base import AnnotationProvider, Proposal

@lru_cache(maxsize=4)
def _whisper_model(model,device,compute_type):
    from faster_whisper import WhisperModel
    return WhisperModel(model,device=device,compute_type=compute_type)

@lru_cache(maxsize=4)
def _diarization_pipeline(model,token):
    from pyannote.audio import Pipeline
    return Pipeline.from_pretrained(model,token=token or None)

@lru_cache(maxsize=4)
def _yolo_model(model):
    from ultralytics import YOLO
    return YOLO(model)

class MediaProvider(AnnotationProvider):
    name="media-pipeline-v2"; supported_modalities=("audio","video")
    def annotate(self,sample,file_path:Path):
        modality=sample.dataset.modality
        if modality=="audio": return self._audio(sample,file_path)
        return self._video(sample,file_path)
    def _audio(self,sample,path):
        meta={"filename":sample.filename,"size_bytes":sample.size_bytes,"extension":path.suffix.lower()}; limitations=[]
        try:
            import soundfile as sf
            info=sf.info(str(path)); meta.update({"duration_seconds":info.duration,"sample_rate_hz":info.samplerate,"channels":info.channels,"frames":info.frames,"format":info.format})
        except Exception:
            try:
                with wave.open(str(path),"rb") as f: meta.update({"duration_seconds":f.getnframes()/f.getframerate(),"sample_rate_hz":f.getframerate(),"channels":f.getnchannels()})
            except Exception: limitations.append("Audio stream metadata unavailable; install ffmpeg/libsndfile for broader codec support.")
        transcript=None; model=os.getenv("THEO_WHISPER_MODEL","")
        if model:
            try:
                wm=_whisper_model(model,os.getenv("THEO_WHISPER_DEVICE","cpu"),os.getenv("THEO_WHISPER_COMPUTE_TYPE","int8"))
                segments,info=wm.transcribe(str(path),vad_filter=True)
                transcript=[{"start":round(s.start,3),"end":round(s.end,3),"text":s.text.strip()} for s in segments]
                meta["detected_language"]={"code":info.language,"probability":info.language_probability}
            except Exception as exc: limitations.append(f"Whisper inference failed: {str(exc)[:240]}")
        else: limitations.append("Transcription is disabled until THEO_WHISPER_MODEL is configured and faster-whisper is installed.")
        diarization=None; diar_model=os.getenv("THEO_DIARIZATION_MODEL","")
        if diar_model:
            try:
                pipe=_diarization_pipeline(diar_model,os.getenv("HF_TOKEN",""))
                diar=pipe(str(path)); diarization=[{"start":round(t.start,3),"end":round(t.end,3),"speaker":speaker} for t,_,speaker in diar.itertracks(yield_label=True)]
            except Exception as exc: limitations.append(f"Diarization unavailable: {str(exc)[:240]}")
        return Proposal({"task":"audio_transcription" if transcript is not None else "audio_asset_analysis","metadata":meta,"transcript_segments":transcript,"speaker_segments":diarization},None,{"method":"soundfile/wave metadata, optional faster-whisper and pyannote.audio","limitations":limitations,"diarization_note":"Requires an approved pyannote model, Hugging Face access token where required, and compliance with model terms."},provider="faster-whisper+pyannote" if transcript is not None and diarization is not None else "faster-whisper" if transcript is not None else self.name)
    def _video(self,sample,path):
        try:
            import cv2
            cap=cv2.VideoCapture(str(path))
            if not cap.isOpened(): raise RuntimeError("OpenCV could not open video")
            fps=cap.get(cv2.CAP_PROP_FPS) or 0; count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); duration=count/fps if fps else None
            interval=max(1,int(fps*float(os.getenv("THEO_VIDEO_SAMPLE_SECONDS","2")))) if fps else 1
            frames=[]; index=0
            while len(frames)<int(os.getenv("THEO_VIDEO_MAX_FRAMES","120")):
                ok,frame=cap.read()
                if not ok: break
                if index%interval==0:
                    frames.append({"frame_index":index,"timestamp_seconds":round(index/fps,3) if fps else None,"width":int(frame.shape[1]),"height":int(frame.shape[0])})
                index+=1
            cap.release()
            tracks=[]; tracking_error=None; model=os.getenv("THEO_YOLO_MODEL","")
            if model:
                try:
                    detector=_yolo_model(model); detector.predictor=None; cap=cv2.VideoCapture(str(path)); frame_no=0
                    while len(tracks)<int(os.getenv("THEO_VIDEO_MAX_FRAMES","120")):
                        ok,frame=cap.read()
                        if not ok: break
                        if frame_no%interval==0:
                            result=detector.track(frame,persist=True,verbose=False)[0]
                            for box in result.boxes:
                                tracks.append({"frame_index":frame_no,"timestamp_seconds":round(frame_no/fps,3) if fps else None,"track_id":int(box.id[0]) if box.id is not None else None,"class_id":int(box.cls[0]),"label":result.names[int(box.cls[0])],"confidence":float(box.conf[0]),"xyxy":[round(float(v),2) for v in box.xyxy[0].tolist()]})
                        frame_no+=1
                    cap.release()
                except Exception as exc: tracking_error=str(exc)[:200]
            return Proposal({"task":"video_tracking" if tracks else "video_temporal_sampling","metadata":{"width":w,"height":h,"fps":fps,"frame_count":count,"duration_seconds":duration},"sampled_frames":frames,"tracked_objects":tracks},None,{"method":"OpenCV temporal sampling with optional Ultralytics persistent tracking","tracking_error":tracking_error,"limitations":["Object tracking links detections across frames but does not infer high-level human activities or scene semantics.","Track identity can fragment under occlusion or camera cuts; validate tracks before use."]},provider="ultralytics-video-tracking" if tracks else self.name)
        except Exception as exc:
            return Proposal({"task":"video_asset_analysis","valid":False,"error":str(exc)[:300]},None,{"method":"OpenCV video decoder"},provider=self.name)
