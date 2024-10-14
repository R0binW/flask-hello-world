import base64
import openai
import os
import sys
from datetime import datetime, timezone, timedelta
import traceback

import requests
import firebase_utils

from flask import Flask, jsonify
from flask_cors import CORS

#----------------------------------------------------------
from utility.video.background_video_generator import generate_video_urlNoCaptions
from utility.video.video_search_query_generator import getVideoSearchQueriesNoCaptions
#-----------------------------------------------------------

app = Flask(__name__)
CORS(app)

LOCAL_IMAGE = "LOCAL IMAGE"

try:
  openai.api_key = os.environ['OPENAI_API_KEY']
except KeyError:
  sys.stderr.write("""
  ERROR: Check API KEY
  If you don't have an API key yet,
  https://platform.openai.com/signup
  Then, open the Secrets Tool and add OPENAI_API_KEY as a secret.
  """)
  exit(1)
  
@app.route('/generate_memory/<prompt>')
def generate_memory(prompt):
  try:
    # Taking the current time and using it as the docname
    pst_timezone = timezone(timedelta(hours=-8))
    doc_id = datetime.now(pst_timezone).strftime("%m-%d-%Y, %H:%M:%S")

    better_prompt = generate_better_prompt(prompt)
    generate_local_image(prompt)
    uploaded_image_url = firebase_utils.upload_to_storage(doc_id, LOCAL_IMAGE)
    video_url = try_get_video(prompt)
    document_data = {
      "originalPrompt": prompt,
      "gptPrompt": better_prompt,
      "imageURL": uploaded_image_url,
      "videoURL": video_url,
    }

    firebase_utils.set("memories", doc_id)
    return jsonify(document_data)
  except Exception:
    return jsonify(traceback.format_exc())

def generate_better_prompt(prompt):
  system_prompt = '''
  I am going to give you some words. 
  Form an image generation prompt of an environment or scene based on those words 
  that is less than 40 words long. Your response must include those words.'''
  return gpt_act_as(system_prompt, prompt)

def generate_local_image(prompt):
  engine_id = "stable-diffusion-v1-6"
  api_host = os.getenv('API_HOST', 'https://api.stability.ai')
  api_key = os.environ['MyDreamStudioKey']
  response = requests.post(
    f"{api_host}/v1/generation/{engine_id}/text-to-image",
    headers={
      "Content-Type": "application/json",
      "Accept": "application/json",
      "Authorization": f"Bearer {api_key}"
    },
    json={
      "text_prompts": [{
        "text": f"{prompt}",
        "weight": 1
      }, {
        "text":
        "background, realistic, photo-like, photorealistic, panorama, panoramic, 360, fisheye, fisheye lens, wide photo",
        "weight": 1
      }, {
        "text":
        "Comic styled, anime styled, cartoon styled, unrealistic, person in focus, portrait, painting",
        "weight": -0.5
      }, {
        "text":
        "BadDream, badhandv4, BadNegAnatomyV1-neg, easynegative, FastNegativeV2, bad anatomy, extra people, (deformed iris, deformed pupils, mutated hands and fingers:1.4), (deformed, distorted, disfigured:1.3), poorly drawn, bad anatomy, wrong anatomy, extra limb, missing limb, floating limbs, disconnected limbs, mutation, mutated, ugly, disgusting, amputation, signature, watermark, airbrush, photoshop, plastic doll, (ugly eyes, deformed iris, deformed pupils, fused lips and teeth:1.2), text, cropped, out of frame, worst quality, low quality, jpeg artifacts, ugly, duplicate, morbid, mutilated, extra fingers, mutated hands, poorly drawn hands, poorly drawn face, mutation, deformed, blurry, dehydrated, bad anatomy, bad proportions, extra limbs, cloned face, disfigured, gross proportions, malformed limbs, missing arms, missing legs, extra arms, extra legs, fused fingers, too many fingers, long neck, masculine, obese, fat, out of frame, caricature, body horror, mutant, facebook, youtube, food, lowres, text, error, cropped, worst quality, low quality, jpeg artifacts, ugly, duplicate, morbid, mutilated, out of frame, extra fingers, mutated hands, poorly drawn hands, poorly drawn face, mutation, deformed, blurry, dehydrated, bad anatomy, bad proportions, extra limbs, cloned face, disfigured, gross proportions, malformed limbs, missing arms, missing legs, extra arms, extra legs, fused fingers, too many fingers, long neck, username, watermark, signature",
        "weight": -0.9
      }],
      "cfg_scale":
      8,
      "height":
      768,
      "width":
      1536,
      "samples":
      1,
      "steps":
      30,
      "style_preset":
      "photographic"
    },
  )
  if response.status_code != 200:
    raise Exception("Non-200 response: " + str(response.text))
  else:
    print("Image response saved")
  data = response.json()
  base64String = data["artifacts"][0]["base64"]
  decodedData = base64.b64decode(base64String)
  imgFile = open(LOCAL_IMAGE, 'wb')
  imgFile.write(decodedData)
  imgFile.close()

def try_get_video(prompt):
  search_terms = getVideoSearchQueriesNoCaptions(prompt)

  background_video_urls = []
  if search_terms:
    background_video_urls = generate_video_urlNoCaptions(search_terms, "pexel")

  if len(background_video_urls) > 0:
    return background_video_urls[0]
  else:
    return ""

def gpt_act_as(system_prompt, user_prompt):
  completion = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    temperature=0.1,
    max_tokens=70,
    messages=[  
      {
        "role": "system",
        "content": system_prompt
      },
      {
        "role": "user",
        "content": user_prompt
      },
    ]
  )
  assistant_response = completion.choices[0].message.content
  return assistant_response

@app.route('/')
def base_page():
  return ("Running!")

@app.route('/get_all')
def get_all():
  return jsonify({
    "artifacts": firebase_utils.read_all("memories")
  })

if __name__ == '__main__':
  app.run(host='0.0.0.0')