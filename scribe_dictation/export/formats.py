"""Format writers for exporting a TranscriptionResult.

Three formats are supported:

- Plain text (.txt): one line per segment, prefixed with a
  `[HH:MM:SS]` timestamp marker, e.g.::

      [00:00:00] Hello there.
      [00:00:04] This is a second segment.

  Design choice: segment boundaries in this app correspond to distinct
  transcription events (e.g. separate recordings appended to the same
  session), so preserving a timestamp per line is more useful than
  collapsing everything into unbroken prose, at negligible readability
  cost.

- Markdown (.md): a `#` heading (title + date), followed by one entry per
  segment as a bullet list with the timestamp rendered as a subtle inline
  code marker, e.g. `` - `[00:00:00]` Hello there. ``

- SRT (.srt): standard SubRip subtitle format — 1-indexed entries, each
  with a `HH:MM:SS,mmm --> HH:MM:SS,mmm` timestamp line (comma-separated
  milliseconds, zero-padded), the text, and a blank line between entries.
"""

from __future__ import annotations

from scribe_dictation.export.models import TranscriptionResult


def _format_clock(seconds: float) -> str:
    """Format seconds as zero-padded HH:MM:SS (used by .txt/.md)."""
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_srt_timestamp(seconds: float) -> str:
    """Format seconds as SRT's HH:MM:SS,mmm (comma, zero-padded milliseconds)."""
    if seconds < 0:
        raise ValueError(f"Cannot format a negative timestamp: {seconds}")
    total_ms = round(seconds * 1000)
    hours, remainder_ms = divmod(total_ms, 3_600_000)
    minutes, remainder_ms = divmod(remainder_ms, 60_000)
    secs, ms = divmod(remainder_ms, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def to_txt(result: TranscriptionResult) -> str:
    """Render a TranscriptionResult as plain text, one timestamped line per segment."""
    lines = [
        f"[{_format_clock(segment.start)}] {segment.text.strip()}"
        for segment in result.segments
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def to_markdown(result: TranscriptionResult) -> str:
    """Render a TranscriptionResult as Markdown with a heading and bullet list."""
    title = result.title or "Transcription"
    date_str = result.created_at.strftime("%Y-%m-%d %H:%M")
    lines = [f"# {title}", "", f"*{date_str}*", ""]
    for segment in result.segments:
        timestamp = _format_clock(segment.start)
        lines.append(f"- `[{timestamp}]` {segment.text.strip()}")
    return "\n".join(lines) + "\n"


def to_srt(result: TranscriptionResult) -> str:
    """Render a TranscriptionResult as an SRT subtitle file."""
    blocks = []
    for index, segment in enumerate(result.segments, start=1):
        start = _format_srt_timestamp(segment.start)
        end = _format_srt_timestamp(segment.end)
        blocks.append(f"{index}\n{start} --> {end}\n{segment.text.strip()}\n")
    return "\n".join(blocks)


def to_json(result: TranscriptionResult) -> str:
    """Render a TranscriptionResult as structured JSON."""
    import json

    data = {
        "title": result.title or "Transcription",
        "created_at": result.created_at.isoformat(),
        "text": result.text,
        "segments": [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
            }
            for segment in result.segments
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def to_html(result: TranscriptionResult) -> str:
    """Render a TranscriptionResult as a beautifully styled HTML page."""
    import html

    title = html.escape(result.title or "Transcription")
    date_str = html.escape(result.created_at.strftime("%Y-%m-%d %H:%M:%S"))

    segments_html = []
    for segment in result.segments:
        start_str = _format_clock(segment.start)
        text_escaped = html.escape(segment.text.strip())
        segments_html.append(
            f'<div class="segment" style="margin-bottom: 12px; padding: 6px; border-left: 3px solid #3182ce; padding-left: 10px;">'
            f'<span class="time" style="color: #718096; font-family: monospace; font-size: 12px; margin-right: 10px;">[{start_str}]</span>'
            f'<span class="text" style="color: #2d3748; font-size: 14px;">{text_escaped}</span>'
            f"</div>"
        )

    body_content = "\n".join(segments_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            background-color: #f7fafc;
            color: #2d3748;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        h1 {{
            color: #1a202c;
            margin-top: 0;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 10px;
        }}
        .meta {{
            font-size: 12px;
            color: #a0aec0;
            margin-bottom: 20px;
        }}
        .transcript {{
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="meta">Generated by Privacy Scribe on {date_str}</div>
        <div class="transcript">
{body_content}
        </div>
    </div>
</body>
</html>
"""
