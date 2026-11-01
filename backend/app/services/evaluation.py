"""Task-agnostic evaluation utilities. Metrics are reported separately, never collapsed into a magic score."""
from __future__ import annotations
from collections import Counter
from typing import Any


def classification_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("y_true and y_pred must have the same non-zero length")
    labels = sorted(set(y_true) | set(y_pred))
    per_class = {}
    for label in labels:
        tp=sum(a==label and b==label for a,b in zip(y_true,y_pred))
        fp=sum(a!=label and b==label for a,b in zip(y_true,y_pred))
        fn=sum(a==label and b!=label for a,b in zip(y_true,y_pred))
        precision=tp/(tp+fp) if tp+fp else 0.0
        recall=tp/(tp+fn) if tp+fn else 0.0
        per_class[label]={"precision":precision,"recall":recall,"f1":2*precision*recall/(precision+recall) if precision+recall else 0.0,"support":sum(x==label for x in y_true)}
    accuracy=sum(a==b for a,b in zip(y_true,y_pred))/len(y_true)
    macro_f1=sum(v['f1'] for v in per_class.values())/len(per_class)
    return {"n":len(y_true),"accuracy":accuracy,"macro_f1":macro_f1,"per_class":per_class,"confusion_matrix":{a:{b:sum(x==a and y==b for x,y in zip(y_true,y_pred)) for b in labels} for a in labels}}


def expected_calibration_error(confidences: list[float], correct: list[bool], bins: int=10) -> dict[str, Any]:
    if len(confidences)!=len(correct) or not confidences: raise ValueError("confidence and correctness arrays must have same non-zero length")
    if bins<2 or bins>100: raise ValueError("bins must be between 2 and 100")
    if any(not 0<=float(c)<=1 for c in confidences): raise ValueError("confidence values must be between 0 and 1")
    rows=[]; ece=0.0
    for i in range(bins):
        lo=i/bins; hi=(i+1)/bins
        idx=[j for j,c in enumerate(confidences) if lo<=c<(hi if i<bins-1 else hi+1e-12)]
        if not idx: continue
        conf=sum(confidences[j] for j in idx)/len(idx); acc=sum(bool(correct[j]) for j in idx)/len(idx)
        ece += len(idx)/len(confidences)*abs(acc-conf)
        rows.append({"lower":lo,"upper":hi,"count":len(idx),"mean_confidence":conf,"observed_accuracy":acc})
    return {"expected_calibration_error":ece,"bins":rows,"n":len(confidences),"interpretation":"Lower ECE indicates closer agreement between reported confidence and observed correctness; it does not establish model accuracy."}


def cohen_kappa(rater_a: list[str|None], rater_b: list[str|None]) -> dict[str, Any]:
    pairs=[(a,b) for a,b in zip(rater_a,rater_b) if a is not None and b is not None]
    if len(rater_a)!=len(rater_b) or not pairs: raise ValueError("Raters must have equal lengths and at least one complete paired label")
    n=len(pairs); observed=sum(a==b for a,b in pairs)/n
    ca=Counter(a for a,_ in pairs); cb=Counter(b for _,b in pairs); labels=set(ca)|set(cb)
    expected=sum(ca[l]*cb[l] for l in labels)/(n*n)
    k=(observed-expected)/(1-expected) if expected<1 else (1.0 if observed==1 else 0.0)
    return {"cohen_kappa":k,"observed_agreement":observed,"expected_agreement":expected,"n":n,"missing_pairs":len(rater_a)-n}


def krippendorff_alpha_nominal(matrix: list[list[str|None]]) -> dict[str, Any]:
    units=[[v for v in row if v is not None] for row in matrix]
    units=[u for u in units if len(u)>=2]
    if not units: raise ValueError("At least one unit needs two or more ratings")
    counts=Counter(v for unit in units for v in unit); total=sum(counts.values())
    observed_num=0; observed_den=0
    for unit in units:
        n=len(unit); c=Counter(unit)
        observed_num += sum(v*(n-v) for v in c.values())/(n-1)
        observed_den += n
    Do=observed_num/observed_den
    De=(total*total-sum(v*v for v in counts.values()))/(total*(total-1)) if total>1 else 0
    alpha=1-Do/De if De else 1.0
    return {"krippendorff_alpha_nominal":alpha,"observed_disagreement":Do,"expected_disagreement":De,"units":len(units),"ratings":total}


def subgroup_audit(labels: list[str], outcomes: list[bool], groups: list[str]) -> dict[str, Any]:
    """Descriptive parity audit on explicitly supplied, consented group labels; no sensitive inference."""
    if not (len(labels)==len(outcomes)==len(groups)) or not labels: raise ValueError("labels, outcomes and groups must have same non-zero length")
    result={}
    for group in sorted(set(groups)):
        idx=[i for i,g in enumerate(groups) if g==group]
        positive=sum(bool(outcomes[i]) for i in idx)
        rate=positive/len(idx); z=1.96; n=len(idx); denom=1+z*z/n
        center=(rate+z*z/(2*n))/denom
        margin=z*((rate*(1-rate)/n+z*z/(4*n*n))**0.5)/denom
        result[group]={"n":n,"positive_outcome_rate":rate,"wilson_95_ci":[max(0,center-margin),min(1,center+margin)],"label_distribution":dict(Counter(labels[i] for i in idx))}
    rates=[v['positive_outcome_rate'] for v in result.values()]
    return {"groups":result,"max_rate_difference":max(rates)-min(rates) if rates else 0,"caveat":"Descriptive disparity signal only. Group definitions, sample size, task context, legitimate base rates and uncertainty require expert review; this is not a legal fairness certification."}
