import openai
import os
import sys
import random
import base64
import requests
from datetime import datetime, timezone, timedelta
import firebase_admin
from firebase_admin import credentials, initialize_app
from firebase_admin import firestore, storage

from flask import Flask, jsonify
from flask_cors import CORS

#----------------------------------------------------------
#----------------------------------------------------------

import edge_tts
import json
import asyncio
import whisper_timestamped as whisper
from utility.script.script_generator import generate_script
from utility.audio.audio_generator import generate_audio
from utility.captions.timed_captions_generator import generate_timed_captions
from utility.video.background_video_generator import generate_video_url
from utility.render.render_engine import get_output_media
from utility.video.video_search_query_generator import getVideoSearchQueriesTimed, merge_empty_intervals
import argparse
#-----------------------------------------------------------

cred = credentials.Certificate(
  "/etc/secrets/firebase")
firebase_admin.initialize_app(cred,
                             {'storageBucket': 'project-50e83.appspot.com'})

app = Flask(__name__)
CORS(app)
db = firestore.client()

#file name of the generated image
generatedImage = "generated_image.png"

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

@app.route('/video/<userprompt>')
def VideoRequest(userprompt):
    SAMPLE_TOPIC = userprompt
    SAMPLE_FILE_NAME = "audio_tts.wav"
    VIDEO_SERVER = "pexel"

    response = generate_script(SAMPLE_TOPIC)
    print("script: {}".format(response))

    asyncio.run(generate_audio(response, SAMPLE_FILE_NAME))

    timed_captions = generate_timed_captions(SAMPLE_FILE_NAME)
    print(timed_captions)

    search_terms = getVideoSearchQueriesTimed(response, timed_captions)
    print(search_terms)

    background_video_urls = None
    if search_terms is not None:
        background_video_urls = generate_video_url(search_terms, VIDEO_SERVER)
        print(background_video_urls)
    else:
        print("No background video")

    background_video_urls = merge_empty_intervals(background_video_urls)

    if background_video_urls is not None:
        video = get_output_media(SAMPLE_FILE_NAME, timed_captions, background_video_urls, VIDEO_SERVER)
        print(video)
    else:
        print("No video")

#Robin Request will be called by a user client(Unity Project)
#It will take a parameter of a simple string describing a memory
#Then, it will put that string into a GPT prompt
#The GPT prompt response will go into dream studio
#We get back the generated image from dream studio
#Image turns from base64 into binary file
#JSON data goes into filebase database
#Image is stored into firestore
#Returns the json data associated with the image
@app.route('/robin/<userprompt>')
def RobinRequest(userprompt):
  system_prompt = 'I am going to give you some words. Form an image generation prompt of an environment or scene based on those words that is less than 40 words long. Your response must include those words.'

  gptResponse = gpt_act_as(system_prompt, userprompt)

  print("Generated Prompt: \n")
  print(gptResponse)
  print("\nPlease wait...")

  base64String = TextToImage(gptResponse)

  docData = create(userprompt, gptResponse)
  #print (gptResponse)

  return jsonify(docData)

#Takes the gpt prompt and puts it into the dream studio api and gives us an image back
def TextToImage(gptPrompt):
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
        "text": f"{gptPrompt}",
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
  # Decode base64 String Data
  decodedData = base64.b64decode(base64String)
  # Write Image from Base64 File
  imgFile = open(generatedImage, 'wb')
  imgFile.write(decodedData)
  imgFile.close()
  return base64String


@app.route('/gpt_act_as/<system_prompt>/<user_prompt>')
def gpt_act_as(system_prompt, user_prompt):
  completion = openai.ChatCompletion.create(model="gpt-3.5-turbo",
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
  ])
  assistant_response = completion.choices[0].message.content
  return assistant_response
#Regular Request
@app.route('/gpt_chat/<user_prompt>')
def gpt_chat(user_prompt):
  response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    prompt=user_prompt,
    max_tokens=70,  # Response Max Length
    temperature=0.5,  # Adjust for creativity
    top_p=1,  # Control response diversity
    frequency_penalty=0,  # Fine-tune word frequency
    presence_penalty=0  # Fine-tune word presence
  )
  message = response.choices[0].text.strip()
  print(message)

  return ("")


@app.route('/')
def base_page():
  return ("Running!")


@app.route('/test')
def test():
  return "test"


@app.route('/delete/<docName>')
def delete(docName):
  doc = db.collection("images").document(docName)
  doc.delete()

  #blob = bucket.blob(docName)

  print(docName, " was deleted")
  return ("")


@app.route('/deleteAll')
def deleteAll():
  col = db.collection("images")
  for doc in col.stream():
    doc.delete()

  print("ALL DOCUMENTS PURGED")
  return ("")


#Create a new Firebase Document
#@app.route('/create/<docName>/<prompt>')
def create(originalPrompt, gptPrompt):
  pst_timezone = timezone(timedelta(hours=-8))
  #Taking the current time and using it as the docname
  time = datetime.now(pst_timezone)
  currentTime = time.strftime("%m-%d-%Y, %H:%M:%S")
  docName = currentTime
  #Stores the image in firebase storage and gets the link
  imageURL = uploadImage(currentTime)
  new_doc = db.collection("images").document(docName)
  docData = {
    "originalPrompt": originalPrompt,
    "gptPrompt": gptPrompt,
    "imageName": currentTime,
    "imageURL": imageURL
  }
  #Store the document
  new_doc.set(docData)
  return docData

#Takes the current working image and stores it into firebase storage
def uploadImage(bucketFileName):
  #Uploads the local image.png
  bucket = storage.bucket()
  #Creates a new block if the given filename isnt there already
  blob = bucket.blob(bucketFileName)
  blob.upload_from_filename(generatedImage)
  blob.make_public()
  print("Image Stored!. Your file url is", blob.public_url)
  return blob.public_url

#Read specific field name from document
@app.route('/read/<docName>')
def read(docName):
  doc = db.collection("images").document(docName)
  doc_info = doc.get().to_dict()
  print(doc_info["prompt"])
  return ("")

#Returns all stored documents as one json object
@app.route('/readall')
def getAllImages():

  jsonList = []
  col = db.collection("images")
  for doc in col.stream():
    jsonList.append(doc.to_dict())
    #print(doc.to_dict())

  bigJson = {"artifacts": jsonList}

  return jsonify(bigJson)