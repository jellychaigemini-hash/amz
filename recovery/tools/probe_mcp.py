"""
Probe the SIF and Sorftime MCP servers to discover:
  1. What tools they actually expose (via tools/list)
  2. What a sample tools/call returns

Run:  python probe_mcp.py <ASIN>   e.g.  python probe_mcp.py B0DK3RXYY1
"""
import sys
import json
import ssl
import uuid
import http.client
import urllib.parse


# ----- Edit these two lines if you rotate keys -----
SIF_ENDPOINT      = "https://mcp.sif.com/mcp"
SIF_KEY           = "sifmcp260508gw8am67mfhjn8fa6"
SORFTIME_ENDPOINT = "https://mcp.sorftime.com/mcp"
SORFTIME_KEY      = "amxoyumzte10ug1pa1bqkzh3vzreqt09"
# ---------------------------------------------------


def _post(endpoint: str, payload: dict, timeout: int = 30) -> tuple[int, str]:
    parsed = urllib.parse.urlparse(endpoint)
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                       timeout=timeout, context=ctx)
    try:
        conn.request("POST", path,
                     body=json.dumps(payload).encode("utf-8"),
                     headers={"Content-Type": "application/json",
                              "Accept": "application/json"})
        r = conn.getresponse()
        body = r.read().decode("utf-8", errors="replace")
        return r.status, body
    finally:
        conn.close()


def probe(server_name: str, base_endpoint: str, key: str, asin: str):
    print(f"\n{'=' * 70}\n{server_name}\n{'=' * 70}")

    # Try both auth-query-param variants
    for q in ("secret-key", "key"):
        url = f"{base_endpoint}?{q}={key}"
        print(f"\n--- tools/list via ?{q}= ---")
        payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()),
                   "method": "tools/list", "params": {}}
        try:
            status, body = _post(url, payload)
            print(f"HTTP {status}")
            # Strip SSE prefix if any
            if body.startswith("data:"):
                body = body[5:].strip()
            try:
                data = json.loads(body)
                tools = (data.get("result", {}) or {}).get("tools", [])
                if tools:
                    print(f"FOUND {len(tools)} tools:")
                    for t in tools:
                        name = t.get("name", "?")
                        desc = (t.get("description", "") or "")[:80]
                        print(f"  - {name}   {desc}")
                    # Try calling the first tool with the ASIN
                    first = tools[0]["name"]
                    print(f"\n--- tools/call {first}({{'asin': '{asin}'}}) ---")
                    call = {"jsonrpc": "2.0", "id": str(uuid.uuid4()),
                            "method": "tools/call",
                            "params": {"name": first,
                                       "arguments": {"asin": asin,
                                                     "marketplace": "US"}}}
                    s2, b2 = _post(url, call, timeout=60)
                    print(f"HTTP {s2}")
                    print(b2[:1500])
                    return   # success on this variant, stop probing
                else:
                    print("Response parsed but no tools[] list:")
                    print(body[:400])
            except json.JSONDecodeError:
                print("Non-JSON response:")
                print(body[:400])
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    asin = sys.argv[1] if len(sys.argv) > 1 else "B0DK3RXYY1"
    print(f"Probing with ASIN = {asin}")
    probe("SIF MCP", SIF_ENDPOINT, SIF_KEY, asin)
    probe("Sorftime MCP", SORFTIME_ENDPOINT, SORFTIME_KEY, asin)
