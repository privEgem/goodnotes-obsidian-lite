"""Optional example: send one Markdown note to Gemini for a study summary."""

import argparse
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown_file", type=Path)
    parser.add_argument("--model", default="gemini-3.8-flash")
    args = parser.parse_args(argv)
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print("Set GEMINI_API_KEY first. See docs/GEMINI_API.md.", file=sys.stderr)
        return 1
    try:
        text = args.markdown_file.read_text(encoding="utf-8")
        from google import genai

        client = genai.Client()
        try:
            response = client.models.generate_content(
                model=args.model,
                contents="Write a short study summary of this note:\n\n" + text,
                # One attempt includes the original request: no automatic retries.
                config={"http_options": {"retry_options": {"attempts": 1}}},
            )
            if not response.text:
                print("Gemini returned no text summary.", file=sys.stderr)
                return 1
            print(response.text)
        finally:
            client.close()
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
