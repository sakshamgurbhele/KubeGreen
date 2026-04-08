# KubeGreen: Smart Carbon-Aware Scheduler

KubeGreen is an intelligent job scheduler designed to optimize Kubernetes deployments based on environmental impact and performance. It evaluates multiple GKE clusters to find the best deployment target using a weighted scoring system that considers **latency**, **CPU availability**, and **carbon intensity**.

---

## 1. Overview
KubeGreen allows for "green" workload distribution. By monitoring real-time carbon intensity and cluster performance, it ensures that computationally intensive jobs are shifted to regions with the cleanest energy profiles without sacrificing performance.

## 2. Prerequisites
Ensure your local environment has the following installed:
* **Operating System:** macOS, Linux, or Windows Subsystem for Linux (WSL).
* **Python:** v3.9 or newer.
* **CLIs:** `gcloud`, `kubectl`, and `helm` (v3+).

---

## 3. Infrastructure Setup

### GCP Authentication
Authenticate your terminal and set your active project. Replace `your-gcp-project-id` with your actual project identifier.
```bash
gcloud auth login
PROJECT_ID="your-gcp-project-id"
gcloud config set project "$PROJECT_ID"
gcloud services enable container.googleapis.com

# Choose zones for each cluster
ZONE_LONDON="europe-west2-a"
ZONE_FRANKFURT="europe-west3-a"
ZONE_MADRID="europe-southwest1-a"

# Create clusters
gcloud container clusters create gke-london \
  --zone "$ZONE_LONDON" --project "$PROJECT_ID" \
  --machine-type e2-standard-2 --num-nodes 1

gcloud container clusters create gke-frankfurt \
  --zone "$ZONE_FRANKFURT" --project "$PROJECT_ID" \
  --machine-type e2-standard-2 --num-nodes 1

gcloud container clusters create gke-madrid \
  --zone "$ZONE_MADRID" --project "$PROJECT_ID" \
  --machine-type e2-standard-2 --num-nodes 1
  
# Pull kube credentials
gcloud container clusters get-credentials gke-london --zone "$ZONE_LONDON" --project "$PROJECT_ID"
gcloud container clusters get-credentials gke-frankfurt --zone "$ZONE_FRANKFURT" --project "$PROJECT_ID"
gcloud container clusters get-credentials gke-madrid --zone "$ZONE_MADRID" --project "$PROJECT_ID"

# List contexts
kubectl config get-contexts

# Verify connectivity
kubectl --context=gke-london get nodes
kubectl --context=gke-frankfurt get nodes
kubectl --context=gke-madrid get nodes


# Add and update the Prometheus community Helm chart repo
helm repo add prometheus-community [https://prometheus-community.github.io/helm-charts](https://prometheus-community.github.io/helm-charts)
helm repo update

# Install Prometheus stack into each cluster
for CTX in gke-london gke-frankfurt gke-madrid; do
  kubectl --context=$CTX create namespace monitoring || true
  helm --kube-context $CTX install prometheus \
    prometheus-community/kube-prometheus-stack \
    -n monitoring \
    --set grafana.enabled=false \
    --set alertmanager.enabled=false
done


# London localhost:9090
kubectl --context=gke-london -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090

# Frankfurt localhost:9091
kubectl --context=gke-frankfurt -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9091:9090

# Madrid localhost:9092
kubectl --context=gke-madrid -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9092:9090


{
  "gke-london": {
    "context": "gke-london",
    "region": "London",
    "carbon_zone": "UK",
    "prometheus_url": "http://localhost:9090"
  },
  "gke-frankfurt": {
    "context": "gke-frankfurt",
    "region": "Frankfurt",
    "carbon_zone": "DE",
    "prometheus_url": "http://localhost:9091"
  },
  "gke-madrid": {
    "context": "gke-madrid",
    "region": "Spain",
    "carbon_zone": "ES",
    "prometheus_url": "http://localhost:9092"
  }
}

{
  "UK": 175,
  "DE": 224,
  "ES": 70
}


python3 scheduler.py
