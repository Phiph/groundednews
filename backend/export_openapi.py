"""
Print the API's OpenAPI schema as JSON. The frontend generates its types from it:
`npm run gen:api` in frontend/ (writes frontend/lib/api-schema.ts).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=1))
