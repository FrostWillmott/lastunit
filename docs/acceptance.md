# Spec

The text of the assignment. The "Expected behaviour" section is numbered: the
"State" table in `README.md` refers to these numbers (bullet → test → status).

Source: the test assignment as received, translated from Russian. Headings and
numbering were added; nothing else was. The Russian original is this file under
the tag `submission-2026-09-14`. In the original, "Expected behaviour" has nine
bullets.

## Requirements

The same for every task.

1. A client-server product: a separate backend and a separate frontend that
   talk over the network.
2. Backend: Python, Go or Node.js. These are preferred, not mandatory. If there
   were good reasons for the choice of language, libraries and tools, describe
   them.
3. Frontend: Vue or React.
4. Storage: a relational DBMS. PostgreSQL, MySQL or any equivalent of your
   choice, PostgreSQL preferred.
5. Accounts and sign-in are up to you, including the sign-in model. Login and
   password is enough, and so is no sign-in at all.
6. Prompts or a decision log are handed in with the code: why the project is
   built this way and not another, why these packages and approaches were
   chosen. What exactly and in what form is in "What we expect from you".
7. Use of AI agents is expected. We assume the project is built together with
   an agent, which is why we ask for the prompts. There is no need to hide it.
8. The prerequisites for deploying the project are described.
9. Local run. The project is quick to bring up locally.
10. External services may be emulated. Mail, third-party APIs and the like can
    be replaced with stubs.
11. Works with two clients open at the same time (for example, two browser
    tabs).
12. An honest description of the project's state: what works, what doesn't,
    what was not done and why.
13. Provability. The project must prove that it works.

## What we expect from you

When the work is done, we expect from you:

1. A link to the project repository on GitHub.
2. What you built it with: which model, which tool. And why those, in a couple
   of sentences.
3. Prompts, a decision log or an export of the agent session. The export is the
   file your tool produces (jsonl or similar); we will treat it with care. If
   you would rather not hand over the export, a decision log or a development
   journal will do.
4. The course of the work over time. We want to see that the work happened
   gradually rather than delivered in one go: from the commit history, the
   session log or the decision log. Record timestamps from the start of the
   work to the end and along the way. Ask the agent to do this.
5. A description of the project: how to deploy it and what state it is in.
6. What you would do in the next round: what did not fit into the scope but
   you consider necessary.
7. If you built on someone else's solution, template or generator, say so.

## Task: Flash sale

The product is a limited-sale service: a shop lists a batch of goods at a
special price for a short time, and there are more buyers than goods. The
payment system is any of your choice (in test mode, or your own stub).

### Must include

- Sale: product, price, quantity, start and end time.
- Storefront with stock and a timer.
- Cart: the item is held for the buyer for 10 minutes until payment.
- Payment through a payment stub that can confirm, decline or "hang".
- Buyer's account: orders and their status.
- Shop screen: stock, sold, in carts, revenue.

### Expected behaviour

1. Nothing can be bought before the start, even if the page was opened in
   advance. At the start, buying opens for everyone at the same moment.
2. Stock on the storefront changes for everyone watching it, without a page
   reload.
3. The last unit cannot be sold to two buyers at once: one gets the item, the
   other gets "sold out".
4. An item in the cart is held for 10 minutes. Not paid — it goes back to the
   storefront, and everyone else sees it immediately.
5. A payment started before the hold expires completes, even if the stub
   answers after that.
6. The stub "hung" — the order is pending, the item does not return to the
   storefront and is not sold twice. When the stub answers, the order is
   settled.
7. A double click on "pay" does not create two orders and does not charge
   twice.
8. The buyer gets an email about the order. One.
9. When the sale ends, unsold stock is withdrawn, unpaid carts are cleared, and
   their owners are notified.
