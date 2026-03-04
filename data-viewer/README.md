# Data Viewer Module

Streamlit app for browsing, inspecting, and managing evaluation datasets stored in Google Cloud Storage.

## Overview

The data viewer provides a UI for exploring test datasets, comparing agent results across configurations, and viewing DeepEval evaluation metrics. It connects directly to the `master-thesis-prod` GCS bucket.

## Structure

```
data-viewer/
├── main.py           # Streamlit app (dataset browser, result comparison, metrics display)
└── fix_dataset.py    # Data migration/cleanup utility for dataset inconsistencies
```

## Features

- Browse test datasets stored in GCS
- View session metadata and conversation turns
- Compare agent results across `custom`, `baseline`, and `baseline_rag` configurations
- Display evaluation metrics per session
- Download and manage dataset files (read, write, move, delete blobs)

## Running

```bash
uv run --package data-viewer streamlit run data-viewer/main.py
```

## Environment Variables

```bash
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_APPLICATION_CREDENTIALS=./gcloud-keys.json
```

The app uses a cached GCS client initialized with the service account credentials.
