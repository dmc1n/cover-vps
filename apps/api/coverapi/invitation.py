# ruff: noqa: E501 - the mail layout is HTML with inline styles (mail programs ignore style sheets)
"""The invitation mail (English): what Cover Studio is, how to get in, and the link to choose a
password. Plain text plus the same in a simple layout in the house colours (ADR-054)."""

from __future__ import annotations

import html as _html

SUBJECT = "You are invited to Cover Studio (S2DIO x SUNS)"
OLIVE, SAND, CREAM, INK, MUTED = "#272c23", "#a38e6e", "#fdfbf4", "#1f1f1f", "#6e6a5f"


def _steps(days: int) -> list[str]:
    return [
        f"Open the link below and choose your password (the link works once, for {days} days).",
        "Log in with your user name and that password.",
        "The first time on a computer or phone we send a 6-digit code to this address; "
        "tick 'Remember this device' and you will not be asked again for 14 days.",
    ]


def text(name: str, username: str, link: str, base: str, inviter: str, note: str, days: int) -> str:
    lines = [f"Hello {name},", ""]
    if note:
        lines += [note.strip(), ""]
    lines += [
        f"{inviter} invited you to Cover Studio, the S2DIO x SUNS system that turns a 3D model "
        "or a drawing of a piece of furniture into the cutting patterns for its cover.",
        "",
        "To get in:",
        *[f"  {i}. {s}" for i, s in enumerate(_steps(days), 1)],
        "",
        f"Your user name: {username}",
        f"Choose your password: {link}",
        "",
        f"Cover Studio: {base}",
        f"How the system works (2 minutes): {base}/#/guide",
        "",
        "This link is personal: please do not forward it.",
        "",
        "S2DIO x SUNS",
    ]
    return "\n".join(lines) + "\n"


def html(name: str, username: str, link: str, base: str, inviter: str, note: str, days: int) -> str:
    e = _html.escape
    steps = "".join(f"<li style='margin:0 0 6px'>{e(s)}</li>" for s in _steps(days))
    note_html = (
        f"<p style='margin:0 0 16px;padding:12px 14px;background:#efe7d6;border-radius:8px'>"
        f"{e(note.strip())}</p>"
        if note
        else ""
    )
    return f"""<!doctype html><html><body style="margin:0;background:{CREAM};font-family:Helvetica,Arial,sans-serif;color:{INK}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;border-top:4px solid {SAND}">
<tr><td style="background:{OLIVE};padding:18px 24px;color:{CREAM};font-size:13px;letter-spacing:.08em">S2DIO &times; SUNS
<div style="font-family:Georgia,serif;font-style:italic;font-size:24px;letter-spacing:0;margin-top:4px">Cover Studio</div></td></tr>
<tr><td style="padding:24px;font-size:15px;line-height:1.5">
<p style="margin:0 0 14px">Hello {e(name)},</p>
{note_html}
<p style="margin:0 0 14px">{e(inviter)} invited you to <b>Cover Studio</b>, the S2DIO &times; SUNS system that turns a 3D model or a drawing of a piece of furniture into the cutting patterns for its cover.</p>
<p style="margin:0 0 6px"><b>To get in</b></p>
<ol style="margin:0 0 18px;padding-left:20px">{steps}</ol>
<p style="margin:0 0 18px">Your user name: <b style="font-family:Menlo,Consolas,monospace">{e(username)}</b></p>
<p style="margin:0 0 22px"><a href="{e(link)}" style="display:inline-block;background:{OLIVE};color:{CREAM};text-decoration:none;padding:12px 22px;border-radius:999px;font-weight:bold">Choose your password</a></p>
<p style="margin:0 0 6px;font-size:13px;color:{MUTED}">How the system works, in two minutes: <a href="{e(base)}/#/guide" style="color:{OLIVE}">{e(base)}/#/guide</a></p>
<p style="margin:0;font-size:13px;color:{MUTED}">This link is personal and works once, for {days} days: please do not forward it. If the button does not work, copy this address into your browser:<br><span style="word-break:break-all">{e(link)}</span></p>
</td></tr></table></td></tr></table></body></html>"""
