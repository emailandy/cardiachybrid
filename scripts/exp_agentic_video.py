import json
import time
import requests
import google.auth
from google.auth.transport.requests import Request
import os
import statistics

def get_auth_token():
    credentials, project = google.auth.default()
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials.token

def score_shocks(gt, pred, tol=3.0):
    gt = sorted(gt)
    pred = sorted(pred)
    matched_gt = set()
    matched_pred = set()
    mae_sum = 0
    
    for p_idx, p in enumerate(pred):
        best_diff = tol + 1.0
        best_g_idx = -1
        for g_idx, g in enumerate(gt):
            if g_idx in matched_gt: continue
            diff = abs(p - g)
            if diff <= tol and diff < best_diff:
                best_diff = diff
                best_g_idx = g_idx
        if best_g_idx != -1:
            matched_gt.add(best_g_idx)
            matched_pred.add(p_idx)
            mae_sum += best_diff
            
    tp = len(matched_gt)
    fp = len(pred) - tp
    fn = len(gt) - tp
    mae = mae_sum / tp if tp > 0 else None
    return tp, fp, fn, mae

def run_experiment():
    with open("fixtures/ground_truth_simvideo2.json") as f:
        gt_data = json.load(f)
    gt_shocks = [s["timestamp_s"] for s in gt_data["shocks"]]
    print(f"GT Shocks: {gt_shocks}")
    
    endpoint = "https://aiplatform.googleapis.com/v1beta1/projects/nodepeel/locations/global/publishers/google/models/gemini-3.8-flash:generateContent"
    token = get_auth_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    schema = {
        "type": "OBJECT",
        "properties": {
            "shocks": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "timestamp_s": {
                            "type": "NUMBER"
                        }
                    }
                }
            }
        }
    }
    
    prompt = "List all defibrillation shocks in the video. Return their timestamps in seconds."
    
    results = {"STATIC": [], "AGENTIC": []}
    os.makedirs(".artifacts", exist_ok=True)
    
    with open(".artifacts/.gitignore", "w") as f:
        f.write("*\n")
        
    total_cost = 0.0
    
    for mode in ["STATIC", "AGENTIC"]:
        for i in range(5):
            print(f"Running {mode} draw {i+1}...")
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "fileData": {
                                    "mimeType": "video/mp4",
                                    "fileUri": "gs://videval/cardiac/simvideo2.mp4"
                                },
                                "mediaProcessing": mode
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema
                }
            }
            
            t0 = time.time()
            resp = requests.post(endpoint, headers=headers, json=payload)
            latency = time.time() - t0
            
            if resp.status_code != 200:
                print(f"Error {resp.status_code}: {resp.text}")
                continue
                
            data = resp.json()
            with open(f".artifacts/{mode}_draw{i+1}.json", "w") as f:
                json.dump(data, f, indent=2)
                
            metadata = data.get("usageMetadata", {})
            total_tokens = metadata.get("totalTokenCount", 0)
            tool_use_tokens = metadata.get("toolUsePromptTokenCount", 0)
            
            cost = (total_tokens / 1_000_000) * 0.30
            total_cost += cost
            if total_cost > 5.00:
                print("COST CEILING EXCEEDED! ABORTING")
                return
                
            try:
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text_content = "".join([p["text"] for p in parts if "text" in p])
                answer = json.loads(text_content)
                pred_shocks = [s.get("timestamp_s", 0) for s in answer.get("shocks", [])]
            except Exception as e:
                print(f"Failed to parse response: {e}")
                pred_shocks = []
                
            tp, fp, fn, mae = score_shocks(gt_shocks, pred_shocks)
            
            results[mode].append({
                "latency": latency,
                "total_tokens": total_tokens,
                "tool_use_tokens": tool_use_tokens,
                "cost": cost,
                "pred_shocks": pred_shocks,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "mae": mae
            })
            mae_str = f"{mae:.2f}" if mae is not None else "n/a"
            print(f"  -> TP: {tp}, FP: {fp}, FN: {fn}, MAE: {mae_str}")

    print("\n--- Summary ---")
    for mode in ["STATIC", "AGENTIC"]:
        tps = [r["tp"] for r in results[mode]]
        fps = [r["fp"] for r in results[mode]]
        fns = [r["fn"] for r in results[mode]]
        maes = [r["mae"] for r in results[mode] if r["tp"] > 0]
        toks = [r["total_tokens"] for r in results[mode]]
        tools = [r["tool_use_tokens"] for r in results[mode]]
        lats = [r["latency"] for r in results[mode]]
        costs = [r["cost"] for r in results[mode]]
        
        print(f"[{mode}]")
        print(f"  TP: {tps} (Median: {statistics.median(tps):.1f})")
        print(f"  FP: {fps} (Median: {statistics.median(fps):.1f})")
        print(f"  FN: {fns} (Median: {statistics.median(fns):.1f})")
        mae_med = statistics.median(maes) if maes else None
        mae_med_str = f"{mae_med:.2f}s" if mae_med is not None else "n/a"
        print(f"  MAE: {[round(m, 2) for m in maes]} (Median: {mae_med_str})")
        print(f"  Total Tokens: {toks} (Median: {statistics.median(toks):.1f})")
        print(f"  Tool Use Tokens: {tools} (Median: {statistics.median(tools):.1f})")
        print(f"  Latency: {[round(l, 1) for l in lats]} (Median: {statistics.median(lats):.1f}s)")
        print(f"  Cost: {[round(c, 3) for c in costs]} (Total: {sum(costs):.3f})")

if __name__ == "__main__":
    run_experiment()
