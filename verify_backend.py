import sys
sys.path.insert(0, '.verification-deps')
sys.path.insert(0, 'backend')
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
Base.metadata.create_all(engine)
Session=sessionmaker(bind=engine)
def test_db():
    with Session() as db: yield db
app.dependency_overrides[get_db]=test_db
with TestClient(app) as client:
    assert client.get('/api/health').json()=={'status':'ok'}
    text='Healthcare research supports hospital patient treatment and medical diagnosis. Clinical studies evaluate disease prevention and improve health outcomes through careful data analysis and evidence based decisions.'
    headers={'Origin':'https://aaravanvith-plagiarism-detector.vercel.app'}
    response=client.post('/api/analyze',files={'file':('healthcare.txt',text,'text/plain')},data={'online':'false'},headers=headers)
    assert response.status_code==200,response.text
    assert 'plagiarism_score' in response.json()
    assert response.headers.get('access-control-allow-origin') in ('*', headers['Origin'])
    print('PASS health, healthcare file analysis, CORS')
    def broken_db():
        raise RuntimeError('simulated failure')
        yield
    app.dependency_overrides[get_db]=broken_db
    response=client.post('/api/analyze',files={'file':('healthcare.txt',text,'text/plain')},headers=headers)
    assert response.status_code==500
    assert response.headers.get('access-control-allow-origin') in ('*', headers['Origin'])
    assert 'detail' in response.json()
    print('PASS error response JSON and CORS')

