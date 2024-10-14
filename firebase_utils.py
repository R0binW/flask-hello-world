import firebase_admin
from firebase_admin import credentials, initialize_app
from firebase_admin import firestore, storage

# cred = credentials.Certificate("project-50e83-firebase-adminsdk-9o6z6-c86699ca6f.json")
# firebase_admin.initialize_app(cred, {'storageBucket': 'project-50e83.appspot.com'})

cred = credentials.Certificate("/etc/secrets/firebase")
firebase_admin.initialize_app(cred, {'storageBucket': 'project-50e83.appspot.com'})
db = firestore.client()

def delete(collection_id, document_id):
  doc = db.collection(collection_id).document(document_id)
  doc.delete()

def delete_all(collection_id):
  col = db.collection(collection_id)
  for doc in col.stream():
    doc.delete()

def set(collection_id, document_id, json):
  db.collection(collection_id).document(document_id).set(json)

def read(collection_id, document_id):
  doc = db.collection(collection_id).document(document_id)
  return doc.get().to_dict()

def read_all(collection_id):
  jsonList = []
  col = db.collection(collection_id)
  for doc in col.stream():
    jsonList.append(doc.to_dict())
  return jsonList

def upload_to_storage(bucket_name, file_name):
  bucket = storage.bucket()
  blob = bucket.blob(bucket_name)
  blob.upload_from_filename(file_name)
  blob.make_public()
  return blob.public_url