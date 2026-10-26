import sys, contextlib, io
sys.path.insert(0,'.verification-deps')
sys.path.insert(0,'backend')
import numpy as np
from scipy.sparse import csr_matrix
from app.services.similarity import _tfidf_overlap, analyze_document
from app.main import ReferenceCorpusCache
from app.database import SessionLocal, Report
rng=np.random.default_rng(7)
a=rng.random((8,40)); b=rng.random((12,40))
a[a<0.7]=0; b[b<0.7]=0; a[0]=0
expected=np.minimum(a[:,None,:], b[None,:,:]).sum(axis=2)/np.maximum(a.sum(axis=1)[:,None],1e-15)
np.testing.assert_allclose(_tfidf_overlap(csr_matrix(a),csr_matrix(b)),expected,atol=1e-7)
print('PASS sparse overlap matches original calculation')
with SessionLocal() as db:
    cache=ReferenceCorpusCache(); cache.rebuild(db)
    corpus=cache.static_corpus(db)
    pubmed={k:v for k,v in corpus.items() if k.startswith('pubmed::')}
    assert len(pubmed)==469,len(pubmed)
    print('PASS bundled references loaded:',len(corpus),'total,',len(pubmed),'PubMed')
    with contextlib.redirect_stdout(io.StringIO()):
        result=analyze_document(next(iter(pubmed.values())),corpus)
    assert result.overall_score>=99,result.overall_score
    print('PASS known copied PubMed document:',result.overall_score)
    report=db.query(Report).filter(Report.filename=='SMVD_DPR.pdf').order_by(Report.id.desc()).first()
    if report:
        with contextlib.redirect_stdout(io.StringIO()):
            before=analyze_document(report.text,{k:v for k,v in corpus.items() if not k.startswith('pubmed::')})
            after=analyze_document(report.text,corpus)
        print('Saved SMVD_DPR.pdf extracted text: starter score=',before.overall_score,'full corpus score=',after.overall_score,'sentences=',len(after.sentence_matches),'flagged=',sum(m.flagged for m in after.sentence_matches))
    else:
        print('Original uploaded PDF is not saved in this workspace')
