"""Side-by-side RBAC probe — runs on the VM."""
import json
import subprocess

BASE = "https://partners.extravis.co"


def login(email, password):
    r = subprocess.run(
        ["curl", "-sf", "-X", "POST", f"{BASE}/api/v1/auth/login",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"email": email, "password": password})],
        capture_output=True, text=True,
    )
    return json.loads(r.stdout)["access_token"]


def get(token, path):
    r = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", "-H",
         f"Authorization: Bearer {token}", f"{BASE}{path}"],
        capture_output=True, text=True,
    )
    parts = r.stdout.rsplit("\n", 1)
    code = parts[1].strip()
    body = parts[0]
    try:
        data = json.loads(body)
    except Exception:
        data = None
    return code, data


super_pw = subprocess.check_output(
    ["bash", "-c",
     "grep ^SUPERADMIN_PASSWORD= /home/ubuntu/Opportunity_Partner_Portal/.env.prod | cut -d= -f2"],
    text=True,
).strip()

stok = login("admin@extravis.com", super_pw)
cmtok = login("channel.manager@extravis.com", "Demo@1234")
ptok = login("marcus.chen@northbeam.example", "Demo@1234")


def summarize(d):
    if d is None:
        return ""
    if isinstance(d, dict):
        if "items" in d:
            return "items={} total={}".format(len(d.get("items", [])), d.get("total"))
        if "is_superadmin" in d:
            return "is_super={} is_cm={} managed={}".format(
                d.get("is_superadmin"), d.get("is_channel_manager"), d.get("managed_company_count"))
        if "total_companies" in d:
            return "companies={} opps={} partners={} worth={}".format(
                d["total_companies"], d["total_opportunities"], d["total_partners"], d["total_worth"])
        if "detail" in d:
            det = d["detail"]
            if isinstance(det, dict):
                return "detail={}".format(det.get("code", det))
            return "detail={}".format(det)
    return str(d)[:80]


endpoints = [
    "/api/v1/auth/me",
    "/api/v1/dashboard/admin/stats",
    "/api/v1/companies?page_size=20",
    "/api/v1/opportunities?page_size=50",
    "/api/v1/dashboard/deals?page_size=50",
    "/api/v1/users?page_size=50",
    "/api/v1/commissions?page_size=50",
]

for ep in endpoints:
    print("\n=== {} ===".format(ep))
    for label, tok in [("superadmin", stok), ("channel mgr", cmtok), ("partner", ptok)]:
        code, data = get(tok, ep)
        print("  {:<13} {}  {}".format(label, code, summarize(data)))
