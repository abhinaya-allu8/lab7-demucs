# lab7-music-separation-kubernetes
![separation](images/music_separation.png)
Music-Separation-as-a-service (MSaaS)
## Overview
In this lab, you're going to create a kubernetes cluster that provides a REST API for automatic music separation service and prepares the different tracks for retrieval. You can, if you wish, provide an alternate gRPC API following the general outline of this lab.

You may [want to bookmark this kubernetes "cheat sheet"](https://kubernetes.io/docs/reference/kubectl/cheatsheet/).

You should complete the QwikLabs tutorials on using Docker and Kubernetes and go through [the csci 4253/5253 Kubernetes tutorial](https://github.com/cu-csci-4253-datacenter/kubernetes-tutorial) prior to starting this homework. That tutorial (and the QwikLab tutorials) shows you how to construct a simple Dockerfile, build a Docker image, push it to the Docker Hub or Google registry and then deploy it on Kubernetes. You can either use the Google cloud shell to do your work or install Docker and Kubernetes on your laptop.

You will deploy containers providing the following services.
+ **rest** - the REST frontend will accept API requests for analysis and handle queries concerning MP3's. The REST worker will queue tasks to workers using `redis` queues. Full details are provided in [rest/README.md](rest/README.md).
+ **worker** - Worker nodes will receive work requests to analyze MP3's and cache results in a cloud object store (probably Min.io). Full details are provided in [worker/README.md](worker/README.md).
+ **redis** - You will be provided a Redis deployment and service to provide a redis database server. Full details are provided in [redis/README.md](redis/README.md.)

### Waveform Source Separation Analysis
The worker will use [open source waveform source separation analysis](https://github.com/facebookresearch/demucs) software from Facebook. See the [worker README](worker/README.md) for more details. Our reason for turning this into a micro-service is because it takes a long time to run the source separation (about 3-4x the running time of a song).

### Setting up Kubernetes
You will need to create a Kubernetes cluster to run your code. You can either use a local install of Docker and Kubernetes or use Google Cloud's service, GKE. You **should use a local setup for development** and then switch to GKE at the end.

See the [directions in the Kubernetes tutorial on deploying a GKE cluster](https://github.com/cu-csci-4253-datacenter/kubernetes-tutorial/tree/master/07-guestbook-on-gke).

### Cloud object service

Rather than send the large MP3 files through Redis, I suggest using the Min.io object storage system (or other object store) to store the song contents ***and*** the output of the waveform separation. 
We suggest you use the [min.io python interface](https://min.io/docs/minio/linux/developers/python/API.html) to connect to an object storage system like [Min.io](https://github.com/cu-csci-4253-datacenter/kubernetes-tutorial/tree/master/06-minio), [Google object store](https://cloud.google.com/storage) and Amazon S3.
The library [has several example code snippets](https://github.com/minio/minio-py/tree/release/examples) that you can repurpose.

One benefit of an object store is that you can control access to those objects & direct the user to download the objects directly from *e.g.* S3 rather than relaying the data through your service. We're not going to rely on that feature.

We strongly suggest you set up a [Min.io server as shown in the Kubernetes tutorial](https://github.com/cu-csci-4253-datacenter/kubernetes-tutorial/tree/master/06-minio) and use that during your development phase. You could then change the credentials and endpoint if you want to e.g. use Google Object Store later.

In my reference solution, I had a single 'bucket' called "queue" that holds the objects containing MP3 songs to process and another bucket called "output" to hold the results ready for download:
![buckets](images/buckets.png)

The "output" bucket has objects named `<songhash>-<track>.mp3` that contain the separate tracks of a song:
![output bucket image](images/output-bucket.png)

## Suggested Development Steps

First, ***it's important to understand that the DEMUCS application consumes a lot of memory***. You should test with the short data samples and only use a single Worker node at first. You can check the node resources using `kubectl get nodes` to list the nodes and *e.g.* `kubectl describe node <nodename>` to see how much memory and cpu is available.using `describe` will also alert you to pods being killed due to lack of memory. 

You should first deploy the `redis` provided deployments. We've provided a script `deploy-local-dev.sh` that does this and enables *port forwarding* from the corresponding services to your local host, simplifying development of your rest and worker program.

Unlike previous labs, we've dropped the use of `rabbitmq` because it has some un-needed complexities. Instead, we suggest you use [Redis list data-types](https://redis.io/docs/data-types/lists/) to provide events to the worker. This can be done using [`lpush`](https://redis.io/docs/data-types/lists/#basic-commands) to add work to the queue and [`blpop` blocking pop](https://redis.io/docs/data-types/lists/#blocking-commands) to wait for work and remove it for processing.

Although not explicitly required in production, we have provided [a simple python program `logs/log.py`](logs/logs.py) that connects to the `logging` key in database 0 of Redis using the `lpush`/`blpop` model. You can use that to subscribe to any informational or debug messages to understand what's going on. It's useful to deploy that service as a "logs" pod (or deployment) so you can monitor the output using `kubectl logs logs-<unique id for pod>`. With port-forwarding enabled you should also be able to run it locally. If you've deployed a GKE cluster, you may also want to use the GKE logs and reporting mechanism.

Following that, you should construct the `rest` server because you can use that to test your `redis` database connection and your debugging interface. Lastly, start on the `worker`. We recommend that you develop your worker on your laptop because that reduces the number of times you need to build and push containers; to do this, you would port-forward the redis connection to your laptop and your worker would then connect to the appropriate ports on `localhost` (see below).

When you deploy things in Kubernetes, you should use version numbers for your container images. If you're in a edit/deploy/debug cycle, your normal process to deploy new code will be to push a new container image and then delete the existing pod (rest or worker). At that point, the deployment will create a new pod. If you're using version numbers, you'll be able to insure that you're running the most recent code. You can also use the `latest` tag, but if it looks like things are not using the right version, switch to version numbers.

Each subdirectory contains directions in the appropriate README file.

### Port Forwarding

While you're developing your rest and worker programs, you may want to do development on your local computer while still using the `minio` and `redis` nodes in your Kubernetes cluster. You can do this using `kubectl port-forward` for specific services which will connect a Kubernetes service to you local system (whether it's in Google's GKE or your local system). You can to that using e.g.
```
kubectl port-forward --address 0.0.0.0 service/redis 6379:6379 &
kubectl port-forward --namespace minio-ns svc/myminio-proj 9000:9000 &
```
to forward your Redis database to port 6379 on your computer and minio to local port 9000 on your computer. Then, your rest server & worker can connect to e.g. `localhost:6379` or `localhost:9000` while you test your code. The script `deploy-local-dev.sh` both deploys `redis` and then sets up port-forwarding for you for `redis` and `minio`.

### Sample Data
We've produced two programs `sample-requests.py` and `short-sample-requests.py` that make some sample requests.

Processing an MP3 file takes a while - they also take a fair amount of memory (at least 6GB in my experience). You're encouraged to use the `short-sample-requests.py` examples on your laptop and then try the longer samples when using GKE.

---

# Deployment Guide: DEMUCS Music Separation on GKE

## Overview

This implementation deploys a music separation service on Google Kubernetes Engine (GKE). Users submit an MP3 through a Flask REST API. The application stores the original file in RustFS, queues a job in Redis, and uses a background DEMUCS worker to separate the audio into four tracks.

The separated MP3 files are stored in RustFS and can be retrieved through the REST API.

### Architecture

```text
Client
  |
  | HTTP request containing base64-encoded MP3
  v
GKE Ingress
  |
  v
Flask REST Service
  |                       |
  | Store original MP3    | Queue processing job
  v                       v
RustFS                    Redis
(queue bucket)            (toWorkers queue)
  ^                       |
  |                       v
  +---------------- DEMUCS Worker
                              |
                              | Separate into four stems
                              v
                        RustFS output bucket
                              |
                              v
                  bass / drums / vocals / other
                              |
                              v
                    REST download endpoints
```

### Technologies

- Google Kubernetes Engine (GKE) for container orchestration
- Google Artifact Registry for Docker images
- Google Cloud Build for container image builds
- Flask and Gunicorn for the REST API
- Redis for asynchronous job processing
- DEMUCS and PyTorch for music source separation
- RustFS for S3-compatible object storage
- Helm for installing RustFS
- Kubernetes Deployments, Services, Secrets, PVCs, and Ingress

## 1. Deployment Environment

The verified deployment used:

| Configuration | Value |
|---|---|
| Google Cloud project | `lab2-507502` |
| GKE cluster | `lab7-demucs` |
| Cluster zone | `us-central1-a` |
| Cluster mode | Standard |
| Node machine type | `e2-standard-4` |
| Initial node count | 1 |
| Artifact Registry location | `us-central1` |
| Artifact Registry repository | `lab7-images` |
| Kubernetes application namespace | `default` |
| RustFS namespace | `rustfs-ns` |

A different Google Cloud project or cluster can be used by changing the project-specific values in these commands and deployment manifests.

## 2. Prerequisites

Required tools:

- Google Cloud CLI (`gcloud`)
- `kubectl`
- Helm
- Git
- Python 3
- A Google Cloud project with active billing

Authenticate and configure the project:

```bash
gcloud auth login
gcloud config set project lab2-507502

gcloud services enable \
  container.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

Clone the repository:

```bash
git clone https://github.com/abhinaya-allu8/lab7-demucs.git
cd lab7-demucs
```

## 3. Create the GKE Cluster

The tested deployment uses one `e2-standard-4` node.

```bash
gcloud container clusters create lab7-demucs \
  --zone us-central1-a \
  --machine-type e2-standard-4 \
  --num-nodes 1 \
  --disk-size 50 \
  --disk-type pd-standard \
  --project lab2-507502
```

Connect kubectl to the cluster:

```bash
gcloud container clusters get-credentials lab7-demucs \
  --zone us-central1-a \
  --project lab2-507502
```

Verify:

```bash
kubectl get nodes
kubectl get storageclass
```

The tested RustFS deployment uses the `standard-rwo` StorageClass. Check which storage classes exist in a new cluster before deploying storage.

## 4. Create the Artifact Registry Repository

Create the repository:

```bash
gcloud artifacts repositories create lab7-images \
  --repository-format=docker \
  --location=us-central1 \
  --description="Lab 7 DEMUCS container images" \
  --project=lab2-507502
```

If the repository already exists, skip this creation step.

Build the REST container:

```bash
gcloud builds submit ./rest \
  --tag us-central1-docker.pkg.dev/lab2-507502/lab7-images/lab7-rest:v1 \
  --project=lab2-507502
```

Build the Worker container:

```bash
gcloud builds submit ./worker \
  --tag us-central1-docker.pkg.dev/lab2-507502/lab7-images/lab7-worker:v2 \
  --timeout=30m \
  --project=lab2-507502
```

The `v2` Worker image includes explicit NumPy, SciPy, and SoundFile dependencies needed by the DEMUCS runtime.

The Kubernetes deployment manifests reference these image names. If using another project, update the image paths in:

- `rest/rest-deployment.yaml`
- `worker/worker-deployment.yaml`

## 5. Deploy Redis

Deploy the Redis Deployment and Service:

```bash
kubectl apply -f redis/redis-deployment.yaml
kubectl apply -f redis/redis-service.yaml
```

Verify:

```bash
kubectl get pods -l app=redis
kubectl get svc redis
```

The REST service and background Worker communicate with Redis using the internal Kubernetes service name `redis` on port `6379`.

The application uses the `toWorkers` Redis queue for separation requests and a separate `logging` queue for processing messages.

## 6. Deploy RustFS Object Storage

RustFS replaces MinIO in this implementation and provides S3-compatible object storage for both uploaded MP3 files and generated separation results.

### 6.1 Obtain the RustFS Helm chart

The tested deployment used the RustFS Helm setup from the course's Kubernetes tutorial, under:

```text
kubernetes-tutorial/06-rustfs/
```

Obtain that tutorial repository and follow its RustFS-specific Helm chart instructions.

The deployed Helm release is named `rustfs` and runs in the `rustfs-ns` namespace.

### 6.2 Configure persistent storage

Use a private Helm values file based on the tutorial's RustFS configuration, selecting a StorageClass available in the cluster.

The verified deployment used:

```text
StorageClass: standard-rwo
RustFS data PVC: rustfs-data
RustFS logs PVC: rustfs-logs
Capacity: 1 GiB each
```

Keep the private values file out of version control. Do not commit RustFS access credentials.

### 6.3 Install the Helm release

Locate the Helm chart directory containing `Chart.yaml`, then install it using the private values configuration.

For example:

```bash
helm upgrade --install rustfs /path/to/rustfs-chart \
  --namespace rustfs-ns \
  --create-namespace \
  -f /path/to/rustfs-config.local.yaml
```

Replace the two paths with the actual chart directory and private values file from the course tutorial.

The private values file must configure the RustFS access credentials and persistent storage consistently with the deployment.

### 6.4 Create the application Secret

The REST service and Worker need credentials matching the RustFS server configuration.

Create the Secret in the `default` namespace:

```bash
kubectl create secret generic rustfs-secret \
  --from-literal=access-key='YOUR_RUSTFS_ACCESS_KEY' \
  --from-literal=secret-key='YOUR_RUSTFS_SECRET_KEY'
```

Replace the placeholders locally with the credentials configured for RustFS. Do not store real values in README files, public scripts, screenshots, or Git commits.

For an existing Secret, update it rather than creating a duplicate.

Both application Deployments reference this Kubernetes Secret.

### 6.5 Verify RustFS

```bash
kubectl get pods -n rustfs-ns
kubectl get svc -n rustfs-ns
kubectl get pvc -n rustfs-ns
```

The verified service endpoint is:

```text
rustfs-svc.rustfs-ns.svc.cluster.local:9000
```

The REST and Worker deployment manifests use this endpoint through their S3 configuration.

RustFS provides the following application buckets:

| Bucket | Purpose |
|---|---|
| `queue` | Stores original uploaded MP3 files |
| `output` | Stores the four separated MP3 tracks |

The REST service creates required buckets when they do not already exist.

## 7. Deploy the REST API

Apply the REST configuration:

```bash
kubectl apply -f rest/rest-deployment.yaml
kubectl apply -f rest/rest-service.yaml
```

Verify:

```bash
kubectl rollout status deployment/rest-server
kubectl get pods -l app=rest-server
kubectl get svc rest-service
```

The REST service listens on port `5000`.

For local testing, forward the service:

```bash
kubectl port-forward svc/rest-service 5000:5000
```

In another terminal:

```bash
curl http://127.0.0.1:5000/
```

Expected response:

```json
{
  "service": "Music Separation Server",
  "status": "running"
}
```

## 8. Deploy the DEMUCS Worker

Apply the Worker deployment:

```bash
kubectl apply -f worker/worker-deployment.yaml
```

Check the rollout:

```bash
kubectl rollout status deployment/demucs-worker
kubectl get pods -l app=demucs-worker
```

Watch Worker logs:

```bash
kubectl logs -f deployment/demucs-worker
```

The Worker performs the following operations:

1. Receives a queued job from Redis.
2. Downloads the original MP3 from the RustFS `queue` bucket.
3. Runs the selected DEMUCS separation model.
4. Generates bass, drums, vocals, and other MP3 tracks.
5. Uploads the separated MP3s to the RustFS `output` bucket.
6. Records processing messages in Redis.

The tested model is `mdx_extra`, which uses four component models during separation.

The first run may download model weights.

## 9. Configure the GKE Ingress

The repository includes:

```text
rest/rest-ingress.yaml
```

Deploy the ingress:

```bash
kubectl apply -f rest/rest-ingress.yaml
```

Inspect provisioning and backend health:

```bash
kubectl get ingress rest-ingress
kubectl describe ingress rest-ingress
```

Retrieve the public IP:

```bash
INGRESS_IP=$(kubectl get ingress rest-ingress \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

echo "$INGRESS_IP"
```

Test the public REST service:

```bash
curl "http://${INGRESS_IP}/"
curl "http://${INGRESS_IP}/apiv1/queue/"
```

The verified November 2026 deployment used a GKE-managed HTTP load balancer whose REST backend reported `HEALTHY`.

The public IP may change if the load balancer is recreated.

**Security note:** This demonstration uses HTTP and has no API authentication. Do not use it for sensitive or private audio files. For production use, add HTTPS, authentication, upload limits, and appropriate network protections.

## 10. REST API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | REST service health |
| GET | `/apiv1/queue/` | Inspect pending jobs |
| POST | `/apiv1/separate` | Submit an MP3 separation job |
| GET | `/apiv1/track/<hash>/<track>` | Download a separated MP3 |
| GET | `/apiv1/remove/<hash>/<track>` | Remove a separated MP3 |

Supported track names include:

```text
bass.mp3
base.mp3
drums.mp3
vocals.mp3
other.mp3
```

`base.mp3` is supported as an alias for the bass track.

An upload request contains a base64-encoded MP3, model selection, and an optional callback URL.

Example JSON request structure:

```json
{
  "mp3": "BASE64_ENCODED_MP3_CONTENT",
  "model": "mdx_extra",
  "callback": null
}
```

A successful submission returns HTTP `202` with a song hash.

## 11. End-to-End Testing

### 11.1 Submit a test MP3

The repository provides `data/short-hop.mp3`.

With port-forwarding active, run:

```bash
python3 - <<'PY'
import base64
from pathlib import Path
import requests

audio = base64.b64encode(
    Path("data/short-hop.mp3").read_bytes()
).decode("utf-8")

response = requests.post(
    "http://127.0.0.1:5000/apiv1/separate",
    json={
        "mp3": audio,
        "model": "mdx_extra",
        "callback": None
    },
    timeout=60
)

response.raise_for_status()
print(response.status_code, response.json())

Path("last-songhash.txt").write_text(
    response.json()["hash"]
)
PY
```

Expected HTTP status: `202`.

### 11.2 Check job processing

```bash
kubectl logs -f deployment/demucs-worker
```

Expected milestones include:

```text
Starting separation
Downloaded input MP3
Running DEMUCS
Uploaded bass.mp3
Uploaded drums.mp3
Uploaded vocals.mp3
Uploaded other.mp3
Completed separation
```

### 11.3 Download output tracks

After the Worker reports completion:

```bash
SONGHASH=$(cat last-songhash.txt)

mkdir -p output-test

for TRACK in bass drums vocals other; do
  curl --fail \
    "http://127.0.0.1:5000/apiv1/track/${SONGHASH}/${TRACK}.mp3" \
    --output "output-test/${TRACK}.mp3"
done

file output-test/*.mp3
```

All four downloads should be valid MP3 audio files.

### 11.4 Test track removal

```bash
curl -i \
  "http://127.0.0.1:5000/apiv1/remove/${SONGHASH}/other.mp3"
```

The expected result is HTTP `200`.

The deleted track should return HTTP `404`:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:5000/apiv1/track/${SONGHASH}/other.mp3"
```

An untouched track should remain accessible:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:5000/apiv1/track/${SONGHASH}/vocals.mp3"
```

Expected: `200`.

## 12. Verified Results

On November 4, 2026, the deployed application was tested through two independent access paths:

- Test A: local Kubernetes port-forward
- Test B: public GKE ingress

Results:

| Metric | Result |
|---|---|
| Total automated checks | 28 |
| Passed | 28 |
| Failed | 0 |
| Kubernetes application pod restarts | 0 |
| DEMUCS output tracks | 4 |
| Distinct output file hashes | 4 |
| REST ingestion and retrieval | Passed |
| `base.mp3` alias | Passed |
| Track removal behavior | Passed |
| Public ingress access | Passed |

All four generated tracks were recognized as valid MP3 audio. The REST API, Redis, Worker, and RustFS completed the end-to-end separation workflow successfully.

These results demonstrate successful functionality in the tested environment; they do not imply that production security, crash recovery, or arbitrary audio inputs have been fully validated.

## 13. Troubleshooting

### Worker fails with missing NumPy

Use the updated Worker dependency list and rebuild the `v2` container image.

### Worker is running but not processing

Check the Redis queue and Worker logs:

```bash
kubectl logs deployment/demucs-worker
kubectl get pods -l app=demucs-worker
```

### Track returns HTTP 404

Confirm that processing completed and that the requested track was uploaded to RustFS. A deleted track also correctly returns HTTP 404.

### RustFS connection fails

Verify the RustFS pod, Kubernetes service, matching credentials, Secret references, and endpoint:

```bash
kubectl get pods,svc,pvc -n rustfs-ns
kubectl get secret rustfs-secret
```

Do not print or commit decoded Secret values.

### GKE ingress returns HTTP 502 or 503

Inspect ingress backend health and the REST service's endpoints:

```bash
kubectl describe ingress rest-ingress
kubectl get endpoints rest-service
kubectl logs deployment/rest-server --tail=50
```

### Worker runs out of memory

Inspect pod events, resource limits, and node capacity:

```bash
kubectl describe pod -l app=demucs-worker
kubectl describe nodes
```

## 14. Shutdown and Cost Management

GKE nodes, persistent disks, Artifact Registry storage, and external load-balancer resources may incur charges.

After grading and demonstrations are complete, delete the cluster if it is no longer needed:

```bash
gcloud container clusters delete lab7-demucs \
  --zone us-central1-a \
  --project lab2-507502
```

Do not delete the cluster before completing the grading demonstration.

The Artifact Registry repository and any retained cloud resources may require separate cleanup.

## 15. Extra-Credit Implementation

### RustFS Object Storage 

MinIO was replaced with RustFS, installed using Helm and configured with persistent Kubernetes volumes. Both the REST service and Worker communicate with RustFS using the S3-compatible API.

### Google Kubernetes Engine 

The complete application runs on GKE, including REST API, Redis, DEMUCS Worker, and RustFS. The REST application is publicly accessible through a GKE-managed ingress and was successfully tested through that ingress.

Both extra-credit features were implemented and functionally verified. 
