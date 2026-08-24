"""make_paste_kit: one self-contained HTML page per system for manual UI runs.

Each prompt becomes a card with a [Copy prompt] button and the exact target
answer file (runs/<condition>/<system>/<ITEM>.md), so answers cannot be
mis-filed. Cards whose answer file is already non-empty show a DONE badge —
regenerate the page to refresh badges. Prompts are embedded verbatim
(HTML-escaped) in hidden textareas; nothing is fetched at view time.

Usage:
  .venv/bin/python tools/make_paste_kit.py --system s6-opus
  .venv/bin/python tools/make_paste_kit.py --system s2-gpt
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path

from chi_edge_bench.paths import exports_dir, prompts_dir, runs_dir
CONDITIONS = ("blind", "matched", "heldout", "uncovered")
PILOT = ("P16", "N17", "AV01")

CSS = """
body{font-family:-apple-system,Segoe UI,sans-serif;margin:0;background:#f5f6f8;color:#1a1d21}
header{background:#1a1d21;color:#fff;padding:18px 28px}
header h1{margin:0 0 6px;font-size:20px} header p{margin:2px 0;font-size:13px;color:#c8cdd4}
main{max-width:960px;margin:0 auto;padding:20px 28px 80px}
h2{margin:34px 0 6px;font-size:17px;border-bottom:2px solid #d8dce2;padding-bottom:6px}
.hint{font-size:13px;color:#555;margin:0 0 14px}
.card{background:#fff;border:1px solid #dde1e7;border-radius:8px;padding:12px 16px;margin:10px 0;
      display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.card.done{opacity:.55;background:#eef7ee;border-color:#bcd9bc}
.id{font-weight:700;font-size:15px;min-width:52px}
.target{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#444;flex:1;min-width:260px;
        overflow-wrap:anywhere}
.size{font-size:12px;color:#888}
.badge{font-size:11px;font-weight:700;color:#2e7d32;border:1px solid #2e7d32;border-radius:10px;
       padding:1px 8px}
.pilot{font-size:11px;font-weight:700;color:#b26a00;border:1px solid #b26a00;border-radius:10px;
       padding:1px 8px}
button{background:#2457d6;color:#fff;border:0;border-radius:6px;padding:7px 14px;font-size:13px;
       cursor:pointer} button:active{background:#173e9e}
button.copied{background:#2e7d32}
details{width:100%} summary{font-size:12px;color:#666;cursor:pointer}
details pre{white-space:pre-wrap;font-size:11px;background:#f0f1f4;padding:10px;border-radius:6px;
            max-height:320px;overflow:auto}
textarea.src{display:none}
.protocol{background:#fff8e6;border:1px solid #e6cf8f;border-radius:8px;padding:12px 18px;
          font-size:13px;margin:18px 0} .protocol li{margin:4px 0}
"""

JS = """
function cp(btn){
  var ta = document.getElementById(btn.dataset.t);
  function ok(){ btn.textContent='Copied ✓'; btn.classList.add('copied');
    setTimeout(function(){btn.textContent='Copy prompt'; btn.classList.remove('copied');}, 1800); }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(ta.value).then(ok, function(){ legacy(); });
  } else { legacy(); }
  function legacy(){ ta.style.display='block'; ta.select();
    try { document.execCommand('copy'); ok(); } finally { ta.style.display='none'; } }
}
"""

PROTOCOL = """
<div class=protocol><b>Protocol — read once, follow every time</b>
<ol>
<li><b>Fresh chat per item.</b> Never reuse a conversation; history contaminates.</li>
<li><b>Web search OFF, memory/custom-instructions OFF</b> (use a temporary chat if the UI has one).
    Web access would silently un-blind the blind condition.</li>
<li>Pin one model in the picker and never change it mid-system; record it in
    <code>system_note.json</code> (model label, thinking on/off, dates).</li>
<li>Copy the prompt with the button below, paste as the only message, send.</li>
<li>Copy the model's <b>entire response</b> with the UI copy button (not drag-select,
    not a code-block copy button), paste verbatim into the target file shown on the card.
    Do not edit, trim, or reformat.</li>
<li><b>Never paste into a file that already has content.</b> DONE badges mark filled files
    (regenerate this page to refresh them).</li>
<li>If a long paste turns into a file attachment in the UI, note it in system_note.json
    — for ChatGPT this may route the material through file tools instead of raw context.</li>
<li>Do the three PILOT-tagged items first, then have the answers scored before bulk pasting.</li>
</ol></div>
"""


def build(system: str) -> str:
    parts = [f"<title>Paste kit — {system}</title><style>{CSS}</style>",
             f"<header><h1>Benchmark v4 paste kit — {html.escape(system)}</h1>",
             "<p>One card = one prompt = one fresh chat = one target file.</p>",
             "<p>Regenerate after pasting to refresh DONE badges: "
             f"<code>tools/make_paste_kit.py --system {html.escape(system)}</code></p></header>",
             "<main>", PROTOCOL]
    total = done_n = 0
    for cond in CONDITIONS:
        prompt_files = sorted((prompts_dir() / cond).glob("*.txt"))
        if not prompt_files:
            continue
        parts.append(f"<h2>{cond} — {len(prompt_files)} prompts</h2>")
        parts.append("<p class=hint>Target directory: "
                     f"<code>runs/{html.escape(cond)}/{html.escape(system)}/</code></p>")
        for pf in prompt_files:
            stem = pf.stem
            text = pf.read_text(encoding="utf-8")
            target = runs_dir() / cond / system / f"{stem}.md"
            done = target.exists() and target.stat().st_size > 0
            total += 1
            done_n += done
            tid = f"ta-{cond}-{stem}"
            badges = ""
            if done:
                badges += "<span class=badge>DONE</span>"
            if stem in PILOT and cond == "blind":
                badges += "<span class=pilot>PILOT FIRST</span>"
            parts.append(
                f"<div class='card{' done' if done else ''}'>"
                f"<span class=id>{html.escape(stem)}</span>"
                f"<span class=target>runs/{html.escape(cond)}/{html.escape(system)}/"
                f"{html.escape(stem)}.md</span>"
                f"<span class=size>{len(text):,} chars</span>{badges}"
                f"<button data-t='{tid}' onclick='cp(this)'>Copy prompt</button>"
                f"<details><summary>view prompt</summary><pre>{html.escape(text)}</pre></details>"
                f"<textarea id='{tid}' class=src>{html.escape(text)}</textarea>"
                "</div>")
    parts.append(f"<p class=hint>{done_n}/{total} answered at generation time.</p>")
    parts.append(f"</main><script>{JS}</script>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--system", default="s6-opus",
                    help="target system dir under runs/ (default s6-opus)")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    out = Path(args.out) if args.out else exports_dir() / f"paste_kit_{args.system}.html"
    out.write_text(build(args.system), encoding="utf-8")
    print(f"[written] {out}")


if __name__ == "__main__":
    main()
