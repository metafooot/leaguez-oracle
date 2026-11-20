import base64
import hashlib
import json
import time
import requests

APP_ID = 776578156
INDEXER_BASES = [
    "https://testnet-idx.algonode.cloud",
    "https://testnet-idx.nodely.io",
]
ALGOD_BASES = [
    "https://testnet-api.algonode.cloud",
    "https://testnet-api.nodely.io",
]
ALL_BASES = INDEXER_BASES + ALGOD_BASES

def encode_address(pubkey: bytes) -> str:
    checksum = hashlib.new("sha512_256", pubkey).digest()[-4:]
    addr_bytes = pubkey + checksum
    return base64.b32encode(addr_bytes).decode().rstrip("=")

def list_box_names():
    for base in ALL_BASES:
        try:
            is_indexer = "idx" in base
            params = {"limit": 1000} if is_indexer else {"max": 1000}
            r = requests.get(f"{base}/v2/applications/{APP_ID}/boxes", params=params, timeout=10)
            print(f"List boxes from {base} -> {r.status_code}")
            if r.status_code != 200:
                print(f"  body: {r.text[:300]}")
                continue
            obj = r.json()
            boxes = obj.get("boxes", [])
            names = []
            raw_names = []
            for b in boxes:
                n = b.get("name", "")
                raw_names.append(n)
                if n:
                    try:
                        names.append(base64.b64decode(n))
                    except Exception:
                        try:
                            names.append(base64.urlsafe_b64decode(n + "=" * (-len(n) % 4)))
                        except Exception:
                            pass
            if names:
                print(f"First raw box name: {raw_names[0]}")
                print(f"First decoded hex: {names[0].hex()} len={len(names[0])}")
                return names
        except Exception as e:
            print(f"List error {base}: {e}")
            continue
    return []

def fetch_box_value(box_name_bytes: bytes):
    b64_std = base64.b64encode(box_name_bytes).decode()
    b64_std_nopad = b64_std.rstrip("=")
    b64_url = base64.urlsafe_b64encode(box_name_bytes).decode()
    b64_url_nopad = b64_url.rstrip("=")
    cands = [b64_std, b64_std_nopad, b64_url, b64_url_nopad]
    # Use requests params= so it URL-encodes correctly, this is the fix
    for base in ALL_BASES:
        for cand in cands:
            try:
                r = requests.get(f"{base}/v2/applications/{APP_ID}/box", params={"name": cand}, timeout=8)
                if r.status_code == 200:
                    obj = r.json()
                    val_b64 = obj.get("value", "")
                    if not val_b64:
                        continue
                    try:
                        return base64.b64decode(val_b64)
                    except Exception:
                        return base64.urlsafe_b64decode(val_b64 + "=" * (-len(val_b64) % 4))
                else:
                    # Only print first box failure to avoid spam
                    if box_name_bytes == b"\x00" * 8 or True:
                        pass
            except Exception:
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
    if not creator:
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
    status_labels = ["open", "matched", "settled", "refunded"]
    b["statusLabel"] = status_labels[b["status"]]
    return b

def main():
    names = list_box_names()
    boxes = len(names)
    values = 0
    bets = []
    for idx, name_bytes in enumerate(names):
        bet_id = parse_bet_id(name_bytes)
        data = fetch_box_value(name_bytes)
        if data is None:
            if idx == 0:
                print("First box value FAILED - check Actions log for list debug above")
            continue
        values += 1
        if idx == 0:
            print(f"First box value OK len={len(data)} hex start={data[:32].hex()}")
        parsed = parse_bet(bet_id, data)
        if parsed is None:
            print(f"Bet {bet_id} parse failed len={len(data)}")
            continue
        if not parsed["creatorAddress"]:
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
