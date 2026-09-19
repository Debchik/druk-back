from google import genai
from google.genai import types

with open('out.wav', 'rb') as f:
    audio_bytes = f.read()

client = genai.Client(
    api_key='sk-_TcywwoSwUQnJD8o62qyRw',
    http_options=types.HttpOptions(base_url='https://api.artemox.com')
)
response = client.models.generate_content(
  model='gemini-3.7-flash',
  contents=[
    'Describe this audio clip',
    types.Part.from_bytes(
      data=audio_bytes,
      mime_type='audio/mp3',
    )
  ]
)

print(response.text)