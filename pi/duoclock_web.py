#!/usr/bin/env python3
"""
==============================================================================
 🌐 DuoClock Web Dashboard
==============================================================================

 A single-page web dashboard that shows 7 days of DuoClock timer activity.
 Reads the event log written by duoclock_monitor.py and renders an HTML page
 with a bar graph, daily totals table, and recent events list.

 ┌──────────────────────────────────────────────────────────────────────┐
 │                        HOW IT WORKS                                  │
 │                                                                      │
 │  /var/log/duoclock.log ──► parse_log() ──► compute_daily_totals()   │
 │                                                    │                 │
 │                                                    ▼                 │
 │                                              build_page()           │
 │                                                    │                 │
 │                                                    ▼                 │
 │                                          ┌─────────────────┐        │
 │                                          │   HTML Page      │        │
 │                                          │  ┌─────────────┐ │        │
 │                                          │  │ 📊 Bar Graph │ │        │
 │                                          │  │  7 days      │ │        │
 │                                          │  ├─────────────┤ │        │
 │                                          │  │ 📋 Table     │ │        │
 │                                          │  │  Daily mins  │ │        │
 │                                          │  ├─────────────┤ │        │
 │                                          │  │ 📜 Recent    │ │        │
 │                                          │  │  Last 20     │ │        │
 │                                          │  └─────────────┘ │        │
 │                                          └─────────────────┘        │
 │                                                                      │
 │  The page auto-refreshes every 60 seconds via <meta http-equiv>.    │
 │  No JavaScript frameworks. No external dependencies. Pure stdlib.   │
 │                                                                      │
 │  Designed for the Pi Zero W's limited resources:                     │
 │    - No background processing or file watching                       │
 │    - Re-parses the log fresh on each HTTP request                    │
 │    - Single-threaded HTTP server (fine for occasional dashboard use) │
 └──────────────────────────────────────────────────────────────────────┘

 URL:     http://clockradio.belairmoon.au:8080/
 Service: duoclock-web.service
 Log:     reads /var/log/duoclock.log (written by duoclock_monitor.py)
==============================================================================
"""

import datetime
import html
import http.server
import os
import socketserver
import sys

# ===========================================================================
# ⚙️ Configuration via environment variables
# ===========================================================================
# These can be overridden without touching the code, but the systemd unit
# doesn't set them — so these defaults are what's actually used.
# ===========================================================================
LOG_FILE = os.environ.get("DUOCLOCK_LOG", "/var/log/duoclock.log")
PORT = int(os.environ.get("DUOCLOCK_WEB_PORT", "8080"))


# ===========================================================================
# 📂 Log Parsing
# ===========================================================================

def parse_log():
    """
    📂 Parse the duoclock event log into a list of (datetime, event) tuples.
    
    Log format (one event per line):
        2026-03-17 13:45:00 THEM_ON
        2026-03-17 14:15:00 THEM_OFF_TIMEOUT
    
    Returns an empty list if the log file doesn't exist yet (fresh install).
    Silently skips malformed lines — the log is append-only and we trust
    the monitor to write valid lines, but defensive parsing is free.
    """
    entries = []
    if not os.path.exists(LOG_FILE):
        return entries
    with open(LOG_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Split into: ["2026-03-17", "13:45:00", "THEM_ON"]
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            try:
                dt = datetime.datetime.strptime(
                    f"{parts[0]} {parts[1]}", "%Y-%m-%d %H:%M:%S"
                )
                entries.append((dt, parts[2]))
            except ValueError:
                continue
    return entries


# ===========================================================================
# 📊 Duration Computation
# ===========================================================================

def compute_daily_totals(entries, num_days=7):
    """
    📊 Compute per-day on-time in minutes for each channel over the last 7 days.
    
    Algorithm:
      1. Create empty daily buckets for the last 7 days
      2. Walk through all log entries tracking when each channel turned on
      3. When we see an OFF event, compute the duration from ON→OFF
      4. Distribute that duration across day buckets (handles midnight crossings)
      5. If a channel is still on (no OFF yet), count up to current time
    
    Returns:
      days:   list of date objects (oldest first)
      totals: dict mapping date → {"THEM": minutes, "ME": minutes}
    
    ┌─────────────────────────────────────────────────────────────┐
    │  State Machine (per channel):                                │
    │                                                              │
    │  ──► [OFF] ──THEM_ON──► [ON] ──THEM_OFF_TIMEOUT──► [OFF]   │
    │        ▲                  │                                   │
    │        └──BOTH_CANCEL────┘                                   │
    └─────────────────────────────────────────────────────────────┘
    """
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=num_days - 1)

    # Build the list of days we're interested in (oldest → newest)
    days = []
    for i in range(num_days):
        d = start_date + datetime.timedelta(days=i)
        days.append(d)
    totals = {d: {"THEM": 0.0, "ME": 0.0} for d in days}

    # Track when each channel turned on (None = currently off)
    on_since = {"THEM": None, "ME": None}

    for dt, event in entries:
        if event == "THEM_ON":
            on_since["THEM"] = dt
        elif event == "ME_ON":
            on_since["ME"] = dt
        elif event in ("THEM_OFF_TIMEOUT",):
            if on_since["THEM"] is not None:
                _add_duration(totals, days, on_since["THEM"], dt, "THEM")
                on_since["THEM"] = None
        elif event in ("ME_OFF_TIMEOUT",):
            if on_since["ME"] is not None:
                _add_duration(totals, days, on_since["ME"], dt, "ME")
                on_since["ME"] = None
        elif event == "BOTH_CANCEL":
            # Both-cancel ends BOTH channels
            for ch in ("THEM", "ME"):
                if on_since[ch] is not None:
                    _add_duration(totals, days, on_since[ch], dt, ch)
                    on_since[ch] = None

    # -----------------------------------------------------------------------
    # If a channel is currently active (ON with no OFF yet), count the
    # duration from its ON time up to right now. This makes the dashboard
    # show real-time accumulated time for in-progress timers.
    # -----------------------------------------------------------------------
    now = datetime.datetime.now()
    for ch in ("THEM", "ME"):
        if on_since[ch] is not None:
            _add_duration(totals, days, on_since[ch], now, ch)

    return days, totals


def _add_duration(totals, days, start_dt, end_dt, channel):
    """
    ➕ Add a duration interval to the appropriate daily buckets.
    
    Handles three cases:
      1. Interval is entirely outside our 7-day window → skip
      2. Interval is within a single day → simple addition
      3. Interval spans midnight → split across multiple day buckets
    
    Duration is stored in MINUTES (float) for easy display.
    
    Example spanning midnight:
      ON at 23:30, OFF at 00:45
      → Day 1 gets 30 minutes (23:30-00:00)
      → Day 2 gets 45 minutes (00:00-00:45)
    """
    start_date = days[0]
    end_date = days[-1]

    # Skip if entirely outside our window
    if end_dt.date() < start_date or start_dt.date() > end_date:
        return

    # Simple case: same day
    if start_dt.date() == end_dt.date():
        d = start_dt.date()
        if d in totals:
            totals[d][channel] += (end_dt - start_dt).total_seconds() / 60.0
        return

    # Spans midnight — walk through each day and attribute the right portion
    cursor = start_dt
    while cursor < end_dt:
        d = cursor.date()
        day_end = datetime.datetime.combine(
            d + datetime.timedelta(days=1), datetime.time.min
        )
        segment_end = min(day_end, end_dt)
        if d in totals:
            totals[d][channel] += (segment_end - cursor).total_seconds() / 60.0
        cursor = segment_end


# ===========================================================================
# 🎨 Display Formatting
# ===========================================================================

def fmt_duration(minutes):
    """
    🕐 Format minutes as a human-readable string: "2h 15m", "45m", "0m"
    
    Used in both the table and the graph scale label.
    """
    if minutes < 1:
        return "0m"
    h = int(minutes) // 60
    m = int(minutes) % 60
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    if h > 0:
        return f"{h}h"
    return f"{m}m"


# ===========================================================================
# 🖥️ HTML Page Builder
# ===========================================================================

def build_page():
    """
    🖥️ Build the complete HTML dashboard page.
    
    This is called on EVERY request — we don't cache anything because:
      1. The Pi has plenty of headroom for occasional dashboard views
      2. Fresh data is more important than response speed
      3. The log file is small (one line per event, maybe 20-50 per day)
    
    The page is fully self-contained:
      - No external CSS/JS files
      - No CDN dependencies
      - Dark theme with red/yellow accent colours matching the physical LEDs
      - Responsive (works on mobile)
      - Auto-refreshes via <meta http-equiv="refresh" content="60">
    
    Page sections:
      📊 Bar Graph  — visual 7-day comparison, bars scaled to max value
      📋 Table      — exact daily totals per channel, today's row bolded
      📜 Recent     — last 20 log entries in reverse-chronological order
    """
    entries = parse_log()
    days, totals = compute_daily_totals(entries)

    # -----------------------------------------------------------------------
    # 📏 Determine graph scale
    # -----------------------------------------------------------------------
    # Find the maximum daily value to scale bar heights as percentages.
    # Round up to nearest 30 minutes for a cleaner scale label.
    # Minimum of 30 minutes so an empty graph doesn't look broken.
    # -----------------------------------------------------------------------
    max_mins = 1  # avoid division by zero
    for d in days:
        for ch in ("THEM", "ME"):
            max_mins = max(max_mins, totals[d][ch])
    max_mins = max(30, ((int(max_mins) // 30) + 1) * 30)

    today = datetime.date.today()
    day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

    # -----------------------------------------------------------------------
    # 📊 Build table rows and bar chart elements
    # -----------------------------------------------------------------------
    rows_html = ""
    bars_html = ""
    for d in days:
        them_mins = totals[d]["THEM"]
        me_mins = totals[d]["ME"]
        them_pct = (them_mins / max_mins) * 100
        me_pct = (me_mins / max_mins) * 100

        day_label = day_names[d.weekday()]
        date_str = d.strftime("%d %b")
        is_today = " (today)" if d == today else ""
        bold = " style='font-weight:700'" if d == today else ""

        rows_html += f"""<tr{bold}>
            <td>{html.escape(day_label)} {html.escape(date_str)}{is_today}</td>
            <td class="dur them">{fmt_duration(them_mins)}</td>
            <td class="dur me">{fmt_duration(me_mins)}</td>
        </tr>\n"""

        bars_html += f"""<div class="bar-group">
            <div class="bar-label">{html.escape(day_label)}<br><small>{html.escape(date_str)}</small></div>
            <div class="bar-pair">
                <div class="bar them" style="height:{them_pct:.1f}%"
                     title="Them: {fmt_duration(them_mins)}"></div>
                <div class="bar me" style="height:{me_pct:.1f}%"
                     title="Me: {fmt_duration(me_mins)}"></div>
            </div>
        </div>\n"""

    # -----------------------------------------------------------------------
    # 📜 Build recent events table (last 20, newest first)
    # -----------------------------------------------------------------------
    recent = entries[-20:]
    recent.reverse()
    recent_html = ""
    for dt, event in recent:
        recent_html += f"<tr><td>{html.escape(dt.strftime('%d %b %H:%M'))}</td><td>{html.escape(event)}</td></tr>\n"

    # -----------------------------------------------------------------------
    # 🎨 Assemble the full HTML page
    # -----------------------------------------------------------------------
    # All CSS is inline in a <style> block. Colour choices:
    #   🔴 #e74c3c = red (THEM) — matches the physical red LED
    #   🟡 #f1c40f = yellow (ME) — matches the physical yellow LED
    #   🌙 #1a1a2e = dark background — easy on the eyes
    # -----------------------------------------------------------------------
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DuoClock</title>
<meta http-equiv="refresh" content="60">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 1.5rem; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 1rem; color: #fff; }}
  h2 {{ font-size: 1.1rem; margin: 1.5rem 0 0.5rem; color: #aaa; }}

  .graph {{ display: flex; align-items: flex-end; gap: 0.5rem; height: 200px;
            background: #16213e; border-radius: 8px; padding: 1rem 0.5rem 2.5rem; margin-bottom: 1rem; position: relative; }}
  .bar-group {{ flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }}
  .bar-pair {{ display: flex; gap: 3px; align-items: flex-end; flex: 1; width: 100%; justify-content: center; }}
  .bar {{ width: 16px; border-radius: 3px 3px 0 0; min-height: 2px; transition: height 0.3s; }}
  .bar.them {{ background: #e74c3c; }}
  .bar.me {{ background: #f1c40f; }}
  .bar-label {{ font-size: 0.7rem; text-align: center; color: #888; margin-top: 0.3rem; position: absolute; bottom: 0.3rem; }}
  .bar-group {{ position: relative; }}
  .bar-label {{ position: relative; }}

  table {{ border-collapse: collapse; width: 100%; max-width: 500px; }}
  th, td {{ padding: 0.35rem 0.75rem; text-align: left; }}
  th {{ color: #888; font-weight: 500; border-bottom: 1px solid #333; }}
  td {{ border-bottom: 1px solid #222; }}
  .dur.them {{ color: #e74c3c; }}
  .dur.me {{ color: #f1c40f; }}

  .legend {{ display: flex; gap: 1.5rem; margin-bottom: 1rem; font-size: 0.85rem; }}
  .legend span {{ display: flex; align-items: center; gap: 0.4rem; }}
  .dot {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .dot.them {{ background: #e74c3c; }}
  .dot.me {{ background: #f1c40f; }}

  .recent {{ font-size: 0.8rem; max-width: 400px; }}
  .recent td {{ color: #999; }}
  .scale {{ position: absolute; left: 0.3rem; top: 0.8rem; font-size: 0.65rem; color: #555; }}
</style>
</head>
<body>
<h1>DuoClock &mdash; 7 Day View</h1>
<div class="legend">
  <span><span class="dot them"></span> Them (red)</span>
  <span><span class="dot me"></span> Me (yellow)</span>
</div>
<div class="graph">
  <div class="scale">{fmt_duration(max_mins)}</div>
  {bars_html}
</div>
<table>
  <tr><th>Day</th><th>Them</th><th>Me</th></tr>
  {rows_html}
</table>
<h2>Recent Events</h2>
<table class="recent">
  <tr><th>Time</th><th>Event</th></tr>
  {recent_html}
</table>
<p style="margin-top:2rem;font-size:0.7rem;color:#555">Auto-refreshes every 60s</p>
</body>
</html>"""


# ===========================================================================
# 🔌 HTTP Server
# ===========================================================================

class Handler(http.server.BaseHTTPRequestHandler):
    """
    🔌 Simple HTTP handler — serves the dashboard on GET /
    
    Only responds to "/" and "/index.html". Everything else gets a 404.
    Request logging is suppressed to keep journalctl clean — the dashboard
    is polled every 60 seconds and we don't need to log each request.
    """

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            body = build_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        # Suppress per-request logging to avoid noise in journal
        pass


def main():
    """
    🚀 Start the HTTP server on the configured port.
    
    Uses socketserver.TCPServer which is single-threaded — perfectly fine
    for a dashboard that gets occasional human visitors. The Pi Zero's
    single core wouldn't benefit from threading here anyway.
    """
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.allow_reuse_address = True
        print(f"DuoClock web on port {PORT}", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
