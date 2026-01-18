
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app import app
    print("Successfully imported app")
except Exception as e:
    print(f"Failed to import app: {e}")
    sys.exit(1)

def run_test():
    app.config['TESTING'] = True
    client = app.test_client()
    
    print("Starting scan...")
    response = client.get('/api/scan/async?sports=upcoming&min_roi=0.1')
    print(f"Start response: {response.status_code}")
    data = response.get_json()
    print(f"Start data: {data}")
    
    if 'job_id' not in data:
        print("ERROR: No job_id returned")
        return
        
    job_id = data['job_id']
    print(f"Job ID: {job_id}")
    
    # Poll
    for i in range(10):
        print(f"Polling attempt {i+1}...")
        resp = client.get(f'/api/scan/status/{job_id}')
        status_data = resp.get_json()
        print(f"Status: {status_data}")
        
        if status_data['status'] == 'done':
            print("SUCCESS: Scan complete")
            return
        elif status_data['status'] == 'error':
            print(f"ERROR: Scan failed with {status_data.get('error')}")
            return
            
        time.sleep(1)
            
    print("TIMEOUT: Scan did not complete")

if __name__ == "__main__":
    run_test()
