import base64
import hashlib
import json
import time
from algosdk.v2client import algod, indexer

APP_ID = 776578156

# Official clients, they handle box name encoding for us
ALGOD_URLS = [
    "https://testnet-api.algonode.cloud",
    "https://testnet-api.nodely.io",
]
INDEXER_URLS = [
    "https://testnet-idx.algonode.cloud",
    "https://testnet-idx.nodely.io",
]

def encode_address(pubkey: bytes) -> str:
    checksum = hashlib.new("sha512_256", pubkey).digest()[-4:]
    return base64.b32encode(pubkey + checksum).decode().rstrip("=")

def get_clients():
    algod_clients = [algod.AlgodClient("", u) for u in ALGOD_URLS]
    indexer_clients = [indexer.IndexerClient("", u) for u in INDEXER_URLS]
    return algod_clients, indexer_clients

def list_box_names(indexer_clients):
    for c in indexer_clients:
        try:
            resp = c.application_boxes(APP_ID)
            boxes = resp.get("boxes", [])
            print(f"Indexer boxes found: {len(boxes)}")
            names = []
            raw = []
            for b in boxes:
                n = b.get("name", "")
                raw.append(n)
                if n:
                    try:
                        names.append(base64.b64decode(n))
                    except Exception:
                        names.append(base64.urlsafe_b64decode(n + "=" * (-len(n) % 4)))
            if names:
                print(f"First raw name: {raw[0]}")
                print(f"First decoded hex: {names[0].hex()} len={len(names[0])}")
                return names
        except Exception as e:
            print(f"List error: {e}")
            continue
    return []

def fetch_box_value(algod_clients, indexer_clients, box_name_bytes: bytes):
    # Try Algod first, then Indexer, both via SDK
    for c in algod_clients:
        try:
            resp = c.application_box_by_name(APP_ID, box_name_bytes)
            # SDK returns dict with value as base64 string or bytes
            val = resp.get("value", "")
            if isinstance(val, str) and val:
                try:
                    return base64.b64decode(val)
                except Exception:
                    return base64.urlsafe_b64decode(val + "=" * (-len(val) % 4))
            if isinstance(val, bytes) and val:
                return val
            # Some SDK versions return {"name":..., "value":...} nested
            if isinstance(resp, dict) and "value" not in resp:
                print(f"Algod resp keys: {list(resp.keys())} raw: {str(resp)[:300]}")
        except Exception as e:
            print(f"Algod box error for {box_name_bytes.hex()}: {e}")
            continue
    for c in indexer_clients:
        try:
            resp = c.application_box_by_name(APP_ID, box_name_bytes)
            val = resp.get("value", "")
            if isinstance(val, str) and val:
                try:
                    return base64.b64decode(val)
                except Exception:
                    return base64.urlsafe_b64decode(val + "=" * (-len(val) % 4))
            if isinstance(val, bytes) and val:
                return val
        except Exception as e:
            print(f"Indexer box error for {box_name_bytes.hex()}: {e}")
            continue
    return None

def parse_bet_id(name_bytes: bytes) -> int:
    if len(name_bytes) == 8:
        return int.from_bytes(name_bytes, "big")
    if len(name_bytes) > 8:
        v = int.from_bytes(name_bytes[-8:], "big")
        if 0 <= v < 1000000:
            return v
        return 0
    return 0

def scan_stake(data: bytes):
    for i in range(len(data) - 7):
        micro = int.from_bytes(data[i:i+8], "big")
        if 1000000 <= micro <= 1000000000:
            d = micro / 1000000.0
            if 1 <= d <= 1000:
                return d
    return 0

def parse_bet(bet_id: int, data: bytes):
    if not data or len(data) < 32:
        return None
    try:
        creator = encode_address(data[0:32])
    except Exception:
        return None
    b = {
        "betId": bet_id,
        "creatorAddress": creator,
        "creatorPick": 0,
        "creatorPickLabel": "HOME",
        "stake": 0,
        "joinerAddress": "",
        "joinerPick": 255,
        "status": 0,
        "statusLabel": "open",
        "createdAt": 0,
    }
    labels = ["HOME", "DRAW", "AWAY"]
    if len(data) == 96:
        c_pick = int.from_bytes(data[64:72], "big")
        j_pick = int.from_bytes(data[72:80], "big")
        stake_micro = int.from_bytes(data[80:88], "big")
        status = int.from_bytes(data[88:96], "big")
        if 0 <= c_pick <= 2 and 1000000 <= stake_micro <= 1000000000 and 0 <= status <= 3:
            b["creatorPick"] = c_pick
            b["creatorPickLabel"] = labels[c_pick]
            b["joinerPick"] = j_pick
            b["stake"] = stake_micro / 1000000.0
            b["status"] = status
            jb = data[32:64]
            if any(x != 0 for x in jb):
                b["joinerAddress"] = encode_address(jb)
            return b
    if len(data) == 83:
        b["creatorPick"] = data[32] & 0xFF
        b["stake"] = int.from_bytes(data[33:41], "big") / 1000000.0
        jb = data[41:73]
        if any(x != 0 for x in jb):
            b["joinerAddress"] = encode_address(jb)
        b["joinerPick"] = data[73] & 0xFF
        b["status"] = data[74] & 0xFF
        b["createdAt"] = int.from_bytes(data[75:83], "big")
    elif len(data) >= 104:
        b["creatorPick"] = data[39] & 0xFF
        b["stake"] = int.from_bytes(data[40:48], "big") / 1000000.0
        jb = data[48:80]
        if any(x != 0 for x in jb):
            b["joinerAddress"] = encode_address(jb)
        b["joinerPick"] = data[87] & 0xFF
        b["status"] = data[95] & 0xFF
        try:
            b["createdAt"] = int.from_bytes(data[96:104], "big")
        except Exception:
            pass
    elif len(data) >= 41:
        b["creatorPick"] = data[32] & 0xFF
        b["stake"] = int.from_bytes(data[33:41], "big") / 1000000.0
        if len(data) >= 74:
            b["status"] = data[73] & 0xFF
        if len(data) >= 73:
            jb = data[41:73]
            if len(jb) == 32 and any(x != 0 for x in jb):
                b["joinerAddress"] = encode_address(jb)
    if b["stake"] < 1 or b["stake"] > 1000:
        s = scan_stake(data)
        if 1 <= s <= 1000:
            b["stake"] = s
    if b["creatorPick"] < 0 or b["creatorPick"] > 2:
        b["creatorPick"] = 0
    b["creatorPickLabel"] = labels[b["creatorPick"]]
    if b["status"] < 0 or b["status"] > 3:
        b["status"] = 1 if b["joinerAddress"] else 0
    if b["stake"] < 1 or b["stake"] > 1000:
        return None
    b["statusLabel"] = ["open", "matched", "settled", "refunded"][b["status"]]
    return b

def main():
    algod_clients, indexer_clients = get_clients()
    names = list_box_names(indexer_clients)
    boxes = len(names)
    values = 0
    bets = []
    for idx, name_bytes in enumerate(names):
        bet_id = parse_bet_id(name_bytes)
        data = fetch_box_value(algod_clients, indexer_clients, name_bytes)
        if data is None:
            if idx == 0:
                print("First box value STILL FAILED, see errors above")
            continue
        values += 1
        if idx == 0:
            print(f"First box value OK len={len(data)} hex start={data[:32].hex()}")
        parsed = parse_bet(bet_id, data)
        if parsed is None:
            print(f"Bet {bet_id} parse failed len={len(data)}")
            continue
        if parsed["stake"] < 1 or parsed["stake"] > 1000:
            continue
        bets.append(parsed)
        time.sleep(0.02)
    bets.sort(key=lambda x: x["betId"])
    out = {
        "updatedAt": int(time.time()),
        "appId": APP_ID,
        "boxes": boxes,
        "values": values,
        "parsed": len(bets),
        "bets": bets,
    }
    with open("bets_testnet.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Boxes: {boxes}, Values: {values}, Parsed: {len(bets)}")

if __name__ == "__main__":
    main()
