import json
import subprocess
import requests
import time
import os
import csv
from datetime import datetime

CPU_WATT = 35  


with open("weights.json") as f:
    weights = json.load(f)
    ALPHA = weights.get("alpha")
    BETA = weights.get("beta")
    GAMMA = weights.get("gamma")

# Load clusters
with open("clusters.json") as f:
    clusters = json.load(f)

with open("carbon.json") as f:
    carbon_data = json.load(f)

def ping_latency(prometheus_url, trials=3):
    latencies = []
    for _ in range(trials):
        try:
            start = time.time()
            r = requests.get(f"{prometheus_url}/-/ready", timeout=2)
            r.raise_for_status()
            end = time.time()
            latencies.append((end - start) * 1000)
        except:
            latencies.append(float("inf"))
    return round(sum(latencies) / len(latencies))

def get_cpu_usage(prom_url):
    query = 'sum(rate(container_cpu_usage_seconds_total[1m]))'
    try:
        r = requests.get(f"{prom_url}/api/v1/query", params={'query': query})
        results = r.json()
        return float(results['data']['result'][0]['value'][1])
    except:
        return float('inf')

def get_carbon_intensity(zone):
    return carbon_data.get(zone, float('inf'))

def get_job_duration(context, job_name="test-job", namespace="default"):
    try:
        out = subprocess.check_output([
            "kubectl", "--context", context,
            "get", "job", job_name,
            "-o", "json",
            "-n", namespace
        ])
        job_data = json.loads(out)
        start = job_data["status"].get("startTime")
        end = job_data["status"].get("completionTime")
        if not (start and end):
            return 0
        start_t = time.strptime(start, "%Y-%m-%dT%H:%M:%SZ")
        end_t = time.strptime(end, "%Y-%m-%dT%H:%M:%SZ")
        return round(time.mktime(end_t) - time.mktime(start_t), 2)
    except:
        return 0

def score_cluster(latency, carbon, cpu):
    return ALPHA * latency + BETA * carbon + GAMMA * cpu


if not os.path.exists("results.csv"):
    with open("results.csv", "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["timestamp", "cluster", "region", "latency", "cpu", "carbon", "score", "duration", "emissions", "selected", "alpha", "beta", "gamma"])

print("📊 Running job on all clusters...")
results = []

def delete_and_apply(context):
    subprocess.run(["kubectl", "--context", context, "delete", "job", "test-job", "--ignore-not-found"], stdout=subprocess.PIPE)
    subprocess.run(["kubectl", "--context", context, "apply", "-f", "job.yaml"], stdout=subprocess.PIPE)

def wait_for_completion(context):
    for _ in range(12):
        duration = get_job_duration(context)
        if duration > 0:
            return duration
        time.sleep(5)
    return 0


for name, data in clusters.items():
    print(f"🚀 Launching on {name}...")
    delete_and_apply(data["context"])


for name, data in clusters.items():
    print(f"⏳ Measuring metrics for {name}...")
    latency = ping_latency(data["prometheus_url"])
    cpu = get_cpu_usage(data["prometheus_url"])
    carbon = get_carbon_intensity(data["carbon_zone"])
    duration = wait_for_completion(data["context"])
    score = score_cluster(latency, carbon, cpu)
    cpu_seconds = cpu * duration
    energy_kwh = (cpu_seconds * CPU_WATT) / 3600
    emissions = energy_kwh * carbon

    results.append({
        "name": name,
        "context": data["context"],
        "region": data["region"],
        "latency": latency,
        "cpu": cpu,
        "carbon": carbon,
        "score": score,
        "duration": duration,
        "emissions": emissions
    })


best = min(results, key=lambda x: x["score"])

with open("results.csv", "a", newline="") as csvfile:
    writer = csv.writer(csvfile)
    for row in results:
        writer.writerow([
            datetime.now().isoformat(),
            row["name"],
            row["region"],
            row["latency"],
            row["cpu"],
            row["carbon"],
            row["score"],
            row["duration"],
            row["emissions"],
            1 if row["name"] == best["name"] else 0,
            ALPHA, BETA, GAMMA
        ])
print("✅ All cluster results logged with real emissions and selected winner.")
