# AI Warranty Claim Checker — Live Tests

Workflow: **AI Warranty Claim Checker** — JSON built, NOT yet imported
Builder: ~/workspace/linkedin/staged/2026-11-23/build-warranty-checker.py
JSON: ~/workspace/linkedin/staged/2026-11-23/warranty-checker.json (validated: valid JSON, all connections resolve, no Gmail/Sheets/HTTP-Request nodes, Respond responseBody starts with `={{ `, Groq maxTokens 8000)
Editor (after import): https://chuck-jumbo-compress.ngrok-free.dev
Production webhook (after activation): https://chuck-jumbo-compress.ngrok-free.dev/webhook/warranty
Active: NO — the run must import, then activate from the editor, then run these tests.

## Design (13 nodes in the file — 12 enumerated steps + 1 shared Groq Chat Model)
The posts-log counts 12 because it excludes the sticky note; nothing is missing.
1. README Note (sticky, 420x280, 280 chars — kept short so it displays fully)
2. New Warranty Query (Webhook POST /warranty: name, message)
3. Validate Query (Code — message non-empty and > 5 chars)
4. Parse Claim (AI Agent + Groq — extracts product + purchase_date as one-line JSON; prompt carries a one-line JSON example + "Output ONLY that one-line JSON object, no thinking, no preamble, no explanation"; today is given as 2026-11-23 so relative dates like "3 months ago" convert to an exact date)
5. Parse Claim JSON (Code — parses the agent's JSON text; REGEX-SALVAGE fallback recovers product/purchase_date from truncated JSON, same lesson as the Quote Estimator run; normalises product to the table keys, purchase_date to YYYY-MM-DD or null)
6. Check Warranty (Code — DETERMINISTIC verdict, demo business TechCare electronics shop; see table below; months since purchase vs today, full months)
7. Route Claim (Switch — Covered / Expired / Need Proof / Out of Scope; fallback Need Proof)
8. Covered Reply (AI Agent — confirms covered + next step: bring product + proof of purchase, free repair/replacement)
9. Expired Reply (AI Agent — polite no + paid repair offer with a free check)
10. Ask Proof Reply (AI Agent — asks for one thing: purchase date or receipt/invoice photo, no guessed verdict)
11. Out of Scope Reply (AI Agent — polite no + lists what the shop covers)
12. Reply — Warranty Response (Respond to Webhook — verdict, product, product_label, purchase_date, months_since_purchase, warranty_months, name, reply)
13. Groq Chat Model (SHARED — one node, connected via ai_languageModel to all 5 AI Agents; same pattern as Triage fwBHaEK1bsvc1pgs, Order Taker c6BKAZAK4kUhsZJK, Hiring Screener 0z3wxCtIWI7hUb5A and Quote Estimator NdRNx92VCT28Ax2x; model openai/gpt-oss-120b, temp 0.3, maxTokens 8000 — 8000 from the start, the Quote Estimator run proved 300 is too low for this reasoning model)

No Gmail/Sheets nodes (VM egress proxy blocks gmail.googleapis.com + sheets.googleapis.com).
No Groq HTTP Request nodes (axios ignores the proxy and hangs) — LangChain AI Agent + Groq Chat Model only.
No email is sent — the reply lives in the webhook RESPONSE only. Demo shop only, not a real shop.

## Warranty table (months, demo business TechCare)
Smartphone 12 · Laptop 24 · TV 24 · Washing Machine 24 · Fridge 24 · Smartwatch 12 · Headphones 6 · Accessories (charger/cable) 3.
Verdict rules: covered if months since purchase <= warranty months; expired if >; need_proof if no usable purchase date (or date in the future); out_of_scope if the product is not in the table.

## Warranty-logic UNIT tests (run standalone in node 2026-11-23 ~06:55 PST, using the EXACT Check Warranty code extracted from warranty-checker.json — 25/25 assertions PASSED, VM date 2026-11-23)
The 5 required cases (13 assertions):
- A: smartphone bought 2026-08-23 → verdict **covered**, 3 months since purchase, warranty 12
- B: laptop bought 2024-05-23 → verdict **expired**, 30 months since purchase, warranty 24
- C: headphones, no purchase date → verdict **need_proof**, months null
- D: car (product "other") → verdict **out_of_scope**, warranty null
- E: charger (accessories) bought 2026-09-23 → verdict **covered**, 2 months since purchase, warranty 3
Product normalisation safety net (4 assertions, all passed):
- "iPhone 14" → smartphone, covered; "charger" → accessories; "car" → out_of_scope
Parse Claim JSON regex-salvage (8 assertions, all passed):
- Full JSON `{"product":"smartphone","purchase_date":"2026-08-23"}` → both fields recovered
- Truncated after the date `{"product":"smartphone","purchase_date":"2026-08-23"` → both fields recovered by salvage
- Truncated mid-date `{"product":"laptop","purchase_date":"2024-0` → product recovered, purchase_date null (no invented date)
- `{"product":"headphones","purchase_date":null}` → headphones, null

These are UNIT tests only — NOT live tests. Live tests run tonight after activation.

## Live test cases (all POST, Content-Type: application/json) — RUN MUST EXECUTE, NOT YET RUN
### Test A — Phone, 3 months old — EXPECTED: covered
- Request: {"name":"Ayesha","message":"Hi, I bought a smartphone on 2026-08-23 and now the screen is not working. Is it still under warranty?"}
- Expect: HTTP 200, verdict "covered", months_since_purchase 3, warranty_months 12, reply confirms it is covered and gives the next step (bring product + proof of purchase, free repair/replacement).

### Test B — Laptop, 30 months old — EXPECTED: expired
- Request: {"name":"Bilal","message":"My laptop battery died. I bought the laptop on 2024-05-23. Is it under warranty?"}
- Expect: HTTP 200, verdict "expired", months_since_purchase 30, warranty_months 24, reply politely says the warranty expired and offers a paid repair with a free check.

### Test C — Headphones, no date — EXPECTED: need_proof
- Request: {"name":"Sara","message":"My headphones stopped working, can you check the warranty?"}
- Expect: HTTP 200, verdict "need_proof", reply asks for the purchase date or a receipt/invoice photo, no verdict guessed.

### Test D — Car — EXPECTED: out_of_scope
- Request: {"name":"Omar","message":"Is my car still under warranty? I bought it last year."}
- Expect: HTTP 200, verdict "out_of_scope", reply politely says TechCare is an electronics shop and lists what is covered.

### Test E — Charger, 2 months old — EXPECTED: covered
- Request: {"name":"Zain","message":"Hi, the charger I bought on 2026-09-23 is not working. Is it covered?"}
- Expect: HTTP 200, verdict "covered", months_since_purchase 2, warranty_months 3, reply confirms it is covered and gives the next step.

## Notes for the run
- Import warranty-checker.json into the VM n8n first (same route as the Order Taker / Hiring Screener / Quote Estimator imports), then activate from the editor (production webhook /warranty only works when active). Then run the 5 curl tests above.
- Verdicts must match EXACTLY (covered / expired / need_proof / out_of_scope / covered) — if the Parse Claim agent misreads the product or the date, the verdict will be wrong; that is a real failure, fix the prompt, do not fudge the post text.
- Do NOT import a second copy over a live workflow: `n8n import:workflow` creates a DUPLICATE, it does not update in place (Quote Estimator lesson) — if a fix is needed after import, fix by surgical DB edit + restart, do not re-import.
- Screenshot: wide PNG canvas capture (Zoom to Fit + one zoom-out step, like Chaser 1860x680 / Triage 2561x1080) — white/light mode, all nodes + sticky note readable in one frame, 1080 height. Eye-check the SAVED file (look.1.png OR look.0.jpg in the browser task's snapshot dir). Do NOT use print-to-PDF (crops the canvas).
- Post text: ~/workspace/linkedin/staged/2026-11-23/post-text-warranty-checker.txt is a DRAFT — replace its live-test paragraph (explicit PLACEHOLDER) with the ACTUAL curl results before publishing. Do NOT publish with the placeholder.
- CTA is DM "WARRANTY" — verified fresh 2026-11-23 (0 uses in the posts log before the PREVIEW for 2026-11-24). Do not reuse any earlier CTA (ROUTER, CHASER, REVIEWS, PAID, BILL, REMEMBER, BOOK, SUPPORT, ORDER, HIRE, QUOTE, ESTIMATE).

## Post-text quality rubric (GPT-5 guide — applied to post-text-warranty-checker.txt)
1. Hook — opens with the customer's exact question + the wait. PASS (hook as specified).
2. Problem — the manual receipt-digging delay, in one short paragraph. PASS.
3. Mechanism — the workflow steps named plainly (parse → check table → route → reply). PASS.
4. Proof — live-test paragraph with exact verdicts. PLACEHOLDER — the run must replace it with actual curl results before publishing; do NOT publish with the placeholder.
5. Honesty — no email/sheet claim, no invented numbers, demo framing. PASS (reply in seconds, no email/sheet step claimed anywhere).
6. CTA — DM "WARRANTY", one clear ask. PASS.
7. Hashtags — exactly the 7 specified. PASS (#n8n #AIAutomation #SmallBusiness #CustomerExperience #Groq #WorkflowAutomation #CustomerSupport).
