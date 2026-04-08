import json
import subprocess
import requests
import time
import os
import csv
from datetime import datetime

CPU_WATT = 35  # Average power draw in watts per vCPU


with open("weights.json") as f:
    weights = json.load(f)
    ALPHA = weights.get("alpha")
    BETA = weights.get("beta")
    GAMMA = weights.get("gamma")


try:
    with open("clusters.json") as f:
        clusters = json.load(f)
    print(f"✅ Loaded {len(clusters)} clusters from config\n")
except Exception as e:
    print(f"❌ Failed to load clusters.json: {e}")
    exit(1)

def ping_latency(prometheus_url):
    try:
        start = time.time()
        r = requests.get(f"{prometheus_url}/-/ready", timeout=2)
        r.raise_for_status()
        end = time.time()
        return round((end - start) * 1000) 
    except Exception as e:
        print(f"⚠️  Latency check failed for {prometheus_url}: {e}")
        return float('inf')

def get_cpu_usage(prom_url):
    query = 'sum(rate(container_cpu_usage_seconds_total[1m]))'
    try:
        r = requests.get(f"{prom_url}/api/v1/query", params={'query': query})
        results = r.json()
        return float(results['data']['result'][0]['value'][1])
    except Exception as e:
        print(f"⚠️  CPU usage fetch failed for {prom_url}: {e}")
        return float('inf')

def get_carbon_intensity(zone):
    try:
        with open("carbon.json") as f:
            carbon_data = json.load(f)
        return carbon_data.get(zone, float('inf'))
    except Exception as e:
        print(f"⚠️  Failed to load carbon data for zone {zone}: {e}")
        return float('inf')

def get_job_duration(context, job_name="test-job", namespace="default"):
    try:
        out = subprocess.check_output([
            "kubectl", "--context", context,
            "get", "job", job_name,
            "-o", "json",
            "-n", namespace
        ])
        job_data = json.loads(out)
        start = job_data["status"]["startTime"]
        end = job_data["status"].get("completionTime")
        if not end:
            return 0  

        start_t = time.strptime(start, "%Y-%m-%dT%H:%M:%SZ")
        end_t = time.strptime(end, "%Y-%m-%dT%H:%M:%SZ")
        duration = time.mktime(end_t) - time.mktime(start_t)
        return round(duration, 2)
    except:
        return 0

def score_cluster(latency, carbon, cpu):
    return ALPHA * latency + BETA * carbon + GAMMA * cpu

best_cluster = None
best_score = float('inf')

print("🔍 Evaluating clusters...\n")

for name, data in clusters.items():
    print(f"📡 Checking cluster: {name}")
    latency = ping_latency(data["prometheus_url"])
    cpu = get_cpu_usage(data["prometheus_url"])
    carbon = get_carbon_intensity(data["carbon_zone"])
    score = score_cluster(latency, carbon, cpu)

    print(f"➡️  {name} → latency: {latency} ms, cpu: {cpu:.2f}, carbon: {carbon}, score: {score:.2f}\n")

    if score < best_score:
        best_score = score
        best_cluster = data
        best_latency = latency
        best_cpu = cpu
        best_carbon = carbon

if best_cluster:
    print(f"✅ Best cluster: {best_cluster['context']} ({best_cluster['region']})")
    print(f"📤 Applying job.yaml to: {best_cluster['context']}...\n")

    if not os.path.exists("job.yaml"):
        print("❌ job.yaml not found. Please make sure it exists.")
        exit(1)

    try:
        subprocess.run([
            "kubectl", "--context", best_cluster["context"],
            "apply", "-f", "job.yaml"
        ], check=True)
        print("🚀 Job submitted successfully!\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to apply job.yaml: {e}")
        exit(1)


    print("⏳ Waiting for job to complete...")
    time.sleep(10)

    job_duration = get_job_duration(best_cluster["context"])
    cpu_seconds = best_cpu * job_duration
    energy_kwh = (cpu_seconds * CPU_WATT) / 3600
    carbon_emitted = energy_kwh * best_carbon

    print(f"🕒 Job duration: {job_duration}s")
    print(f"⚡ CPU time: {cpu_seconds:.2f}s → Energy: {energy_kwh:.6f} kWh")
    print(f"🌱 Carbon emitted: {carbon_emitted:.4f} gCO₂\n")


    log_row = [
        datetime.now().isoformat(),
        best_cluster['context'],
        best_cluster['region'],
        best_latency,
        best_cpu,
        best_carbon,
        best_score,
        job_duration,
        carbon_emitted,
        "smart"
    ]

    with open("results.csv", "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(log_row)
        print("📝 Logged decision to results.csv")

else:
    print("❌ No suitable cluster found or all metrics failed.")
