from collections import Counter

def report(dataset):
    samples=dataset.samples
    annotations=[a for s in samples for a in s.annotations]
    statuses=Counter(a.status for a in annotations)
    duplicates=len(samples)-len({s.sha256 for s in samples})
    reviewed=[a for a in annotations if a.status in ("APPROVED","REJECTED")]
    corrected=sum(1 for a in reviewed if a.original_label != a.label)
    evidence_present=sum(1 for a in annotations if a.evidence)
    validations=[a.evidence.get("structural_validation") for a in annotations if isinstance(a.evidence,dict) and a.evidence.get("structural_validation")]
    validation_passed=sum(1 for v in validations if v.get("passed"))
    warnings=[
        "Provider confidence is not accuracy and may not be calibrated.",
        "No independently verified gold set is configured; semantic accuracy cannot be estimated.",
        "Automated metadata and lexical checks do not establish semantic correctness.",
        "Bias and subgroup fairness are not inferred or certified by this report.",
    ]
    if validations and validation_passed<len(validations): warnings.append(f"{len(validations)-validation_passed} annotation(s) failed structural validation and need correction.")
    if duplicates:warnings.append(f"{duplicates} duplicate file(s) detected by SHA-256 within this dataset.")
    if len(samples)!=len(annotations):warnings.append(f"{len(samples)-len(annotations)} sample(s) have no annotation proposal.")
    if statuses.get("REVIEW_REQUIRED",0):warnings.append(f"{statuses['REVIEW_REQUIRED']} annotation(s) still require human review.")
    ready=bool(samples) and len(samples)==len(annotations) and not statuses.get("REVIEW_REQUIRED",0) and all(a.status in ("APPROVED","REJECTED") for a in annotations)
    return {
        "dataset_id":dataset.id,"sample_count":len(samples),"annotation_count":len(annotations),
        "status_counts":dict(statuses),"review_coverage":round(len(reviewed)/len(annotations),3) if annotations else 0,
        "evidence_coverage":round(evidence_present/len(annotations),3) if annotations else 0,
        "structural_validation_coverage":round(len(validations)/len(annotations),3) if annotations else 0,
        "structural_validation_pass_rate":round(validation_passed/len(validations),3) if validations else None,
        "structural_validation_failed_count":len(validations)-validation_passed,
        "human_correction_rate":round(corrected/len(reviewed),3) if reviewed else None,
        "duplicate_files":duplicates,"missing_annotations":max(0,len(samples)-len(annotations)),
        "warnings":warnings,"readiness":"ready_for_release" if ready else "review_required"
    }
