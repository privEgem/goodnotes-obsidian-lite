# Optional Gemini study summaries

Gemini is **optional**. PDF-to-Markdown sync works without an API key and never
contacts Gemini. This example sends the chosen note's text to Google.

As of October 2026, creating a Gemini API key in **Google AI Studio** does not
require paying. Google's Free Tier supports certain models, including free input
and output usage for `gemini-3.8-flash`, subject to Google's usage limits. You can
try this example without enabling paid billing while staying within those limits.
Upgrading to paid usage requires [setting up billing](https://ai.google.dev/gemini-api/docs/billing).
Limits, model availability, and pricing can change; check
[Google's pricing page](https://ai.google.dev/gemini-api/docs/pricing) and
[API-key documentation](https://ai.google.dev/gemini-api/docs/api-key).

Google states that Free Tier content may be used to improve its products.
Do not send private or sensitive notes unless you are comfortable sharing that
content with Google.

1. Open [Google AI Studio](https://aistudio.google.com/) and sign in.
2. Create or copy an API key from its [API keys page](https://aistudio.google.com/apikey).
3. From the repository folder, install requirements in your virtual environment:

   ```text
   python -m pip install -r requirements.txt
   ```

4. Set your key for the **current terminal session**. Replace the placeholder.

   PowerShell:

   ```powershell
   $env:GEMINI_API_KEY="your-key-here"
   ```

   macOS/Linux:

   ```bash
   export GEMINI_API_KEY="your-key-here"
   ```

5. Run the example:

   ```text
   python gemini_summary.py path/to/note.md
   ```

The Google GenAI SDK uses `from google import genai` and `genai.Client()` to read
the environment key. It also accepts `GOOGLE_API_KEY`; if both variables are set,
that one takes precedence. The script prints a summary, leaves the note alone,
and disables automatic retries. Use `--model` to choose another available model.

Never paste a real key into Python source or commit it to GitHub. If a key is
exposed, revoke it and create another.
