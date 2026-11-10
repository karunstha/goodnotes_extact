import base64
import requests
import json

# 1. Define your file path
image_path = "output/page-4.png"

# 2. Read and encode the image locally
with open(image_path, "rb") as image_file:
    base64_image = base64.b64encode(image_file.read()).decode('utf-8')

# 3. Construct the complete payload with your prompt and JSON schema
payload = {
    "model": "Ternary-Bonsai-2-27B-PQ2_0",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text", 
                    "text": "Inspect this handwritten GoodNotes page and return only a JSON object. Transcribe its page date if present. For every handwritten task or bullet, include its exact readable wording, whether it is crossed out/completed, a confidence from 0 to 1, and a short note only for ambiguity. Do not create or modify any tasks."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
        }
    ],
    "response_format": {
        "type": "json_schema",
        "json_schema": {
            "name": "goodnotes_extraction",
            "schema": {
                "type": "object",
                "properties": {
                    "page": { "type": "integer" },
                    "date": { "type": ["string", "null"] },
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": { "type": "string" },
                                "completed": { "type": "boolean" },
                                "confidence": { "type": "number" },
                                "notes": { "type": ["string", "null"] }
                            },
                            "required": ["title", "completed", "confidence", "notes"],
                            "additionalProperties": False
                        }
                    },
                    "ambiguous": {
                        "type": "array",
                        "items": { "type": "string" }
                    }
                },
                "required": ["page", "date", "tasks", "ambiguous"],
                "additionalProperties": False
            }
        }
    }
}

# 4. Send it to the llama.cpp server
try:
    print(f"Sending {image_path} to server...")
    response = requests.post(
        "http://100.115.19.104:8090/v1/chat/completions",
        headers={"Content-Type": "application/json"},
        json=payload
    )
    
    response.raise_for_status()
    
    # Extract just the raw JSON text the model generated
    result_text = response.json()['choices'][0]['message']['content']
    
    # Print the cleanly formatted JSON object
    print(json.dumps(json.loads(result_text), indent=2))
    
except Exception as e:
    print(f"Request failed: {e}")
    if 'response' in locals():
        print(f"Server response: {response.text}")