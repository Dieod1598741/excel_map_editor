from utils.geocoding import GeocodeEngine
import sys

def test_naver_geocoding(client_id, client_secret):
    engine = GeocodeEngine(naver_client_id=client_id, naver_client_secret=client_secret)
    engine.provider = "naver"
    
    test_address = "서울특별실 중구 세종대로 110"
    print(f"Testing Naver geocoding for: {test_address}")
    
    lon, lat, addr = engine.geocode(test_address)
    
    if lon and lat:
        print(f"Success!")
        print(f"Longitude: {lon}")
        print(f"Latitude: {lat}")
        print(f"Refined Address: {addr}")
    else:
        print("Failed to get coordinates from Naver.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_naver.py <client_id> <client_secret>")
    else:
        test_naver_geocoding(sys.argv[1], sys.argv[2])
