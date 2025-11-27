#!/usr/bin/env python3
import os
import sys
import time
import json

try:
    import requests
except ImportError:
    print("   requests library required!")
    print("   Install: pip install requests")
    sys.exit(1)

API_URL = "http://localhost:5030"
API_KEY = "copilot-secret-key-123456789"

def search_and_download(query):
    headers = {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json'
    }
    
    print(f"  Searching: {query}\n")
    
    search_data = {
        'searchText': query,
        'filterResponses': True,
        'searchTimeout': 25000
    }
    
    resp = requests.post(f'{API_URL}/api/v0/searches', headers=headers, json=search_data)
    search_id = resp.json()['id']
    
    print(f"  Searching...", end="", flush=True)
    responses = []
    max_wait = 60
    
    for i in range(max_wait):
        time.sleep(1)
        print(".", end="", flush=True)
        
        status_resp = requests.get(f'{API_URL}/api/v0/searches/{search_id}', headers=headers)
        search_status = status_resp.json()
        
        resp = requests.get(f'{API_URL}/api/v0/searches/{search_id}/responses', headers=headers)
        responses = resp.json()
        
        if search_status.get('state') == 'Completed':
            break
    
    print(" ✓\n")
    
    if not responses:
        print("   No results found")
        print("   Try a different search term")
        return False
    
    print(f"  Got results from {len(responses)} users\n")
    
    def get_sample_rate(file):
        if 'sampleRate' in file:
            return file['sampleRate']
        
        if 'attributes' in file:
            for attr in file['attributes']:
                if attr.get('attributeType') == 1:
                    return attr.get('value', 44100)
        
        if 'bitRate' in file and file['bitRate']:
            bitrate = file['bitRate']
            if bitrate >= 2000:
                return 96000
            elif bitrate >= 1411:
                return 44100
        
        return 44100
    
    def score_quality(files):
        if not files:
            return 0
        sample_rates = [get_sample_rate(f) for f in files]
        avg_rate = sum(sample_rates) / len(sample_rates)
        
        bitrates = [f.get('bitRate', 0) for f in files]
        avg_bitrate = sum(bitrates) / len(bitrates) if bitrates else 0
        
        return avg_rate + (avg_bitrate * 0.01)
    
    candidates = []
    for user_resp in responses:
        files = user_resp['files']
        
        folders = {}
        for f in files:
            folder = '\\'.join(f['filename'].split('\\')[:-1])
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(f)
        
        for folder, folder_files in folders.items():
            if len(folder_files) >= 5:
                flac_files = [f for f in folder_files if f['filename'].lower().endswith('.flac')]
                
                if flac_files:
                    quality_score = score_quality(flac_files)
                    candidates.append({
                        'username': user_resp['username'],
                        'files': flac_files[:20],
                        'has_flac': True,
                        'quality': quality_score
                    })
    
    candidates.sort(key=lambda x: x['quality'], reverse=True)
    
    if len(candidates) > 1:
        print("  Top candidates found:")
        for i, c in enumerate(candidates[:3]):
            khz = c['quality'] / 1000
            print(f"   {i+1}. {c['username']}: {len(c['files'])} files, {khz:.1f}kHz")
        print()
    
    best = candidates[0] if candidates else None
    
    if not best:
        print("✗ No suitable album found")
        return False
    
    total_size = sum(f['size'] for f in best['files']) / (1024*1024)
    quality_khz = best['quality'] / 1000
    
    print(f"  Best match:")
    print(f"   User: {best['username']}")
    print(f"   Files: {len(best['files'])}")
    print(f"   Format: FLAC {quality_khz:.1f}kHz")
    print(f"   Total size: {total_size:.1f} MB\n")
    
    print("  Starting download...")
    
    download_data = [{'filename': f['filename'], 'size': f['size']} for f in best['files']]
    
    try:
        resp = requests.post(
            f'{API_URL}/api/v0/transfers/downloads/{best["username"]}',
            headers=headers,
            json=download_data,
            timeout=30
        )
        
        if resp.status_code in [200, 201, 204]:
            print(f"SUCCESS! {len(best['files'])} files added to download queue!")
            print(f"\nTrack downloads:")
            print(f"   {API_URL}")
            print(f"   ~/slskd/downloads/\n")
            return True
        else:
            print(f"   Download failed: HTTP {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
            return False
            
    except Exception as e:
        print(f"   Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 auto_download.py \"Artist - Album\"")
        print("\nExamples:")
        print("  python3 auto_download.py \"Daft Punk Discovery\"")
        print("  python3 auto_download.py \"Pink Floyd Dark Side of the Moon\"")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    search_and_download(query)
