import pytest
import time
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_async_scan_flow(client):
    """Test the full async scan flow: start -> poll -> result"""
    
    # 1. Start Scan
    response = client.get('/api/scan/async?sports=upcoming&min_roi=0.1')
    assert response.status_code == 200
    data = response.get_json()
    assert 'job_id' in data
    job_id = data['job_id']
    
    # 2. Poll Status
    max_retries = 30
    for _ in range(max_retries):
        status_response = client.get(f'/api/scan/status/{job_id}')
        assert status_response.status_code == 200
        status_data = status_response.get_json()
        
        status = status_data.get('status')
        assert status in ['running', 'done', 'error']
        
        if status == 'done':
            # Verify results
            result = status_data.get('result')
            assert result is not None
            assert 'opportunities' in result
            assert 'api_usage' in result
            break
        
        print(f"Polling attempt {_+1}: status={status}, error={status_data.get('error')}")
        time.sleep(1)
    else:
        print(f"Final Status Data: {status_data}")
        pytest.fail("Async scan timed out")
