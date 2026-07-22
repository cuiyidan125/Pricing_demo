# Demo Script

Six beats, about five minutes. Written for a used-vehicle manager or general manager —
lead with dollars and days, not architecture.

**Before you start:** `streamlit run app.py`, open http://localhost:8501, and click
through once so Streamlit's caches are warm. A cold first load runs the whole lot and
takes a few seconds.

The sidebar is organised by the dealer's job, not by ours: **Ask the Dealer AI Assistant**
on top, then **Acquire / Price / Merchandise / Improve Aging Inventory**. If someone asks
where the three skills are, that is the right question — they sit underneath the
workflows, and a workflow can use more than one.

---

## Beat 0 — Open on the assistant (20s)

The app lands on **Ask the Dealer AI Assistant**.

> "This is where a manager starts — a question in their own words, not a form."

Say plainly what it does today: it captures the question and tells you routing is not
connected yet. **Do not mime a conversation.** The honesty is the point, and the sidebar
below it is what the rest of the demo runs on.

---

## Beat 1 — Open on the lot (45s)

Sidebar → **Acquire Inventory**.

> "This is a twelve-car lot on a Tuesday morning. Eighty-six percent full, two open
> slots, three units past ninety days, and three advertised below what they cost."

Point at the two banners:

- `HIGH_PERCENTAGE_BELOW_BREAK_EVEN` — three cars book a loss on sale
- `INBOUND_CAPACITY_CONFLICT` — committed inbound exceeds available slots by one

> "It hasn't recommended anything yet. It's told me what I'd have found out on Friday."

The **Lot** tab is sorted by risk, and risk weights cost basis — so a $45,000 problem
outranks a $9,000 one. That ordering is the point; say so.

---

## Beat 2 — Price a car (75s)

Sidebar → **Price Inventory** → `V-10001 · 2022 Toyota RAV4`.

Open **Ask in plain English** and hit **Extract**.

> "I typed what I'd say out loud. It came back as validated JSON, and look at what
> isn't in it — no price, no valuation, no days-to-sale. Those fields don't exist in
> the extraction schema. The model transcribes; it doesn't decide."

Point at the provenance table: every field marked `USER_STATED` or `MISSING`. Nothing
guessed.

Then the recommendation: **$29,195**, market value $28,400, P50 gross $2,597, 30 days to
sell.

Scroll to **Gross against turn**:

> "Three strategies, one simulation, same seed — so the difference between them is the
> price change, not noise. Maximize Gross wins here: giving up $2,200 of gross to sell
> eleven days sooner doesn't pay on a car this fresh."

---

## Beat 3 — The one that matters (90s)

Still in **Price Inventory**, switch the vehicle to `V-10005 · 2018 BMW 540i · 108d`.

Let the red banner land before saying anything.

> "Break-even is $28,963. The market is $24,900. This car cannot be sold at a profit
> today, and the system won't publish a price for it."

Walk the three `BLOCKING` warnings. Note that each carries the observed value **and** the
threshold — the margin by which the rule was missed, not just that it was missed.

> "Note what it didn't do. It didn't quietly raise the price to the floor to make the
> arithmetic work. It shows what the model recommended and what policy did about it, as
> two separate facts. A car priced into a vacuum above the market doesn't sell — it just
> ages while the loss grows."

Point at **Maximum safe discount: $0** and the required `Loss Minimization` approval.

> "The system quantifies both sides — the loss now against the modelled cost of holding.
> It doesn't decide. That's the manager's call, and it needs a signature."

**This is the beat the demo is for.** A tool that only ever says "price it here" is a
calculator.

---

## Beat 4 — Work the whole lot (75s)

Sidebar → **Merchandise Inventory**. Event: **Summer Clearance**. Target: **70%**.

> "I want the lot at seventy percent by the end of a five-day event."

Verdict first: **Not Achievable**.

> "It needs four incremental sales in five days. The most aggressive safe plan gets about
> half a car. It's telling me no — and then telling me what would work."

Show the quantified alternatives: extend the campaign, revise the target, or wholesale
four units.

Then the **Excluded** tab — this is the sharpest observation in the demo:

> "Four cars are excluded for `NO_SAFE_HEADROOM`, and they're the aged ones. The cars I
> most want to move are exactly the ones I can't legally discount, because they're
> already at or below their floor. That tension is real, and most tools hide it."

Drag the target to **85%** to show the verdict change.

---

## Beat 5 — Show the receipts (30s)

Back to **Price Inventory** → **Assumptions and audit trail**.

> "Every MCP call with its timestamp, the simulation seed, the assumption version, the
> percentile convention."

Then the last table:

> "And this is the only thing the explanation layer is allowed to quote from. If the model
> writes a number that isn't in this list, the response is thrown away rather than shown
> to you."

---

## Questions you should expect

**"Are these numbers real?"**
No. Synthetic dealer, synthetic market. The forecast is a configured simulation labelled
as one, not a trained model. The architecture is the deliverable; the numbers demonstrate
it.

**"Where does the market value come from?"**
vAuto anchors it. An independent comparable-based estimate runs alongside every time, and
disagreement widens the range and lowers confidence — it never silently averages the two.

**"What's the least trustworthy part?"**
Price elasticity. It alone decides every velocity-versus-gross tradeoff and it isn't
calibrated. It's one file, and it's labelled.

**"What does Improve Aging Inventory do?"**
Nothing yet, and the page says so. It is the fourth workflow and the reason the
architecture is built this way: it coordinates all three skills against aged units rather
than being a fourth skill. Today it shows the six-step sequence and which capability
serves each step. Say that plainly — the page will contradict you otherwise.

**"Can I just ask it a question?"**
Not yet. The assistant captures the question and tells you routing is not connected. The
workflows in the sidebar are what runs today.

**"Could the AI just make up a price?"**
Two independent guards, both tested. The calculation layer can't import a model, and any
figure in generated prose that the engine didn't produce gets the response discarded. Show
the guard test if they want it.
