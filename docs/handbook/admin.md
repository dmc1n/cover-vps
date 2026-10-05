# Users, approvals and the admin page

Cover Studio is on the internet at **https://covers.suns.nu**. Everyone logs in with their own
account; nothing can be seen or changed without one.

## Logging in for the first time

An admin makes your account and sends you an invitation in English (by mail when the mail
server is set, or the link copied by hand). It says what Cover Studio is, gives your user name
and a personal link, valid for 7 days, that works once. Open it, choose a password of at least
12 characters (not your user name), and you are logged in. Forgot your password? Ask an admin
(Admin → Users → Reset password, then confirm); the old password stops working.

## Inviting people (for example for a kickoff)

Admin → Users:

1. Add everyone (user name, name, e-mail, role, may approve). Untick **send the invitation
   now** to add people first and invite them all at once later.
2. Optional: write a line for the top of the mail in **Invitations**, for example the date and
   time of the kickoff.
3. **Invite everyone not yet in** sends the invitation to everyone with an e-mail address and no
   password yet. **Send invitation** in the list sends it to one person; **Send again** gives a
   new link (the old one stops working).

The column **Access** shows who has a password, who is invited (and until when the link works)
and who is not invited yet. The invitation links to the short guide **How Cover Studio works**
(#/guide, readable without logging in).

After five wrong passwords your account waits 15 minutes; ten wrong tries from one address
block that address for a while.

## Roles and rights

| role | may |
|---|---|
| viewer | look at everything and download files |
| editor | also upload models, calculate, change settings and seams |
| admin | also the admin page: users, rights, mail, address, logins, audit log |

Besides the role, an admin sets per user **may approve**: only those users can approve the
definitive drawing of a cover.

## Approving the definitive drawing

On every model with cut pieces there is a block at the top:

- **not approved yet**: an approver presses *Approve the definitive drawing* (with a note if
  wanted). The approval belongs to the current revision. *Approved size drawing* and *Approved
  cutting list* are copies with "APPROVED name date revision" on every page.
- **approved by … on …**: the cover may be cut. Its status is *production*.
- **changed after the approval**: the cover was calculated again and the files are different;
  approve again before cutting.

An editor who may not approve presses *Ask for approval*: the approvers get a mail with the
link. Status *production* can only be set with a valid approval.

## The admin page (Admin in the header)

- **Users**: add, change role, may approve, active (an inactive user is logged out at once),
  e-mail; *New link* / *Reset* makes a password link (shown to copy, and mailed when possible).
- **Mail and address**: the outgoing mail server (SMTP: server, port, security, user name,
  password, sender), a test mail; the public address used in links.
- **Logged in**: who is logged in, since when and from where.
- **Audit log**: every login, failed login, change, approval, with who and when.
- **System**: version, disk, last backup, mail and AI state, open problems, the alert address
  (mails when the server has a problem) and the last alerts.

## From the command line (the server)

```
COVER_DATA_DIR=~/cover-data uv run cover-users list
COVER_DATA_DIR=~/cover-data uv run cover-users add <name> --name "Full Name" --email … \
    --role editor [--approve]
COVER_DATA_DIR=~/cover-data uv run cover-users invite <name>      # a new password link
```

## The drape simulation (3D view)

**Drape simulation** sews the cut pieces virtually and drops them over the furniture (and the
balloons and chairs of a table), with Newton's Style3D garment solver. It takes about 40
minutes for a sofa, in a queue of its own, so other work goes on meanwhile. Every new model gets
it by itself after its calculation; the result is kept with the model and in the nightly
backup. **Drape** then plays the fall
and shows the cover as it lies.

The fall is followed by a short settling phase: the cover comes to rest, so what you see is the
shape it keeps, not a moment in the fall. Sewn seams bend less easily than the plain fabric, as
on a real cover.

- **Red** shows folds: there the piece has more fabric than the shape needs.
- The card below gives:
  - the fold area;
  - the tightest spot;
  - how far the top sags below the designed surface;
  - how much of the cover lies on the furniture.

**Back to the design** shows the designed surface again. The fabric values are estimates until
the fabric has been measured.

## Water on the cover as it lies (heatmap)

After the drape simulation the rain falls on the cover as it really lies.

- In the 3D view, choose **Drape**, then switch **Water** on. The cover is coloured:
  - **sage**: water runs off;
  - **amber**: water streams past;
  - **orange**: flat, water stands;
  - **red**: a pond (darker is deeper).
- The card gives the number of ponds, the litres and the deepest point, and whether a pond
  keeps growing under its own weight.

The rain on the designed surface (the **Rain** button) stays, to compare.

## The cover webshop

The shop is at **/shop/**: the landing page, the configurator, checkout and the order status.
Three tabs on the admin page belong to it.

- **Shop settings:** everything the shop needs:
  - company data and domain;
  - prices (tick *confirmed* to drop "indicative");
  - delivery costs per country;
  - the Mollie key (`test_…` to try, `live_…` for real);
  - the balloon and frame products, colours, and the film's address.

  The empty fields are listed at the top.
- **Website (AI):** type what should change on the site, in plain words, for example "add a
  question about delivery time: about three weeks". The AI changes the draft in Dutch and
  English. Open the preview, then **Publish** (or **Discard**). Earlier versions can be
  brought back. The same works on the server: `cover-site "…"`, `cover-site --publish`.
  Colleagues with the editor role find the same command line under **Website** at the top
  right: they draft and check the preview; an admin publishes.
- **Orders:** every order with its customer, cover, total and status.
  - A paid order goes into production by itself: its pattern, then the drape. **Into
    production** does it by hand (for a payment by bank transfer).
  - Changing the status mails the customer.

## Matches: which existing cover fits (learning mode)

- **The customer enters their sizes in the configurator.**
  - **Learning mode** (Shop settings, matching, mode `shadow`; the default): the customer leaves
    an e-mail address. You get a mail, and the request appears in the admin tab **Matches**
    with the best covers, their percentage and the difference per size in cm (+ is roomier).
  - Press **Take N %** for the proposal, **Custom**, or type another cover (`suns-…`) and press
    **Choose**. A note for the customer is optional.
  - The customer gets a link to the proposal, in their own language, and can order the existing
    cover or a custom one.
- **Every change you make is a lesson.** The table **What we learn** shows, per match band,
  how often the proposal was changed, the fit answers of customers (1–5) and the returns.
  When a band fits well, set the threshold (Shop settings, matching, `threshold_pct`) and,
  when you trust it, mode `auto`: customers then see the match at once.
- **The fit question:** Shop settings, `fit_mail`. Switch it on and set the days. It needs the
  domain and the mail server. A shipped order then gets one question by mail; the answers
  appear under Matches.

## Languages

- Shop settings, `languages`: for example `nl,en,de,fr`. The first is the main language.
- Website (AI), **Translate missing languages**: DeepSeek fills them into the draft. Check the
  preview (switch the language at the top right), then **Publish**.
- Every text, buttons included, can be changed by an instruction in the command line, in all
  languages at once.
