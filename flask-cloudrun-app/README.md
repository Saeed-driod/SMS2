# Flask Cloud Run App

A simple Flask application ready to be deployed to Google Cloud Run.

## Project Structure

```text
flask-cloudrun-app/
├── app.py             # Main Flask application
├── requirements.txt   # Python dependencies
├── Dockerfile         # Docker configuration for Cloud Run
├── .dockerignore      # Files to exclude from Docker image
├── deploy.sh          # Deployment script
└── README.md          # Documentation
```

## Local Run Instructions

To run this project locally:

```bash
pip install -r requirements.txt
python app.py
```
The app will be available at `http://localhost:8080`.

## Deploy Instructions

To deploy to Google Cloud Run, execute the deployment script:

```bash
bash deploy.sh
```

Make sure to replace `YOUR_PROJECT_ID` in `deploy.sh` with your actual Google Cloud Project ID before running the script.
