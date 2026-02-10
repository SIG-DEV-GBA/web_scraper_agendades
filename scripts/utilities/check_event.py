"""Test Firecrawl with proxy - different timeouts."""
import requests
import time

# Test with longer timeout
print("Testing Firecrawl with 90s timeout...")
start = time.time()

r = requests.post('https://firecrawl.si-erp.cloud/scrape', json={
    'url': 'https://www.viralagenda.com/es/andalucia/granada',
    'formats': ['html'],
    'timeout': 90000,  # 90 seconds
    'waitFor': 5000,   # Wait 5s for JS to load
}, timeout=120)

elapsed = time.time() - start
print(f"Request took: {elapsed:.2f}s")
print(f"Status: {r.status_code}")

if r.status_code == 200:
    data = r.json()
    content = data.get('content', '')
    print(f"Content length: {len(content)}")
    # Check if we got actual event content
    if 'viral-event' in content:
        print("SUCCESS: Found event cards in content!")
    else:
        print("WARNING: No event cards found")
    print(f"Preview: {content[:500]}")
else:
    print(f"Error: {r.text[:500]}")
