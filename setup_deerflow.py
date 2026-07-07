import requests

response = requests.post(
    "http://localhost:8080/api/v1/auth/initialize",
    json={"username": "admin", "password": "aos123456", "email": "admin@aos.com"}
)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
