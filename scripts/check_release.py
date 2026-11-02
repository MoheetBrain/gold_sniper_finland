"""Fast release integrity/privacy check; supplements human review and Gitleaks."""
from pathlib import Path
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]

def check():
    manifest=json.loads((ROOT/'RELEASE_MANIFEST.json').read_text())
    from build_manifest import files
    expected={r['path'] for r in manifest['files']}
    if set(files())!=expected:raise ValueError('Manifest file inventory differs; rebuild after review')
    patterns={
        'personal_path':re.compile('/'+'Users/'+r'[^\s"\']+'),
        'selected_target_identifier':re.compile(r'g[125]k_\d{4,}'),
        'github_token':re.compile('gh' + r'[pousr]_[A-Za-z0-9]{30,}'),
        'private_key':re.compile('-----BEGIN '+r'(?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        'google_key':re.compile('AI' + r'za[0-9A-Za-z_-]{35}'),
    }
    findings=[]
    for row in manifest['files']:
        p=ROOT/row['path'];b=p.read_bytes()
        if hashlib.sha256(b).hexdigest()!=row['sha256']:raise ValueError(f'Hash mismatch: {row["path"]}')
        if b.startswith(b'version https://git-lfs.github.com/spec/'):raise ValueError('Unresolved LFS pointer')
        if p.suffix.lower() in {'.zip','.gpkg','.tif','.ecw','.npz','.pem','.key'}:
            findings.append({'file':row['path'],'category':'unexpected_binary'})
        try:s=b.decode('utf-8')
        except UnicodeDecodeError:continue
        for cat,pat in patterns.items():
            if pat.search(s):findings.append({'file':row['path'],'category':cat})
        if p.suffix=='.md':
            for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)',s):
                if target.startswith(('http:','https:','#','mailto:')):continue
                if not (p.parent/target.split('#')[0]).exists():findings.append({'file':row['path'],'category':'broken_local_link','target':target})
    if findings:raise ValueError(json.dumps(findings,indent=2))
    v=json.loads((ROOT/'data/historical/STEP2_VALIDATION.json').read_text())
    assert v['n_positives']==8 and v['n_eval_cells']==3649
    assert v['capture']['model_xgb_oof']['top5pct']==.125
    assert v['roc_auc']['model_xgb_oof']==.798
    example=json.loads((ROOT/'data/example/summary.json').read_text())
    assert example['grid_cells']==900 and example['positives']==9 and example['all_oof_finite']
    folds=json.loads((ROOT/'data/example/folds.json').read_text())
    seen=[]
    for fold in folds:
        assert not set(fold['train_groups'])&set(fold['test_groups'])
        assert not set(fold['train_indices'])&set(fold['test_indices'])
        seen+=fold['test_indices']
    assert sorted(seen)==list(range(example['evaluation_cells']))
    env=(ROOT/'.env.example').read_text().splitlines()
    assert all(not line.split('=',1)[1].strip() for line in env if '=' in line and not line.startswith('#'))
    for stem in ['pipeline','study_region','feature_layers','historical_performance','monte_carlo','spatial_cv']:
        assert (ROOT/'docs/figures'/f'{stem}.png').exists()
    print(json.dumps({'status':'PASS','files_hashed':len(expected),'privacy_pattern_findings':0,'links':'PASS','fold_coverage':'PASS','historical_aggregate_consistency':'PASS','scope':'current distributable files; not original Git history'},indent=2))

if __name__=='__main__':check()
