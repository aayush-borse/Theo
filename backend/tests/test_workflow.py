import time

def wait_job(client, job_id):
    for _ in range(100):
        job=client.get(f'/api/jobs/{job_id}').json()
        if job['status'] in ('SUCCEEDED','FAILED'):
            return job
        time.sleep(.02)
    raise AssertionError('annotation job timed out')

def test_health_and_provider_registry(client):
    response=client.get('/api/health')
    assert response.status_code==200
    assert response.json()['service']=='theo'
    assert set(response.json()['providers'])=={'image','text','document','tabular','audio','video'}

def test_end_to_end_text_dataset(client):
    created=client.post('/api/datasets',json={'name':'Review corpus','description':'Small test set','modality':'text','task':'classification'})
    assert created.status_code==200
    dataset_id=created.json()['id']
    uploaded=client.post(f'/api/datasets/{dataset_id}/samples',files=[('files',('review.txt',b'This product is excellent and useful.','text/plain'))])
    assert uploaded.status_code==200 and uploaded.json()['uploaded']==1
    queued=client.post(f'/api/datasets/{dataset_id}/annotate')
    assert queued.status_code==200
    job=wait_job(client,queued.json()['job_id'])
    assert job['status']=='SUCCEEDED' and job['result']['created']==1
    annotations=client.get('/api/annotations?status=REVIEW_REQUIRED').json()
    assert len(annotations)==1
    ann=annotations[0]
    assert ann['label']['sentiment']=='positive'
    blocked=client.post(f'/api/datasets/{dataset_id}/releases')
    assert blocked.status_code==409
    reviewed=client.patch(f"/api/annotations/{ann['id']}",json={'status':'APPROVED','reviewer':'test','note':'checked'})
    assert reviewed.status_code==200 and reviewed.json()['status']=='APPROVED'
    quality=client.get(f'/api/datasets/{dataset_id}/quality').json()
    assert quality['review_coverage']==1.0
    release=client.post(f'/api/datasets/{dataset_id}/releases')
    assert release.status_code==200 and release.json()['version']==1
    exported=client.get(f'/api/datasets/{dataset_id}/export/jsonl')
    assert exported.status_code==200 and 'positive' in exported.text

def test_reject_invalid_modality(client):
    response=client.post('/api/datasets',json={'name':'Bad modality','modality':'alien','task':'x'})
    assert response.status_code==400

def test_modality_file_validation(client):
    dataset=client.post('/api/datasets',json={'name':'CSV metrics','modality':'tabular'}).json()
    bad=client.post(f"/api/datasets/{dataset['id']}/samples",files=[('files',('notes.txt',b'not csv','text/plain'))])
    assert bad.status_code==415
    good=client.post(f"/api/datasets/{dataset['id']}/samples",files=[('files',('metrics.csv',b'name,score\nA,10\nB,12\n','text/csv'))])
    assert good.status_code==200
    queued=client.post(f"/api/datasets/{dataset['id']}/annotate")
    job=wait_job(client,queued.json()['job_id'])
    assert job['status']=='SUCCEEDED'
    annotations=client.get('/api/annotations?status=REVIEW_REQUIRED').json()
    assert any(a['dataset_id']==dataset['id'] and a['label']['rows']==2 for a in annotations)

def test_duplicate_upload_is_skipped(client):
    dataset=client.post('/api/datasets',json={'name':'Duplicates','modality':'text'}).json()
    files=[('files',('same.txt',b'hello','text/plain'))]
    first=client.post(f"/api/datasets/{dataset['id']}/samples",files=files)
    second=client.post(f"/api/datasets/{dataset['id']}/samples",files=files)
    assert first.json()['uploaded']==1
    assert second.json()['uploaded']==0 and second.json()['duplicates_skipped']==1

def test_frontend_is_served(client):
    response=client.get('/')
    assert response.status_code==200
    assert 'THEO' in response.text

def test_release_freezes_dataset_and_clone_is_editable(client):
    created=client.post('/api/datasets',json={'name':'Frozen set','modality':'text','task':'classification'}).json()
    did=created['id']
    client.post(f'/api/datasets/{did}/samples',files=[('files',('a.txt',b'Great useful data','text/plain'))])
    job=client.post(f'/api/datasets/{did}/annotate').json()['job_id']; wait_job(client,job)
    ann=client.get(f'/api/annotations?dataset_id={did}').json()[0]
    client.patch(f"/api/annotations/{ann['id']}",json={'status':'APPROVED','reviewer':'qa'})
    release=client.post(f'/api/datasets/{did}/releases')
    assert release.status_code==200
    import io, zipfile
    handoff=client.get(f'/api/datasets/{did}/export/sentinelml')
    assert handoff.status_code==200
    with zipfile.ZipFile(io.BytesIO(handoff.content)) as archive:
        assert {'manifest.json','records.jsonl','quality_report.json'}.issubset(set(archive.namelist()))
    blocked=client.post(f'/api/datasets/{did}/samples',files=[('files',('b.txt',b'new data','text/plain'))])
    assert blocked.status_code==409
    clone=client.post(f'/api/datasets/{did}/clone')
    assert clone.status_code==200 and clone.json()['copied_samples']==1


def test_evaluation_endpoints(client):
    metrics=client.post('/api/evaluation/classification',json={'y_true':['cat','dog','cat'],'y_pred':['cat','cat','cat']})
    assert metrics.status_code==200 and metrics.json()['accuracy']==2/3
    calibration=client.post('/api/evaluation/calibration',json={'confidences':[.9,.8,.2,.1],'correct':[True,True,False,False]})
    assert calibration.status_code==200 and calibration.json()['expected_calibration_error']<0.16
    agreement=client.post('/api/evaluation/cohen-kappa',json={'rater_a':['a','b','a'],'rater_b':['a','b','b']})
    assert agreement.status_code==200 and 'cohen_kappa' in agreement.json()
    alpha=client.post('/api/evaluation/krippendorff-alpha',json={'ratings':[['a','a','b'],['b','b'],['a','a']]})
    assert alpha.status_code==200 and 'krippendorff_alpha_nominal' in alpha.json()


def test_subgroup_audit_requires_explicit_groups(client):
    result=client.post('/api/evaluation/subgroup-audit',json={'labels':['yes','no','yes','no'],'outcomes':[True,False,True,False],'groups':['group_a','group_a','group_b','group_b']})
    assert result.status_code==200 and result.json()['max_rate_difference']==0


def test_image_export_formats(client):
    from PIL import Image
    import io, zipfile
    buffer=io.BytesIO(); Image.new('RGB',(8,6)).save(buffer,format='PNG')
    created=client.post('/api/datasets',json={'name':'Objects','modality':'image','task':'detection'}).json()
    did=created['id']
    client.post(f'/api/datasets/{did}/samples',files=[('files',('sample.png',buffer.getvalue(),'image/png'))])
    job=client.post(f'/api/datasets/{did}/annotate').json()['job_id']; wait_job(client,job)
    annotation=client.get(f'/api/annotations?dataset_id={did}').json()[0]
    client.patch(f"/api/annotations/{annotation['id']}",json={'status':'APPROVED','reviewer':'qa'})
    coco=client.get(f'/api/datasets/{did}/export/coco')
    assert coco.status_code==200 and coco.json()['images'][0]['width']==8
    yolo=client.get(f'/api/datasets/{did}/export/yolo')
    assert yolo.status_code==200
    with zipfile.ZipFile(io.BytesIO(yolo.content)) as archive:
        assert 'dataset.yaml' in archive.namelist()
        assert any(x.startswith('images/') for x in archive.namelist())


def test_password_hash_and_token_helpers():
    from app.security.passwords import hash_password, verify_password
    from app.security.tokens import issue_token, verify_token
    password='correct-horse-battery-staple'
    encoded=hash_password(password)
    assert verify_password(password,encoded)
    assert not verify_password('wrong-password',encoded)
    token=issue_token('reviewer','reviewer',secret='a'*48)
    claims=verify_token(token,secret='a'*48)
    assert claims['sub']=='reviewer' and claims['role']=='reviewer'


def test_gold_standard_evaluation_is_persisted(client):
    dataset=client.post('/api/datasets',json={'name':'Gold benchmark','modality':'text','task':'classification'}).json()
    did=dataset['id']
    upload=client.post(f'/api/datasets/{did}/samples',files=[('files',('sample.txt',b'This is excellent and useful','text/plain'))])
    sid=upload.json()['samples'][0]['id']
    job=client.post(f'/api/datasets/{did}/annotate').json()['job_id']; wait_job(client,job)
    annotation=client.get(f'/api/annotations?dataset_id={did}').json()[0]
    client.patch(f"/api/annotations/{annotation['id']}",json={'status':'APPROVED','reviewer':'reviewer'})
    gold=client.post(f'/api/datasets/{did}/gold-labels',json={'sample_id':sid,'task':'classification','label':{'sentiment':'positive'},'verified_by':'expert-1','guideline_version':'v1'})
    assert gold.status_code==200
    result=client.post(f'/api/datasets/{did}/evaluate-gold',json={'task':'classification','label_key':'sentiment','reference_version':'gold-v1'})
    assert result.status_code==200 and result.json()['result']['accuracy']==1.0
    runs=client.get(f'/api/datasets/{did}/evaluation-runs')
    assert runs.status_code==200 and len(runs.json())==1


def test_first_admin_bootstrap_and_login(client, monkeypatch):
    from app.security import tokens
    monkeypatch.setattr(tokens,'SECRET','s'*48)
    credentials={'username':'root-admin','password':'correct-horse-battery-staple'}
    created=client.post('/api/auth/register',json=credentials)
    assert created.status_code==200 and created.json()['role']=='admin'
    login=client.post('/api/auth/login',json=credentials)
    assert login.status_code==200
    me=client.get('/api/auth/me',headers={'Authorization':'Bearer '+login.json()['access_token']})
    assert me.status_code==200 and me.json()['role']=='admin'


def test_schema_validation_blocks_approval_until_corrected(client):
    schema={'type':'object','required':['approved_by_policy'],'properties':{'approved_by_policy':{'type':'boolean'}}}
    created=client.post('/api/datasets',json={'name':'Schema gate','modality':'text','task':'classification','schema_json':schema}).json()
    did=created['id']
    client.post(f'/api/datasets/{did}/samples',files=[('files',('sample.txt',b'great and useful','text/plain'))])
    job=client.post(f'/api/datasets/{did}/annotate').json()['job_id']; wait_job(client,job)
    annotation=client.get(f'/api/annotations?dataset_id={did}').json()[0]
    blocked=client.patch(f"/api/annotations/{annotation['id']}",json={'status':'APPROVED','reviewer':'qa'})
    assert blocked.status_code==409
    corrected={**annotation['label'],'approved_by_policy':True}
    approved=client.patch(f"/api/annotations/{annotation['id']}",json={'status':'APPROVED','label':corrected,'reviewer':'qa'})
    assert approved.status_code==200 and approved.json()['evidence']['structural_validation']['passed'] is True


def test_adjudication_requires_independent_disagreement(client):
    dataset=client.post('/api/datasets',json={'name':'Disagreement','modality':'text','task':'classification'}).json()
    did=dataset['id']
    client.post(f'/api/datasets/{did}/samples',files=[('files',('sample.txt',b'great useful','text/plain'))])
    job=client.post(f'/api/datasets/{did}/annotate').json()['job_id']; wait_job(client,job)
    annotation=client.get(f'/api/annotations?dataset_id={did}').json()[0]
    aid=annotation['id']
    client.patch(f'/api/annotations/{aid}',json={'status':'APPROVED','reviewer':'reviewer-a'})
    one=client.post(f'/api/annotations/{aid}/adjudicate',json={'status':'APPROVED','reviewer':'adjudicator'})
    assert one.status_code==409
    client.patch(f'/api/annotations/{aid}',json={'status':'REJECTED','reviewer':'reviewer-b'})
    final=client.post(f'/api/annotations/{aid}/adjudicate',json={'status':'APPROVED','reviewer':'adjudicator','note':'Resolved with reference guideline v1'})
    assert final.status_code==200 and final.json()['annotation']['status']=='APPROVED'
