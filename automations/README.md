# Automations

Drop a Python script here to add notes to your hub automatically. Every script
can reuse the same code the app uses via `_helpers`:

```python
from _helpers import add_note, capture_url

# Add a note directly
add_note(
    title="Quantize YOLO for edge",
    category="Computer Vision",
    subcategory="Inspection",
    body="Try INT8 quantization on the defect model.",
    tags=["edge", "quantization"],
    due="2026-07-01",
)

# Or capture a URL (X/Twitter-aware)
capture_url("https://x.com/someone/status/123456789")
```

Run a script from the `app/` folder:

```
python automations/capture_x_post.py https://x.com/user/status/123
```

## Scheduling (optional)

To run an automation on a schedule, use **Windows Task Scheduler**:

1. Open *Task Scheduler* → *Create Basic Task*.
2. Trigger: Daily (or whatever cadence).
3. Action: *Start a program*.
   - Program: `python`
   - Arguments: `automations\your_script.py`
   - Start in: the full path to this `app` folder.

Notes are plain Markdown files, so anything that can write a `.md` file with
YAML frontmatter into `vault/<Category>/<Subcategory>/` will show up in the app.
