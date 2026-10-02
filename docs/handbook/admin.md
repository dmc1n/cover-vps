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
balloons of a table). It takes a few minutes, in the background. **Drape** then plays the fall
and shows the cover as it lies.

- **Red** shows folds: there the piece has more fabric than the shape needs.
- The card below gives:
  - the fold area;
  - the tightest spot;
  - how far the top sags below the designed surface;
  - how much of the cover lies on the furniture.

**Back to the design** shows the designed surface again. The fabric values are estimates until
the fabric has been measured.
