#!/usr/bin/env python3
"""
DuoClock Web — single-page dashboard showing 7 days of timer activity.
Reads /var/log/duoclock.log and serves an HTML page with daily totals and a bar graph.
"""

import datetime
import html
import http.server
import os
import socketserver
import sys

LOG_FILE = os.environ.get("DUOCLOCK_LOG", "/var/log/duoclock.log")
PORT = int(os.environ.get("DUOCLOCK_WEB_PORT", "8080"))


def parse_log():
    """Parse the duoclock log and return a list of (datetime, event) tuples."""
    entries = []
    if not os.path.exists(LOG_FILE):
        return entries
    with open(LOG_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Format: "2026-03-17 13:45:00 EVENT"
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


def compute_daily_totals(entries, num_days=7):
    """Compute per-day on-time in minutes for THEM and ME over the last num_days days."""
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=num_days - 1)

    # Initialise daily buckets
    days = []
    for i in range(num_days):
        d = start_date + datetime.timedelta(days=i)
        days.append(d)
    totals = {d: {"THEM": 0.0, "ME": 0.0} for d in days}

    # Track when each channel turned on
    on_since = {"THEM": None, "ME": None}

    for dt, event in entries:
        d = dt.date()

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
            for ch in ("THEM", "ME"):
                if on_since[ch] is not None:
                    _add_duration(totals, days, on_since[ch], dt, ch)
                    on_since[ch] = None

    # If a channel is still on, count up to now
    now = datetime.datetime.now()
    for ch in ("THEM", "ME"):
        if on_since[ch] is not None:
            _add_duration(totals, days, on_since[ch], now, ch)

    return days, totals


def _add_duration(totals, days, start_dt, end_dt, channel):
    """Add duration (in minutes) to the appropriate day bucket(s)."""
    start_date = days[0]
    end_date = days[-1]

    # Clamp to our window
    if end_dt.date() < start_date or start_dt.date() > end_date:
        return

    # Simple case: same day
    if start_dt.date() == end_dt.date():
        d = start_dt.date()
        if d in totals:
            totals[d][channel] += (end_dt - start_dt).total_seconds() / 60.0
        return

    # Spans midnight — split across days
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


def fmt_duration(minutes):
    """Format minutes as 'Xh Ym'."""
    if minutes < 1:
        return "0m"
    h = int(minutes) // 60
    m = int(minutes) % 60
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    if h > 0:
        return f"{h}h"
    return f"{m}m"


def build_page():
    """Build the full HTML page."""
    entries = parse_log()
    days, totals = compute_daily_totals(entries)

    # Find max for scaling the graph
    max_mins = 1  # avoid division by zero
    for d in days:
        for ch in ("THEM", "ME"):
            max_mins = max(max_mins, totals[d][ch])
    # Round up to nearest 30 min for a cleaner scale
    max_mins = max(30, ((int(max_mins) // 30) + 1) * 30)

    today = datetime.date.today()
    day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

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

    # Recent events (last 20)
    recent = entries[-20:]
    recent.reverse()
    recent_html = ""
    for dt, event in recent:
        recent_html += f"<tr><td>{html.escape(dt.strftime('%d %b %H:%M'))}</td><td>{html.escape(event)}</td></tr>\n"

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


class Handler(http.server.BaseHTTPRequestHandler):
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
        # Suppress request logging to avoid noise in journal
        pass


def main():
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
