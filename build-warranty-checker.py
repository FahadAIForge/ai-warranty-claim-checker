#!/usr/bin/env python3
"""Build the AI Warranty Claim Checker workflow JSON (Triage mould).
Pattern copied from build-quote-estimator.py (2026-11-22) / Triage mould:
shared Groq Chat Model across all AI Agents (LangChain), no Gmail/Sheets
nodes (VM proxy blocks googleapis data endpoints), reply comes back in the
webhook response. Demo business is an electronics shop ("TechCare", demo
only, not a real shop). The verdict is DETERMINISTIC (Code node, not the
AI): a fixed warranty table, months since purchase vs today.
Warranty table (months): Smartphone 12, Laptop 24, TV 24, Washing Machine
24, Fridge 24, Smartwatch 12, Headphones 6, Accessories (charger/cable) 3.
Verdicts: covered (months since purchase <= warranty) / expired (>) /
need_proof (no usable purchase date, or date in the future) / out_of_scope
(product not in the table).
Node count note: the file holds 13 nodes — the 12 enumerated steps plus the
one shared Groq Chat Model. The posts-log counts 12 because it excludes the
sticky note; nothing is missing.
"""
import json, uuid

def uid():
    return str(uuid.uuid4())

ID = {
    "sticky": uid(),
    "webhook": uid(),
    "validate": uid(),
    "parse": uid(),
    "parsejson": uid(),
    "check": uid(),
    "switch": uid(),
    "covered": uid(),
    "expired": uid(),
    "askproof": uid(),
    "outofscope": uid(),
    "respond": uid(),
    "groq": uid(),
}
WEBHOOK_ID = uid()
COND = {k: uid() for k in ("covered", "expired", "need_proof", "out_of_scope")}

GROQ_CRED = {"groqApi": {"id": "7JX1ltl0qs1xrSEY", "name": "Groq account"}}
# maxTokens 8000 from the start — the Quote Estimator run proved 300 is too
# low for this reasoning model (transient empty/truncated outputs).
GROQ_PARAMS = {"model": "openai/gpt-oss-120b",
               "options": {"temperature": 0.3, "maxTokensToSample": 8000}}

def agent_node(name, node_id, pos, text_expr, system_msg):
    return {
        "id": node_id, "name": name,
        "type": "@n8n/n8n-nodes-langchain.agent", "typeVersion": 3.1,
        "position": pos,
        "parameters": {
            "promptType": "define",
            "text": text_expr,
            "options": {"systemMessage": system_msg},
        },
    }

STICKY = "## AI Warranty Claim Checker (demo: TechCare)\nCustomer asks 'is this under warranty?' — Groq AI parses product + purchase date, a Code node checks a warranty table, a Switch routes it: covered, expired, need proof, or out of scope. No email/sheet step (no Google APIs on this VM)."

PARSEJSON_JS = r"""
const raw = ($json.output || '').toString().trim();
const cleaned = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
let parsed = {};
try { parsed = JSON.parse(cleaned); } catch (e) {
  parsed = {};
  const pick = function(re) { const m = cleaned.match(re); return m ? m[1] : undefined; };
  const pr = pick(/"product": *"([^"]*)"/);
  if (pr) parsed.product = pr;
  const pd = pick(/"purchase_date": *"([^"]*)"/);
  if (pd) parsed.purchase_date = pd;
  if (/"purchase_date": *null/.test(cleaned)) parsed.purchase_date = null;
}
const v = $('Validate Query').first().json;
let product = (parsed.product || 'other').toString().toLowerCase().trim();
const allowed = ['smartphone', 'laptop', 'tv', 'washing_machine', 'fridge', 'smartwatch', 'headphones', 'accessories', 'other'];
if (!allowed.includes(product)) product = 'other';
let pd = parsed.purchase_date;
if (pd === null || pd === undefined || pd === 'null' || pd === '') pd = null;
else {
  pd = pd.toString().trim();
  if (!/^\d{4}[-/]\d{1,2}[-/]\d{1,2}$/.test(pd)) pd = null;
  else pd = pd.replace(/\//g, '-');
}
return [{ json: { name: v.name, message: v.message, valid: v.valid, reason: v.reason, product, purchase_date: pd } }];
""".strip()

CHECK_JS = r"""
const v = $('Parse Claim JSON').first().json;
const WARRANTY_MONTHS = {
  smartphone: 12,
  laptop: 24,
  tv: 24,
  washing_machine: 24,
  fridge: 24,
  smartwatch: 12,
  headphones: 6,
  accessories: 3
};
const LABELS = {
  smartphone: 'Smartphone',
  laptop: 'Laptop',
  tv: 'TV',
  washing_machine: 'Washing Machine',
  fridge: 'Fridge',
  smartwatch: 'Smartwatch',
  headphones: 'Headphones',
  accessories: 'Accessories (charger/cable)'
};
function normaliseProduct(raw) {
  const s = (raw || '').toString().toLowerCase().trim();
  if (!s) return 'other';
  if (/(washing machine|washer)/.test(s)) return 'washing_machine';
  if (/(smartwatch|apple watch|watch)/.test(s)) return 'smartwatch';
  if (/(headphone|earphone|earbud|airpod)/.test(s)) return 'headphones';
  if (/(charger|cable|accessor)/.test(s)) return 'accessories';
  if (/(fridge|refrigerator)/.test(s)) return 'fridge';
  if (/(^|[^a-z])tv([^a-z]|$)|television/.test(s)) return 'tv';
  if (/(laptop|macbook|notebook)/.test(s)) return 'laptop';
  if (/(iphone|smartphone|mobile|phone)/.test(s)) return 'smartphone';
  if (WARRANTY_MONTHS[s] !== undefined) return s;
  return 'other';
}
function parseDate(raw) {
  if (!raw) return null;
  const s = raw.toString().trim();
  const m = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  if (!m) return null;
  const d = new Date(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10));
  if (isNaN(d.getTime())) return null;
  return d;
}
function fmt(d) {
  const p = function(n) { return (n < 10 ? '0' : '') + n; };
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
}
function fullMonths(from, to) {
  let months = (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth());
  if (to.getDate() < from.getDate()) months -= 1;
  return months;
}
const product = normaliseProduct(v.product);
const bought = parseDate(v.purchase_date);
const today = new Date();
let monthsSince = null;
if (bought) monthsSince = fullMonths(bought, today);
const warrantyMonths = WARRANTY_MONTHS[product] !== undefined ? WARRANTY_MONTHS[product] : null;
const label = LABELS[product] || (v.product ? v.product.toString() : 'product');
let verdict = 'need_proof';
let reason = '';
if (product === 'other') {
  verdict = 'out_of_scope';
  reason = (v.product ? v.product.toString() : 'This product') + ' is not a product TechCare sells — the warranty table covers smartphones, laptops, TVs, washing machines, fridges, smartwatches, headphones and chargers/cables only.';
} else if (!bought || monthsSince === null) {
  verdict = 'need_proof';
  reason = 'No usable purchase date in the message — ask for the receipt or invoice so the warranty can be checked.';
} else if (monthsSince < 0) {
  verdict = 'need_proof';
  reason = 'The purchase date given is in the future — ask for the receipt or invoice to check the warranty.';
} else if (monthsSince <= warrantyMonths) {
  verdict = 'covered';
  reason = label + ' bought ' + fmt(bought) + ' — ' + monthsSince + ' months ago, warranty ' + warrantyMonths + ' months. Still covered.';
} else {
  verdict = 'expired';
  reason = label + ' bought ' + fmt(bought) + ' — ' + monthsSince + ' months ago, warranty was ' + warrantyMonths + ' months. Warranty expired.';
}
return [{ json: { name: v.name, message: v.message, valid: v.valid, reason: v.reason, product, product_label: label, purchase_date: bought ? fmt(bought) : null, months_since_purchase: monthsSince, warranty_months: warrantyMonths, verdict, warranty_reason: reason } }];
""".strip()

nodes = [
    {
        "id": ID["sticky"], "name": "README Note",
        "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
        "position": [0, 0],
        "parameters": {
            "color": 4,
            "content": STICKY,
            "height": 280, "width": 420,
        },
    },
    {
        "id": ID["webhook"], "name": "New Warranty Query",
        "type": "n8n-nodes-base.webhook", "typeVersion": 2,
        "position": [0, 320], "webhookId": WEBHOOK_ID,
        "notes": "POST a warranty question here: { name, message }.",
        "parameters": {"httpMethod": "POST", "options": {}, "path": "warranty",
                       "responseMode": "responseNode"},
    },
    {
        "id": ID["validate"], "name": "Validate Query",
        "type": "n8n-nodes-base.code", "typeVersion": 2,
        "position": [260, 320],
        "parameters": {
            "jsCode": "const body = $json.body || $json; const name = body.name ?? ''; const message = (body.message ?? '').toString(); let valid = true; let reason = 'Request is valid.'; if (!message || message.trim().length === 0) { valid = false; reason = 'Message is empty - please describe the product and when it was bought.'; } else if (message.trim().length <= 5) { valid = false; reason = 'Message is too short - please describe the product and when it was bought.'; } return [{ json: { name, message: message.trim(), valid, reason } }];"
        },
    },
    agent_node(
        "Parse Claim", ID["parse"], [520, 320],
        "={{ '<context>TechCare is a small electronics shop. A customer messaged asking whether their product is still under warranty.</context><task>Parse the customer message into structured JSON.</task><input>Customer name: ' + $json.name + '. Message: ' + $json.message + '. Today is 2026-11-23 — use it to convert relative dates like \"3 months ago\" into an exact date.</input><format>Return ONLY a JSON object with exactly these fields: product (one of: smartphone, laptop, tv, washing_machine, fridge, smartwatch, headphones, accessories, other — use other ONLY if the product is clearly not electronics the shop sells, e.g. a car), purchase_date (the purchase date as YYYY-MM-DD, or null if the customer does not state one).</format><rules>Output ONLY that one-line JSON object, no thinking, no preamble, no explanation, no markdown.</rules><example>{\"product\":\"smartphone\",\"purchase_date\":\"2026-08-23\"}</example>' }}",
        "You are a warranty parser for a small electronics shop. Read the customer's free-text message and extract the product and the purchase date. Return ONLY a JSON object: {\"product\": \"...\", \"purchase_date\": \"YYYY-MM-DD or null\"}. Product must be one of: smartphone, laptop, tv, washing_machine, fridge, smartwatch, headphones, accessories, other. Use null for purchase_date when the customer does not state one. No markdown, no extra text.",
    ),
    {
        "id": ID["parsejson"], "name": "Parse Claim JSON",
        "type": "n8n-nodes-base.code", "typeVersion": 2,
        "position": [780, 320],
        "parameters": {"jsCode": PARSEJSON_JS},
    },
    {
        "id": ID["check"], "name": "Check Warranty",
        "type": "n8n-nodes-base.code", "typeVersion": 2,
        "position": [1040, 320],
        "parameters": {"jsCode": CHECK_JS},
    },
    {
        "id": ID["switch"], "name": "Route Claim",
        "type": "n8n-nodes-base.switch", "typeVersion": 3.2,
        "position": [1300, 320],
        "parameters": {
            "mode": "rules",
            "rules": {"values": [
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                "conditions": [{"id": COND["covered"], "leftValue": "={{ $json.verdict }}", "rightValue": "covered",
                                                "operator": {"type": "string", "operation": "equals"}}],
                                "combinator": "and"},
                 "renameOutput": True, "outputKey": "Covered"},
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                "conditions": [{"id": COND["expired"], "leftValue": "={{ $json.verdict }}", "rightValue": "expired",
                                                "operator": {"type": "string", "operation": "equals"}}],
                                "combinator": "and"},
                 "renameOutput": True, "outputKey": "Expired"},
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                "conditions": [{"id": COND["need_proof"], "leftValue": "={{ $json.verdict }}", "rightValue": "need_proof",
                                                "operator": {"type": "string", "operation": "equals"}}],
                                "combinator": "and"},
                 "renameOutput": True, "outputKey": "Need Proof"},
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                "conditions": [{"id": COND["out_of_scope"], "leftValue": "={{ $json.verdict }}", "rightValue": "out_of_scope",
                                                "operator": {"type": "string", "operation": "equals"}}],
                                "combinator": "and"},
                 "renameOutput": True, "outputKey": "Out of Scope"},
            ]},
            "options": {"fallbackOutput": "extra", "renameFallbackOutput": True,
                        "fallbackOutputKey": "Need Proof"},
        },
    },
    agent_node(
        "Covered Reply", ID["covered"], [1560, 80],
        "={{ 'Write a friendly reply for this customer. Customer name: ' + $json.name + '. Their ' + $json.product_label + ' is still under warranty — bought ' + $json.purchase_date + ' (' + $json.months_since_purchase + ' months ago), warranty ' + $json.warranty_months + ' months. Tell them the next step: bring the product and the proof of purchase to the shop and the repair or replacement is free under warranty. Warm, under 100 words. Return only the reply text, no JSON, no markdown.' }}",
        "You are a support assistant for a small electronics shop. The customer's product IS under warranty. Write the reply (max 100 words): confirm it is covered, state the purchase date and warranty length given, and give the next step — bring the product and proof of purchase to the shop for a free repair or replacement. Use ONLY the facts given — never invent a date or a price. Return ONLY the reply text, no JSON, no markdown.",
    ),
    agent_node(
        "Expired Reply", ID["expired"], [1560, 240],
        "={{ 'Write a polite reply for this customer. Customer name: ' + $json.name + '. Their ' + $json.product_label + ' is out of warranty — bought ' + $json.purchase_date + ' (' + $json.months_since_purchase + ' months ago), the warranty was ' + $json.warranty_months + ' months. Say so kindly, offer a paid repair with a free check, no pressure. Warm, under 100 words. Return only the reply text, no JSON, no markdown.' }}",
        "You are a support assistant for a small electronics shop. The customer's product is OUT of warranty. Write the reply (max 100 words): say so kindly, state the purchase date and warranty length given, and offer a paid repair with a free check, no pressure. Use ONLY the facts given — never invent a date or a price. Return ONLY the reply text, no JSON, no markdown.",
    ),
    agent_node(
        "Ask Proof Reply", ID["askproof"], [1560, 400],
        "={{ 'Write a short, friendly reply for this customer. Customer name: ' + $json.name + '. They asked whether their ' + $json.product_label + ' is under warranty but gave no purchase date, so we cannot check it yet. Ask them for one thing: the purchase date or a photo of the receipt or invoice. Warm, under 80 words. Return only the reply text, no JSON, no markdown.' }}",
        "You are a support assistant for a small electronics shop. The customer gave no purchase date, so the warranty cannot be checked. Ask for one thing only — the purchase date or a photo of the receipt or invoice — in a short friendly message (max 80 words). Never guess a date or a verdict. Return ONLY the reply text, no JSON, no markdown.",
    ),
    agent_node(
        "Out of Scope Reply", ID["outofscope"], [1560, 560],
        "={{ 'Write a warm, polite reply for this customer. Customer name: ' + $json.name + '. They asked whether their ' + $json.product_label + ' is under warranty — but TechCare is an electronics shop and does not sell or cover that kind of product. Say so kindly, list what we do cover (smartphones, laptops, TVs, washing machines, fridges, smartwatches, headphones, chargers and cables), and invite them to ask about one of those instead. Kind, under 100 words. Return only the reply text, no JSON, no markdown.' }}",
        "You are a support assistant for a small electronics shop. The customer asked about a product the shop does not sell. Reply warmly (max 100 words): say the shop only covers electronics, list what is covered (smartphones, laptops, TVs, washing machines, fridges, smartwatches, headphones, chargers and cables), and invite a question about one of those. Never promise coverage or a price for the out-of-scope product. Return ONLY the reply text, no JSON, no markdown.",
    ),
    {
        "id": ID["respond"], "name": "Reply \u2014 Warranty Response",
        "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.1,
        "position": [1820, 320],
        "parameters": {
            "options": {},
            "respondWith": "json",
            "responseBody": "={{ JSON.stringify({ verdict: $('Check Warranty').first().json.verdict, product: $('Check Warranty').first().json.product, product_label: $('Check Warranty').first().json.product_label, purchase_date: $('Check Warranty').first().json.purchase_date, months_since_purchase: $('Check Warranty').first().json.months_since_purchase, warranty_months: $('Check Warranty').first().json.warranty_months, name: $('Check Warranty').first().json.name, reply: $json.output, message: 'Warranty reply ready.' }) }}",
        },
    },
    {
        "id": ID["groq"], "name": "Groq Chat Model",
        "type": "@n8n/n8n-nodes-langchain.lmChatGroq", "typeVersion": 1,
        "position": [520, 80],
        "credentials": GROQ_CRED,
        "parameters": GROQ_PARAMS,
    },
]

def main_conn(target):
    return {"main": [[{"index": 0, "node": target, "type": "main"}]]}

connections = {
    "New Warranty Query": main_conn("Validate Query"),
    "Validate Query": main_conn("Parse Claim"),
    "Parse Claim": main_conn("Parse Claim JSON"),
    "Parse Claim JSON": main_conn("Check Warranty"),
    "Check Warranty": main_conn("Route Claim"),
    "Route Claim": {"main": [
        [{"index": 0, "node": "Covered Reply", "type": "main"}],
        [{"index": 0, "node": "Expired Reply", "type": "main"}],
        [{"index": 0, "node": "Ask Proof Reply", "type": "main"}],
        [{"index": 0, "node": "Out of Scope Reply", "type": "main"}],
        [{"index": 0, "node": "Ask Proof Reply", "type": "main"}],
    ]},
    "Covered Reply": main_conn("Reply \u2014 Warranty Response"),
    "Expired Reply": main_conn("Reply \u2014 Warranty Response"),
    "Ask Proof Reply": main_conn("Reply \u2014 Warranty Response"),
    "Out of Scope Reply": main_conn("Reply \u2014 Warranty Response"),
    # Shared Groq Chat Model -> all 5 AI Agents (one ai_languageModel slot, fan-out)
    "Groq Chat Model": {"ai_languageModel": [[
        {"index": 0, "node": "Parse Claim", "type": "ai_languageModel"},
        {"index": 0, "node": "Covered Reply", "type": "ai_languageModel"},
        {"index": 0, "node": "Expired Reply", "type": "ai_languageModel"},
        {"index": 0, "node": "Ask Proof Reply", "type": "ai_languageModel"},
        {"index": 0, "node": "Out of Scope Reply", "type": "ai_languageModel"},
    ]]},
}

wf = {
    "active": False,
    "connections": connections,
    "name": "AI Warranty Claim Checker",
    "nodes": nodes,
    "pinData": {},
    "settings": {"executionOrder": "v1"},
}

out = "/home/hatch/workspace/linkedin/staged/2026-11-23/warranty-checker.json"
with open(out, "w") as f:
    json.dump(wf, f, indent=2)
print("wrote", out, "| nodes:", len(nodes))
d = json.load(open(out))
names = {n["name"] for n in d["nodes"]}
for src, conns in d["connections"].items():
    assert src in names, f"missing source {src}"
    for ctype, slots in conns.items():
        for slot in slots:
            for c in slot:
                assert c["node"] in names, f"missing target {c['node']} from {src}"
print("connections OK; targets all exist")
print("node list:", [n["name"] for n in d["nodes"]])
# Hard-constraint checks (learned from past runs — do not weaken)
assert len(STICKY) <= 320, f"sticky too long: {len(STICKY)} chars"
print("sticky length:", len(STICKY), "chars (max 320)")
forbidden = ("gmail", "googleSheets", "googleDrive", "httpRequest")
for n in d["nodes"]:
    assert not any(f in n["type"] for f in forbidden), f"forbidden node type: {n['type']}"
print("no Gmail/Sheets/HTTP-Request nodes: OK")
resp = next(n for n in d["nodes"] if n["name"].startswith("Reply"))["parameters"]["responseBody"]
assert resp.startswith("={{ "), "Respond responseBody is missing the leading '=' — would import as a static string and break with HTTP 500"
print("Respond responseBody starts with '={{ ': OK")
groq = next(n for n in d["nodes"] if n["name"] == "Groq Chat Model")
assert groq["parameters"]["model"] == "openai/gpt-oss-120b", "Groq model wrong"
assert groq["parameters"]["options"]["maxTokensToSample"] == 8000, "Groq maxTokens must be 8000"
assert groq["credentials"]["groqApi"]["id"] == "7JX1ltl0qs1xrSEY", "Groq credential id wrong"
print("Groq Chat Model: openai/gpt-oss-120b, maxTokens 8000, credential 'Groq account': OK")
agents = [n for n in d["nodes"] if n["type"] == "@n8n/n8n-nodes-langchain.agent"]
assert len(agents) == 5, f"expected 5 AI Agents, got {len(agents)}"
print("AI Agents: 5 (Parse Claim + 4 replies): OK")
