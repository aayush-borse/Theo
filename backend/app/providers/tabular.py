"""Tabular profiling: schema/type inference, missingness, duplicates and robust outlier flags."""
import csv, math, statistics
from .base import AnnotationProvider, Proposal
class TabularProvider(AnnotationProvider):
    name="tabular-profiler-v2"; supported_modalities=("tabular",)
    def annotate(self,sample,file_path):
        with open(file_path,newline="",encoding="utf-8-sig",errors="replace") as f:
            reader=csv.DictReader(f); rows=list(reader); columns=reader.fieldnames or []
        profile={}; duplicate_rows=len(rows)-len({tuple(sorted(r.items())) for r in rows})
        for col in columns:
            vals=[(r.get(col) or "").strip() for r in rows]; nonempty=[v for v in vals if v!=""]
            nums=[]
            for v in nonempty:
                try:
                    n=float(v)
                    if math.isfinite(n): nums.append(n)
                except ValueError: pass
            numeric=bool(nonempty) and len(nums)/len(nonempty)>=.9
            item={"inferred_type":"numeric" if numeric else "categorical_or_text","count":len(vals),"missing":len(vals)-len(nonempty),"missing_rate":(len(vals)-len(nonempty))/len(vals) if vals else 0,"unique":len(set(nonempty))}
            if numeric:
                item.update({"min":min(nums),"max":max(nums),"mean":statistics.fmean(nums),"median":statistics.median(nums)})
                q1,q3=_quantile(nums,.25),_quantile(nums,.75); iqr=q3-q1
                outliers=[x for x in nums if x<q1-1.5*iqr or x>q3+1.5*iqr] if iqr else []
                item["iqr_outlier_count"]=len(outliers)
            profile[col]=item
        return Proposal({"task":"tabular_quality_profile","rows":len(rows),"columns":columns,"duplicate_rows":duplicate_rows,"profile":profile},None,{"method":"CSV deterministic profiling with IQR flags","warning":"Outliers, missingness and duplicates are review signals, not automatic evidence of invalid data."},provider=self.name)
def _quantile(values,q):
    xs=sorted(values); pos=(len(xs)-1)*q; lo=int(pos); hi=min(lo+1,len(xs)-1); return xs[lo]+(xs[hi]-xs[lo])*(pos-lo)
