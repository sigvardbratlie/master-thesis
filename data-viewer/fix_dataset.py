#!/usr/bin/env python3
"""
One-time fix script: repair mojibake encoding and renumber sessions/orders in a dataset JSON.

Usage:
    # Fix local file, output to <input>_fixed.json
    python fix_dataset.py /path/to/dataset.json

    # Fix and upload to GCS (requires GOOGLE_APPLICATION_CREDENTIALS or --key-file)
    python fix_dataset.py /path/to/dataset.json --upload --dataset TOSL-2024-125319
    python fix_dataset.py /path/to/dataset.json --upload --dataset TOSL-2024-125319 --key-file /path/to/key.json
"""

import argparse
import json
import sys
from pathlib import Path


def fix_mojibake(obj):
    """Recursively fix UTF-8 text that was incorrectly decoded as latin-1 (mojibake).

    The corruption pattern: UTF-8 bytes were decoded as latin-1, producing garbage
    like 'Ã¥' instead of 'å'. To reverse: re-encode as latin-1, then decode as UTF-8.
    """
    if isinstance(obj, str):
        try:
            fixed = obj.encode("latin-1").decode("utf-8")
            return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            return obj  # Already correct or not fixable
    elif isinstance(obj, dict):
        return {k: fix_mojibake(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fix_mojibake(item) for item in obj]
    return obj


def renumber(data: dict) -> None:
    """Reassign sequential 'session' and global 'order' fields in-place."""
    global_order = 0
    for s_idx, session in enumerate(data.get("sessions", [])):
        session["session"] = s_idx
        for query in session.get("conversation", []):
            query["order"] = global_order
            global_order += 1


def needs_encoding_fix(data: dict) -> bool:
    sample = json.dumps(data, ensure_ascii=False)
    return "Ã" in sample or "â€" in sample or "Â§" in sample


def main():
    parser = argparse.ArgumentParser(description="Fix mojibake encoding and renumber dataset JSON.")
    parser.add_argument("input", help="Path to the input JSON file")
    parser.add_argument("--output", help="Path to write fixed JSON (default: <input>_fixed.json)")
    parser.add_argument("--upload", action="store_true", help="Upload fixed file to GCS after fixing")
    parser.add_argument("--dataset", help="Dataset name in GCS (e.g. TOSL-2024-125319). Required if --upload.")
    parser.add_argument("--bucket", default="master-thesis-prod", help="GCS bucket name")
    parser.add_argument("--key-file", help="Path to GCS service account JSON key file")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else input_path.with_stem(input_path.stem + "_fixed")

    print(f"Reading: {input_path}")
    raw = json.loads(input_path.read_text(encoding="utf-8"))

    # Fix encoding
    if needs_encoding_fix(raw):
        print("Detected mojibake encoding — applying fix...")
        raw = fix_mojibake(raw)
        if needs_encoding_fix(raw):
            print("Warning: encoding still looks corrupted after fix. Manual review may be needed.")
        else:
            print("Encoding fixed OK.")
    else:
        print("Encoding looks correct — skipping encoding fix.")

    # Renumber sessions and orders
    before_sessions = [s.get("session") for s in raw.get("sessions", [])]
    before_orders = [q.get("order") for s in raw.get("sessions", []) for q in s.get("conversation", [])]
    renumber(raw)
    after_sessions = [s.get("session") for s in raw.get("sessions", [])]
    after_orders = [q.get("order") for s in raw.get("sessions", []) for q in s.get("conversation", [])]

    if before_sessions != after_sessions:
        print(f"Sessions renumbered: {before_sessions} → {after_sessions}")
    else:
        print("Session numbers were already correct.")

    if before_orders != after_orders:
        print(f"Orders renumbered: {before_orders} → {after_orders}")
    else:
        print("Order numbers were already correct.")

    # Write output
    output_path.write_text(json.dumps(raw, ensure_ascii=False, indent=4), encoding="utf-8")
    print(f"\nFixed file written to: {output_path}")

    # Optionally upload to GCS
    if args.upload:
        if not args.dataset:
            print("Error: --dataset is required when using --upload.", file=sys.stderr)
            sys.exit(1)

        try:
            from google.cloud import storage
            from google.oauth2 import service_account

            if args.key_file:
                creds = service_account.Credentials.from_service_account_file(args.key_file)
                client = storage.Client(credentials=creds)
            else:
                client = storage.Client()  # Uses GOOGLE_APPLICATION_CREDENTIALS env var

            payload = output_path.read_bytes()
            bucket = client.bucket(args.bucket)
            ds = args.dataset

            canonical = f"datasets/{ds}/dataset_{ds}.json"
            draft = f"datasets/{ds}/dataset_{ds}_draft.json"

            bucket.blob(canonical).upload_from_string(payload, content_type="application/json; charset=utf-8")
            print(f"Uploaded canonical: gs://{args.bucket}/{canonical}")

            # Delete stale draft so app loads fresh from canonical
            draft_blob = bucket.blob(draft)
            if draft_blob.exists():
                draft_blob.delete()
                print(f"Deleted stale draft:  gs://{args.bucket}/{draft}")

        except ImportError:
            print("Error: google-cloud-storage is not installed. Run: pip install google-cloud-storage", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error uploading to GCS: {e}", file=sys.stderr)
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
