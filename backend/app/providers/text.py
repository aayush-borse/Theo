"""Text pipeline with optional Hugging Face sentiment and NER models."""
import os, re
from functools import lru_cache
from .base import AnnotationProvider, Proposal

@lru_cache(maxsize=8)
def _transformer_pipeline(task, model, aggregation=None):
    from transformers import pipeline
    kwargs={}
    if aggregation: kwargs["aggregation_strategy"]=aggregation
    return pipeline(task,model=model,**kwargs)

class TextProvider(AnnotationProvider):
    name="text-pipeline-v2"; supported_modalities=("text",)
    def annotate(self,sample,file_path):
        text=sample.extracted_text or file_path.read_text(encoding="utf-8",errors="replace")
        tasks={"characters":len(text),"tokens":len(re.findall(r"\b\w+\b",text)),"email_patterns":len(re.findall(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",text)),"url_patterns":len(re.findall(r"https?://[^\s]+",text))}
        positive={"good","great","excellent","love","useful","happy","reliable","fast","clear","helpful","amazing"}; negative={"bad","poor","terrible","hate","broken","slow","awful","unreliable","confusing","useless","worst"}
        words=set(re.findall(r"[\w'-]+",text.lower())); pos=sorted(words & positive); neg=sorted(words & negative)
        lexical_sentiment="positive" if len(pos)>len(neg) else "negative" if len(neg)>len(pos) else "neutral_or_uncertain"
        tasks["lexical_sentiment_hint"]=lexical_sentiment
        sentiment_model=os.getenv("THEO_SENTIMENT_MODEL",""); ner_model=os.getenv("THEO_NER_MODEL","")
        predictions={}; evidence={"method":"text normalization, regex inventory and transparent lexicon hint","matched_lexicon_terms":{"positive":pos,"negative":neg},"limitations":["Lexical sentiment is not semantic ground truth; negation, sarcasm, context and multilingual text are not modelled."]}
        if sentiment_model:
            try:
                out=_transformer_pipeline("sentiment-analysis",sentiment_model)(text[:10000],truncation=True)[0]
                predictions["sentiment"]={"label":out["label"],"reported_score":float(out["score"])}
                evidence["sentiment_model"]=sentiment_model
            except Exception as exc: evidence["limitations"].append(f"Sentiment model unavailable: {str(exc)[:200]}")
        if ner_model:
            try:
                entities=_transformer_pipeline("token-classification",ner_model,"simple")(text[:10000])
                predictions["entities"]=[{"text":e["word"],"label":e["entity_group"],"score":float(e["score"]),"start":e["start"],"end":e["end"]} for e in entities]
                evidence["ner_model"]=ner_model
            except Exception as exc: evidence["limitations"].append(f"NER model unavailable: {str(exc)[:200]}")
        if not predictions:
            evidence["limitations"].append("No pretrained NLP model configured. Configure THEO_SENTIMENT_MODEL and/or THEO_NER_MODEL; lexical patterns are not semantic annotation.")
        return Proposal({"task":"text_analysis","sentiment":lexical_sentiment,"inventory":tasks,"model_predictions":predictions},None,evidence,provider="huggingface-text" if predictions else self.name)
