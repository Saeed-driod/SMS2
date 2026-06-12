#!/bin/bash
gcloud auth login
gcloud config set project model-folio-393013
gcloud run deploy flask-app \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated
