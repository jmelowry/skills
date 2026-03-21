#!/usr/bin/env python3
"""
voice_preview_server.py — Launch a local web UI for browsing and previewing ElevenLabs voices.

Usage:
    python voice_preview_server.py [--port 7123] [--host 127.0.0.1] [--no-browser]

Required env:
    ELEVENLABS_API_KEY

The server auto-refreshes the voice cache on startup if it's stale (>24h).
Open http://localhost:7123 in a browser to browse voices, filter by vibe/label,
and play preview audio directly in the page.

Endpoints:
    GET  /              — Voice library UI
    GET  /api/voices    — JSON list of voices (with optional ?q=<search>)
    GET  /api/preview/<voice_id>  — Proxy preview audio from ElevenLabs
    POST /api/refresh   — Force re-fetch voices from ElevenLabs API
"""

import json
import os
import sys
import time
import webbrowser
import argparse
import threading
from pathlib import Path

import requests

# ─── Bootstrap path so we can import siblings ────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from list_voices import (
    fetch_all_voices, normalize_voice, load_cache, save_cache,
    CACHE_PATH, CACHE_TTL_HOURS
)
from voice_selector import VIBE_ALIASES

try:
    from flask import Flask, jsonify, request, Response, send_from_directory
except ImportError:
    print("Flask not found. Install with: pip install flask")
    sys.exit(1)

# ─── App setup ────────────────────────────────────────────────────────────────

app = Flask(__name__)
ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"

def get_api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")
    return key


def ensure_fresh_cache() -> list[dict]:
    cache = load_cache(CACHE_PATH)
    if cache:
        return cache["voices"]
    print("Cache stale or missing — fetching voices from ElevenLabs...")
    raw = fetch_all_voices(get_api_key())
    voices = [normalize_voice(v) for v in raw]
    save_cache(voices, CACHE_PATH)
    print(f"Cached {len(voices)} voices.")
    return voices

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML_UI

@app.route("/api/voices")
def api_voices():
    voices = ensure_fresh_cache()
    q = request.args.get("q", "").lower().strip()
    if q:
        voices = [
            v for v in voices
            if q in v["name"].lower()
            or q in v["description"].lower()
            or any(q in val.lower() for val in v["labels"].values())
        ]
    # Annotate with vibe matches
    for v in voices:
        v["vibes"] = _voice_vibes(v)
    return jsonify({"voices": voices, "total": len(voices)})

@app.route("/api/preview/<voice_id>")
def api_preview(voice_id):
    """Proxy the ElevenLabs preview URL so we avoid CORS and expose no key to the browser."""
    voices = ensure_fresh_cache()
    voice = next((v for v in voices if v["voice_id"] == voice_id), None)
    if not voice or not voice.get("preview_url"):
        return jsonify({"error": "No preview available"}), 404
    r = requests.get(voice["preview_url"], stream=True)
    return Response(
        r.iter_content(chunk_size=8192),
        content_type=r.headers.get("Content-Type", "audio/mpeg"),
    )

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    try:
        raw = fetch_all_voices(get_api_key())
        voices = [normalize_voice(v) for v in raw]
        save_cache(voices, CACHE_PATH)
        return jsonify({"ok": True, "count": len(voices)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── Vibe annotation ─────────────────────────────────────────────────────────

def _voice_vibes(voice: dict) -> list[str]:
    """Return which vibe aliases this voice matches (by name)."""
    name_lower = voice["name"].lower()
    matches = []
    seen_ids = set()
    for alias_key, alias_val in VIBE_ALIASES.items():
        if alias_val["name"].lower() == name_lower and alias_val["id"] not in seen_ids:
            matches.append(alias_key)
            seen_ids.add(alias_val["id"])
    return matches

# ─── Embedded UI ──────────────────────────────────────────────────────────────

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Voice Library</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=DM+Sans:wght@300;400;500;600&display=swap');

  :root {
    --bg:        #0e0e0f;
    --surface:   #161618;
    --border:    #2a2a2e;
    --border-hi: #3e3e44;
    --text:      #e8e8ea;
    --muted:     #6b6b72;
    --accent:    #7c6af7;
    --accent-hi: #a095ff;
    --play:      #2ecc8f;
    --play-hi:   #3fffa8;
    --tag-bg:    #1e1e24;
    --radius:    6px;
    --mono:      'DM Mono', monospace;
    --sans:      'DM Sans', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px 28px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--bg);
    z-index: 10;
  }

  header h1 {
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 400;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent-hi);
    flex-shrink: 0;
  }

  .search-wrap {
    flex: 1;
    max-width: 360px;
    position: relative;
  }

  .search-wrap svg {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    pointer-events: none;
  }

  #search {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-family: var(--mono);
    font-size: 12px;
    padding: 8px 12px 8px 32px;
    outline: none;
    transition: border-color 0.15s;
  }

  #search:focus { border-color: var(--accent); }
  #search::placeholder { color: var(--muted); }

  .header-right {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
  }

  #count {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
  }

  .btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--muted);
    font-family: var(--mono);
    font-size: 11px;
    padding: 6px 12px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .btn:hover { border-color: var(--border-hi); color: var(--text); }
  .btn.loading { color: var(--accent); border-color: var(--accent); }

  /* ── Filter chips ── */
  .filters {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    padding: 12px 28px;
    border-bottom: 1px solid var(--border);
  }

  .chip {
    background: var(--tag-bg);
    border: 1px solid var(--border);
    border-radius: 20px;
    color: var(--muted);
    font-family: var(--mono);
    font-size: 11px;
    padding: 4px 10px;
    cursor: pointer;
    transition: all 0.15s;
    user-select: none;
  }
  .chip:hover { border-color: var(--border-hi); color: var(--text); }
  .chip.active {
    background: rgba(124,106,247,0.15);
    border-color: var(--accent);
    color: var(--accent-hi);
  }

  /* ── Table ── */
  .table-wrap {
    padding: 16px 28px 48px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  thead th {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    text-align: left;
    padding: 0 12px 10px;
    border-bottom: 1px solid var(--border);
  }

  thead th:first-child { padding-left: 0; }

  tbody tr {
    border-bottom: 1px solid var(--border);
    transition: background 0.1s;
  }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: rgba(255,255,255,0.02); }

  td {
    padding: 14px 12px;
    vertical-align: top;
  }
  td:first-child { padding-left: 0; }

  /* ── Name cell ── */
  .name-cell {
    min-width: 120px;
  }
  .voice-name {
    font-weight: 500;
    color: var(--text);
    font-size: 13px;
  }
  .voice-id {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    margin-top: 2px;
    cursor: pointer;
    transition: color 0.15s;
  }
  .voice-id:hover { color: var(--accent-hi); }
  .voice-id.copied { color: var(--play); }

  /* ── Label tags ── */
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .tag {
    background: var(--tag-bg);
    border: 1px solid var(--border);
    border-radius: 3px;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    padding: 2px 6px;
  }
  .tag.accent {
    background: rgba(124,106,247,0.1);
    border-color: rgba(124,106,247,0.3);
    color: var(--accent-hi);
  }

  /* ── Description ── */
  .desc {
    font-size: 12px;
    color: var(--muted);
    max-width: 280px;
    line-height: 1.4;
  }

  /* ── Vibes ── */
  .vibes {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .vibe-tag {
    background: rgba(46,204,143,0.08);
    border: 1px solid rgba(46,204,143,0.2);
    border-radius: 3px;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--play);
    padding: 2px 6px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .vibe-tag:hover {
    background: rgba(46,204,143,0.18);
    border-color: rgba(46,204,143,0.5);
  }

  /* ── Play button ── */
  .play-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: none;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--muted);
    font-family: var(--mono);
    font-size: 11px;
    padding: 6px 12px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .play-btn:hover {
    border-color: var(--play);
    color: var(--play);
  }
  .play-btn.playing {
    border-color: var(--play-hi);
    color: var(--play-hi);
    background: rgba(46,204,143,0.08);
  }
  .play-btn.loading {
    border-color: var(--accent);
    color: var(--accent);
  }
  .play-btn svg { flex-shrink: 0; }

  /* ── Audio bar ── */
  .audio-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
  }
  .progress-wrap {
    flex: 1;
    height: 2px;
    background: var(--border);
    border-radius: 1px;
    overflow: hidden;
    max-width: 120px;
  }
  .progress-fill {
    height: 100%;
    background: var(--play);
    width: 0%;
    transition: width 0.1s linear;
  }

  /* ── Empty state ── */
  .empty {
    text-align: center;
    padding: 64px 0;
    color: var(--muted);
    font-family: var(--mono);
    font-size: 12px;
  }

  /* ── Toast ── */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--surface);
    border: 1px solid var(--border-hi);
    border-radius: var(--radius);
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text);
    padding: 10px 16px;
    transform: translateY(20px);
    opacity: 0;
    transition: all 0.2s;
    pointer-events: none;
    z-index: 100;
  }
  .toast.show { transform: translateY(0); opacity: 1; }
</style>
</head>
<body>

<header>
  <h1>&#x2022; Voice Library</h1>
  <div class="search-wrap">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
    </svg>
    <input id="search" type="text" placeholder="search by name, accent, use case…" autocomplete="off" spellcheck="false">
  </div>
  <div class="header-right">
    <span id="count"></span>
    <button class="btn" id="refresh-btn" onclick="refreshVoices()">↻ Refresh</button>
  </div>
</header>

<div class="filters" id="filters"></div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>Name</th>
        <th>Labels</th>
        <th>Description</th>
        <th>Vibe aliases</th>
        <th>Preview</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">No voices match that filter.</div>
</div>

<div id="toast" class="toast"></div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let allVoices = [];
let activeFilter = null;
let currentAudio = null;
let currentBtn = null;
let searchDebounce = null;

// ── Boot ───────────────────────────────────────────────────────────────────
(async () => {
  await loadVoices();
  buildFilterChips();
  renderTable(allVoices);
  document.getElementById('search').addEventListener('input', e => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      applyFilters(e.target.value.trim());
    }, 180);
  });
})();

// ── Data ───────────────────────────────────────────────────────────────────
async function loadVoices(q = '') {
  const url = q ? `/api/voices?q=${encodeURIComponent(q)}` : '/api/voices';
  const res = await fetch(url);
  const data = await res.json();
  allVoices = data.voices;
  return allVoices;
}

async function refreshVoices() {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = '↻ Refreshing…';
  btn.classList.add('loading');
  try {
    const res = await fetch('/api/refresh', { method: 'POST' });
    const data = await res.json();
    await loadVoices();
    buildFilterChips();
    applyFilters(document.getElementById('search').value.trim());
    toast(`Refreshed — ${data.count} voices loaded`);
  } catch(e) {
    toast('Refresh failed: ' + e.message);
  } finally {
    btn.textContent = '↻ Refresh';
    btn.classList.remove('loading');
  }
}

// ── Filters ────────────────────────────────────────────────────────────────
const FILTER_CHIPS = [
  { label: 'all',           q: '' },
  { label: 'assistant',     q: 'assistant' },
  { label: 'narration',     q: 'narration' },
  { label: 'conversational',q: 'conversational' },
  { label: 'news',          q: 'news' },
  { label: 'female',        q: 'female' },
  { label: 'male',          q: 'male' },
  { label: 'british',       q: 'british' },
  { label: 'american',      q: 'american' },
  { label: 'young',         q: 'young' },
];

function buildFilterChips() {
  const el = document.getElementById('filters');
  el.innerHTML = FILTER_CHIPS.map(c =>
    `<div class="chip${c.q === (activeFilter || '') ? ' active' : ''}"
          onclick="setFilter('${c.q}', this)">${c.label}</div>`
  ).join('');
}

function setFilter(q, chipEl) {
  activeFilter = q || null;
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  chipEl.classList.add('active');
  document.getElementById('search').value = q;
  applyFilters(q);
}

function applyFilters(q) {
  const term = q.toLowerCase();
  const filtered = term
    ? allVoices.filter(v =>
        v.name.toLowerCase().includes(term) ||
        v.description.toLowerCase().includes(term) ||
        Object.values(v.labels).some(l => l.toLowerCase().includes(term)) ||
        (v.vibes || []).some(vib => vib.includes(term))
      )
    : allVoices;
  renderTable(filtered);
}

// ── Render ─────────────────────────────────────────────────────────────────
function renderTable(voices) {
  const tbody = document.getElementById('tbody');
  const empty = document.getElementById('empty');
  const count = document.getElementById('count');

  count.textContent = `${voices.length} voice${voices.length !== 1 ? 's' : ''}`;

  if (!voices.length) {
    tbody.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = voices.map(v => {
    const l = v.labels;
    const labelTags = [l.gender, l.age, l.accent]
      .filter(Boolean)
      .map(t => `<span class="tag">${t}</span>`)
      .join('');
    const useCaseTag = l.use_case
      ? `<span class="tag accent">${l.use_case}</span>` : '';
    const vibeTags = (v.vibes || []).slice(0, 4)
      .map(vib => `<span class="vibe-tag" onclick="setFilterStr('${vib}')" title="Click to filter">${vib}</span>`)
      .join('');
    const shortId = v.voice_id.substring(0, 8) + '…';
    const desc = v.description ? v.description.substring(0, 120) + (v.description.length > 120 ? '…' : '') : '';

    return `<tr>
      <td class="name-cell">
        <div class="voice-name">${esc(v.name)}</div>
        <div class="voice-id" title="Click to copy full ID" onclick="copyId('${v.voice_id}', this)">${shortId}</div>
      </td>
      <td><div class="tags">${labelTags}${useCaseTag}</div></td>
      <td><div class="desc">${esc(desc)}</div></td>
      <td><div class="vibes">${vibeTags}</div></td>
      <td>
        <button class="play-btn" id="btn-${v.voice_id}" onclick="togglePlay('${v.voice_id}', this)">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
          play
        </button>
        <div class="audio-bar" id="bar-${v.voice_id}" style="display:none">
          <div class="progress-wrap"><div class="progress-fill" id="prog-${v.voice_id}"></div></div>
        </div>
      </td>
    </tr>`;
  }).join('');
}

// ── Playback ───────────────────────────────────────────────────────────────
function togglePlay(voiceId, btn) {
  if (currentAudio && currentBtn === btn) {
    stopAudio();
    return;
  }
  if (currentAudio) stopAudio();

  btn.classList.add('loading');
  btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> loading`;

  const audio = new Audio(`/api/preview/${voiceId}`);
  currentAudio = audio;
  currentBtn = btn;

  const bar = document.getElementById('bar-' + voiceId);
  const prog = document.getElementById('prog-' + voiceId);

  audio.addEventListener('canplay', () => {
    btn.classList.remove('loading');
    btn.classList.add('playing');
    btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> playing`;
    bar.style.display = 'flex';
    audio.play();
  });

  audio.addEventListener('timeupdate', () => {
    if (audio.duration) {
      prog.style.width = (audio.currentTime / audio.duration * 100) + '%';
    }
  });

  audio.addEventListener('ended', () => stopAudio());
  audio.addEventListener('error', () => {
    toast('Preview not available for this voice');
    stopAudio();
  });
}

function stopAudio() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  if (currentBtn) {
    const voiceId = currentBtn.id.replace('btn-', '');
    currentBtn.classList.remove('playing', 'loading');
    currentBtn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg> play`;
    const bar = document.getElementById('bar-' + voiceId);
    const prog = document.getElementById('prog-' + voiceId);
    if (bar) bar.style.display = 'none';
    if (prog) prog.style.width = '0%';
    currentBtn = null;
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────
function setFilterStr(q) {
  document.getElementById('search').value = q;
  applyFilters(q);
}

async function copyId(id, el) {
  await navigator.clipboard.writeText(id);
  const prev = el.textContent;
  el.textContent = 'copied!';
  el.classList.add('copied');
  setTimeout(() => {
    el.textContent = prev;
    el.classList.remove('copied');
  }, 1500);
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

let toastTimer;
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2800);
}
</script>
</body>
</html>"""

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Launch voice preview server")
    parser.add_argument("--port", type=int, default=7123)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    # Warm cache before starting
    try:
        ensure_fresh_cache()
    except Exception as e:
        print(f"Warning: couldn't pre-warm cache: {e}")

    url = f"http://{args.host}:{args.port}"
    print(f"\n  Voice Library  →  {url}\n")
    print("  Ctrl+C to stop\n")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
