"""Browser check of every Desk action (14 Oct 2026: "Approve on the Desk seems to do nothing").

An approval stamps the size drawing and the cutting list into approved/, which takes seconds;
the button gave no sign, the list and its counts did not follow in time, and people clicked
again. Per browser (Chromium, WebKit, Firefox) and width (1440, 1024 as an iPad touch screen)
this checks, as an approver:

- Approve (the button) on an "AI checked" card and on a rejected card: the button busy at once
  ("Approving…"), a message when done, the counts (Approved +1, To review or Rejected -1) and
  the list (the cover leaves To do) refreshed, the next card of the list opened;
- the key `a` the same way;
- Reject (a reason, words): Rejected +1, the next card;
- Comment: a message, the list refreshed, the card stays, "Not changed yet" on its row;
- a refusal is never silent: a cover approved behind the page's back, then Approve → the
  server's 409 reason ("already approved by …") on the screen;
- an order's quick approval in the queue: busy, message, the order leaves To do, Approved +1;
- the filters (Rens, 14 Oct 2026): "2nd round" only covers changed after a remark that wait
  again (new or AI checked), "Waiting for us" exactly the covers with an open remark (the
  rule of scripts/desk_open_remarks.py), their rows marked "Not changed yet".

It changes the Desk: run it against a scratch copy of the data (never the live data). The
quick approval needs orders on the Desk; mark some first, on the host (refuses ~/cover-data):

    COVER_DATA_DIR=<scratch data> uv run python apps/web/e2e/desk_actions.py --prepare 6

then, with the scratch studio running:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/deskactions:/shots" \\
      -e COVER_E2E_URL=http://127.0.0.1:18295 \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/desk_actions.py"

COVER_E2E_BROWSERS, COVER_E2E_WIDTHS, COVER_E2E_USER (an approver, default wout) and
COVER_E2E_PASSWORD choose; screenshots go to $COVER_E2E_SHOTS (default /shots).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18295")
BROWSERS = os.environ.get("COVER_E2E_BROWSERS", "chromium,webkit,firefox").split(",")
WIDTHS = [int(w) for w in os.environ.get("COVER_E2E_WIDTHS", "1440,1024").split(",")]
TOUCH = {1024}  # the iPad width runs as a touch screen
USER = os.environ.get("COVER_E2E_USER", "wout")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
SLOW = 150_000  # an approval stamps PDFs (a size drawing may be made first): seconds to a minute
STEP = 30_000


def prepare(n: int) -> int:
    """Mark n built, AI-checked covers as orders sent to production (scratch data only)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
    from coverapi import desk

    data = Path(os.environ.get("COVER_DATA_DIR", "")).expanduser().resolve()
    live = (Path.home() / "cover-data").resolve()
    if not data.is_dir() or data == live or live in data.parents:
        print(f"refused: COVER_DATA_DIR must be a scratch copy, not {data}")
        return 2
    models = data / "models"
    done = 0
    base = 90000 + int(time.time()) % 10000 * 10
    for d in sorted(models.iterdir(), reverse=True):  # from the end: not the first cards
        if done >= n:
            break
        if not (d / "desk.json").is_file() or not (d / "cut.dxf").is_file():
            continue
        st = desk.state(d)
        if st["status"] != "ai-checked" or st.get("order") or desk.no_cover(d):
            continue
        number = base + done  # a new number each run
        desk.mark_order(d, number, "e2e", data / "learning")
        print(f"order {number}: {d.name}")
        done += 1
    print(f"{done} orders on the Desk")
    return 0 if done == n else 1


# ---- the browser part ------------------------------------------------------------------------


async def login(page: Any) -> None:
    from playwright.async_api import expect

    await page.goto(f"{URL}/#/")
    await page.get_by_label("User name").fill(USER)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible(timeout=STEP)


async def queue(page: Any) -> dict[str, Any]:
    r = await page.request.get(f"{URL}/api/desk")
    assert r.ok, f"GET /api/desk {r.status}"
    return dict(await r.json())


async def kpis(page: Any) -> dict[str, int]:
    rows = await page.evaluate(
        """[...document.querySelectorAll('.d-kpi')].map(e => [
            e.querySelector('.d-kpi-label')?.innerText.trim(),
            e.querySelector('.d-kpi-value')?.innerText.trim()])"""
    )
    return {k: int(v) for k, v in rows if k and v and re.fullmatch(r"\d+", v)}


async def list_ids(page: Any) -> list[str]:
    return list(
        await page.eval_on_selector_all(".d-list li[data-id]", "els => els.map(e => e.dataset.id)")
    )


async def wait_kpis(page: Any, want: dict[str, int], what: str) -> None:
    end = time.monotonic() + STEP / 1000
    got: dict[str, int] = {}
    while time.monotonic() < end:
        got = await kpis(page)
        if all(got.get(k) == v for k, v in want.items()):
            return
        await page.wait_for_timeout(250)
    raise AssertionError(f"{what}: counts {got}, wanted {want}")


async def show(page: Any, flt: str) -> None:
    await page.locator(f".d-seg-ctl button[data-filter='{flt}']").click()


async def open_card(page: Any, mid: str, code: str) -> str | None:
    """The card in the To do list; returns the id of the card after it in that list."""
    from playwright.async_api import expect

    await show(page, "open")
    await page.evaluate("id => { location.hash = '#/work/desk/' + id }", mid)
    await expect(page.locator(".d-card-head h2")).to_have_text(code, timeout=STEP)
    await expect(page.locator(f".d-list li[data-id='{mid}']")).to_have_class(re.compile("sel"))
    ids = await list_ids(page)
    k = ids.index(mid)
    return ids[k + 1] if k + 1 < len(ids) else None


async def toast(page: Any, kind: str, text: str) -> str:
    from playwright.async_api import expect

    t = page.locator(f"[data-testid=desk-toast].t-{kind}")
    await expect(t).to_contain_text(text, timeout=SLOW)
    return str(await t.locator("span").first.inner_text())


async def busy_seen(page: Any, locator: Any) -> bool:
    """The control says it is working, or the action was already done (a fast server)."""
    for _ in range(40):
        txt = await locator.inner_text() if await locator.count() else ""
        if "Approving" in txt:
            return True
        if await page.locator("[data-testid=desk-toast].t-ok").count():
            return True
        await page.wait_for_timeout(25)
    return False


class Run:
    def __init__(self, page: Any, label: str) -> None:
        self.page = page
        self.label = label
        self.problems: list[str] = []
        self.posts: list[str] = []
        self.queue_gets = 0
        page.on("request", self._req)

    def _req(self, r: Any) -> None:
        u = r.url.replace(URL, "")
        if r.method == "POST" and u.startswith("/api/desk/"):
            self.posts.append(u)
        if r.method == "GET" and u.split("?")[0] == "/api/desk":
            self.queue_gets += 1

    def check(self, ok: bool, what: str) -> None:
        print(f"  {'ok ' if ok else 'BAD'} {self.label}: {what}", flush=True)
        if not ok:
            self.problems.append(f"{self.label}: {what}")

    async def shot(self, name: str) -> None:
        await self.page.screenshot(path=f"{SHOTS}/{self.label}-{name}.png")


async def approve(run: Run, item: dict[str, Any], how: str) -> None:
    page = run.page
    from playwright.async_api import expect

    nxt = await open_card(page, item["id"], item["code"])
    before = await kpis(page)
    gets = run.queue_gets
    btn = page.locator("[data-testid=desk-approve]")
    await expect(btn).to_be_enabled()
    if how == "key":
        await page.locator(".d-card-head h2").click()  # no field has the focus
        await page.keyboard.press("a")
    else:
        await btn.click()
    run.check(await busy_seen(page, btn), f"{how} approve {item['code']}: busy at once")
    msg = await toast(page, "ok", f"Approved: {item['code']}")
    run.check(True, f"{how} approve {item['code']} ({item['status']}): '{msg.strip()[:60]}'")
    want = {"Approved": before["Approved"] + 1}
    if item["status"] == "rejected":
        want["Rejected"] = before["Rejected"] - 1
    else:
        want["To review"] = before["To review"] - 1
    await wait_kpis(page, want, f"{how} approve {item['code']}")
    run.check(run.queue_gets > gets, f"{how} approve: the list was fetched again")
    run.check(item["id"] not in await list_ids(page), f"{how} approve: {item['code']} left To do")
    if nxt:
        await expect(page).to_have_url(re.compile(f"#/work/desk/{re.escape(nxt)}"), timeout=STEP)
        run.check(True, f"{how} approve: next card {nxt} opened")
    st = (await queue(page))["items"]
    run.check(
        next(i for i in st if i["id"] == item["id"])["status"] == "approved",
        f"{how} approve: the server has it approved",
    )


async def reject(run: Run, item: dict[str, Any]) -> None:
    page = run.page
    from playwright.async_api import expect

    nxt = await open_card(page, item["id"], item["code"])
    before = await kpis(page)
    await page.locator("[data-testid=desk-reject]").click()
    await page.locator(".d-reject .d-chips button").first.click()
    await page.locator(".d-reject textarea").fill("e2e: desk_actions reject")
    await page.locator("[data-testid=desk-dialog-send]").click()
    await toast(page, "ok", f"Rejected: {item['code']}")
    await wait_kpis(
        page,
        {"Rejected": before["Rejected"] + 1, "To review": before["To review"] - 1},
        f"reject {item['code']}",
    )
    row = page.locator(f".d-list li[data-id='{item['id']}']")
    await expect(row.locator(".d-pill")).to_contain_text("Rejected", timeout=STEP)
    run.check(True, f"reject {item['code']}: counts and its row follow")
    if nxt:
        await expect(page).to_have_url(re.compile(f"#/work/desk/{re.escape(nxt)}"), timeout=STEP)
        run.check(True, f"reject: next card {nxt} opened")


async def comment(run: Run, item: dict[str, Any]) -> None:
    page = run.page
    from playwright.async_api import expect

    await open_card(page, item["id"], item["code"])
    before = await kpis(page)
    gets = run.queue_gets
    await page.locator("[data-testid=desk-comment]").click()
    await page.locator(".d-reject textarea").fill("e2e: desk_actions comment")
    await page.locator("[data-testid=desk-dialog-send]").click()
    await toast(page, "ok", f"Comment saved: {item['code']}")
    await expect(page.locator(".d-card-head h2")).to_have_text(item["code"])
    for _ in range(40):
        if run.queue_gets > gets:
            break
        await page.wait_for_timeout(100)
    run.check(run.queue_gets > gets, f"comment {item['code']}: the list was fetched again")
    run.check(await kpis(page) == before, "comment: the counts stay")
    row = page.locator(f".d-list li[data-id='{item['id']}']")
    await expect(row).to_contain_text("Not changed yet", timeout=STEP)
    await expect(page.locator(".d-card-head")).to_contain_text("Not changed yet")
    run.check(True, "comment: 'Not changed yet' on its row and its card")


async def refused(run: Run, item: dict[str, Any]) -> None:
    """Approved behind the page's back, then Approve: the 409's reason on the screen."""
    page = run.page
    from playwright.async_api import expect

    await open_card(page, item["id"], item["code"])
    r = await page.request.post(f"{URL}/api/desk/{item['id']}", data={"action": "approve"})
    assert r.ok, f"approve by API {r.status}"
    await page.locator("[data-testid=desk-approve]").click()
    msg = await toast(page, "err", "refused")
    run.check("already approved" in msg, f"refusal shown: '{msg.strip()[:90]}'")
    await expect(page.locator("[data-testid=desk-msg]")).to_contain_text("already approved")
    await expect(page.locator("[data-testid=desk-approve]")).to_be_disabled(timeout=STEP)
    run.check(True, "refusal: the card reloaded as approved")
    await expect(page.locator(f".d-list li[data-id='{item['id']}']")).to_have_count(0, timeout=STEP)
    run.check(True, "refusal: the list refreshed (the cover left To do)")


async def quick(run: Run, item: dict[str, Any]) -> None:
    page = run.page
    from playwright.async_api import expect

    await show(page, "open")
    before = await kpis(page)
    row = page.locator(f".d-list li[data-id='{item['id']}']")
    btn = row.locator("[data-testid=desk-quick-approve]")
    await btn.click()
    run.check(await busy_seen(page, btn), f"quick approve order {item['order']['order']}: busy")
    await toast(page, "ok", f"Approved order {item['order']['order']}")
    await wait_kpis(
        page,
        {"Approved": before["Approved"] + 1, "To review": before["To review"] - 1},
        "quick approve",
    )
    await expect(row).to_have_count(0, timeout=STEP)
    run.check(True, f"quick approve {item['code']}: counts, and it left To do")


async def filters(run: Run) -> None:
    page = run.page
    from playwright.async_api import expect

    q = (await queue(page))["items"]
    by = {i["id"]: i for i in q}
    await show(page, "second")
    await page.wait_for_timeout(300)
    ids = await list_ids(page)
    bad = [
        i for i in ids if not (by[i]["second_round"] and by[i]["status"] in ("new", "ai-checked"))
    ]
    run.check(not bad, f"2nd round: {len(ids)} covers, all waiting again {bad[:3]}")
    await show(page, "waiting")
    await page.wait_for_timeout(300)
    ids = await list_ids(page)
    want = {i["id"] for i in q if i["open_remark"]}
    run.check(
        set(ids) == want, f"Waiting for us: {len(ids)} covers = the open remarks ({len(want)})"
    )
    if ids:
        await expect(page.locator(f".d-list li[data-id='{ids[0]}']")).to_contain_text(
            "Not changed yet"
        )
    label = await page.locator(".d-seg-ctl button[data-filter='waiting']").inner_text()
    run.check(str(len(want)) in label, f"Waiting for us shows its number ({label.strip()})")
    await show(page, "open")


async def one(pw: Any, browser_name: str, width: int) -> list[str]:
    browser = await getattr(pw, browser_name).launch()
    ctx = await browser.new_context(
        viewport={"width": width, "height": 900 if width > 1100 else 1366},
        has_touch=width in TOUCH,
    )
    page = await ctx.new_page()
    label = f"{browser_name}-{width}"
    run = Run(page, label)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"page error: {e}"))

    def on_console(m: Any) -> None:
        if m.type == "error":
            errors.append(f"console: {m.text} ({m.location.get('url', '')})")

    page.on("console", on_console)
    try:
        await login(page)
        await page.goto(f"{URL}/#/work/desk")
        await page.locator(".d-list li[data-id]").first.wait_for(timeout=STEP)
        q = (await queue(page))["items"]
        plain = [
            i for i in q
            if i["status"] == "ai-checked" and i["built"] and not i.get("order")
            and not i["arrangement"] and not i["no_cover"]
        ]  # fmt: skip
        plain = plain[len(plain) // 3 :]  # not the first ones: other checks look at those
        rejected = [
            i for i in q if i["status"] == "rejected" and i["built"] and not i["arrangement"]
        ]
        orders = [i for i in q if i.get("order") and i["built"] and i["status"] == "ai-checked"]
        assert len(plain) >= 5, "too few AI-checked covers left: a fresh scratch copy"
        await filters(run)
        await approve(run, plain[0], "button")
        await run.shot("approved")
        if rejected:
            await approve(run, rejected[0], "button")
        else:
            run.check(False, "no rejected cover left to approve: a fresh scratch copy")
        await approve(run, plain[1], "key")
        await reject(run, plain[2])
        await comment(run, plain[3])
        await run.shot("comment")
        await refused(run, plain[4])
        await run.shot("refused")
        if orders:
            await quick(run, orders[0])
        else:
            run.check(False, "no order on the Desk: run --prepare first")
    except Exception as exc:  # noqa: BLE001 - one combination's failure, the rest still run
        run.problems.append(f"{label}: {type(exc).__name__}: {str(exc)[:300]}")
        try:
            await run.shot("failed")
        except Exception:  # noqa: BLE001
            pass
    # the one expected console error: the session probe before the login (401 on /api/auth/me)
    other = [e for e in errors if not ("401" in e and "auth/me" in e)]
    other = [e for e in other if "WebGL" not in e and "GL Driver" not in e]
    # the refusal step's 409 is the point of that step (its message is checked there)
    other = [e for e in other if not ("409" in e and "/api/desk/" in e)]
    if other:
        run.problems.append(f"{label}: {other[:3]}")
    await browser.close()
    return run.problems


async def main() -> int:
    from playwright.async_api import async_playwright

    problems: list[str] = []
    async with async_playwright() as pw:
        for b in BROWSERS:
            for w in WIDTHS:
                print(f"== {b} {w}", flush=True)
                problems += await one(pw, b, w)
    print("\n".join(problems) if problems else "all Desk actions fine")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--prepare":
        raise SystemExit(prepare(int(sys.argv[2])))
    raise SystemExit(asyncio.run(main()))
