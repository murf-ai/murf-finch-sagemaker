# Murf Finch Speech-to-Text on Amazon SageMaker

Murf Finch transcribes speech to text in real time, as a live stream, or in batch.
It runs as an Amazon SageMaker endpoint inside your own AWS account with network
isolation: audio and transcripts never leave your account, and nothing is sent to Murf.

The AWS Marketplace listing has two versions. Pick the one that matches your audio:

| Version | Languages | Word timestamps |
|---|---|---|
| Finch Global | English, German, Spanish, French, Italian, Portuguese, Dutch | Not yet |
| Finch Indic | Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Odia, Assamese, English (India) | Yes |

Language is detected automatically, or you can set it per request.

**Contents:** [Get started in 15 minutes](#get-started-in-15-minutes) ·
[Choose an instance](#choose-an-instance) · [Transcribe files](#transcribe-files-real-time) ·
[Stream live audio](#stream-live-audio) · [Batch transform](#batch-transform) ·
[Accuracy and latency](#accuracy-and-latency) · [Billing](#billing) ·
[Troubleshooting](#troubleshooting) · [Security](#security-and-privacy) · [Support](#support)

## Get started in 15 minutes

Prefer a notebook? [Murf-Finch-STT-on-SageMaker.ipynb](Murf-Finch-STT-on-SageMaker.ipynb)
runs every step below, including streaming and batch, with the sample audio in this repo.

### 0. Before you start

- AWS permissions to subscribe and deploy: the managed policies
  `AWSMarketplaceManageSubscriptions` and `AmazonSageMakerFullAccess` (or equivalent).
- GPU quota. New accounts often have 0. Check, and request at least 1 if needed
  (quota increases can take a day, so ask early):

  ```bash
  aws service-quotas list-service-quotas --service-code sagemaker --region us-east-1 \
    --query "Quotas[?contains(QuotaName,'ml.g5.2xlarge for endpoint usage')].[QuotaName,Value]"
  ```

  For batch transform, check `ml.g6.2xlarge for transform job usage` as well.
- AWS CLI v2 or Python with `boto3`. Live streaming from Python needs Python 3.12+.

### 1. Subscribe and copy the model package ARN

1. Open the Murf Finch listing on AWS Marketplace, choose **Continue to subscribe**,
   and accept the offer. Nothing is charged until you run an endpoint or a job.
2. Choose **Continue to configuration**, select the version (Finch Global or Finch
   Indic) and your AWS Region, and copy the **model package ARN**. It is different
   in every Region. You can find it again later under
   **AWS Marketplace > Manage subscriptions > Murf Finch > Launch new configuration**.

### 2. Create an execution role (once per account)

```bash
aws iam create-role --role-name murf-finch-sagemaker \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"sagemaker.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name murf-finch-sagemaker \
  --policy-arn arn:aws:iam::aws:policy/AmazonSageMakerFullAccess
```

### 3. Deploy an endpoint

```bash
export AWS_REGION=us-east-1
export MODEL_PACKAGE_ARN="arn:aws:sagemaker:us-east-1:<account>:model-package/<murf-finch-...>"
export ROLE_ARN=$(aws iam get-role --role-name murf-finch-sagemaker --query Role.Arn --output text)
export NAME=murf-finch

aws sagemaker create-model --model-name $NAME --execution-role-arn $ROLE_ARN \
  --primary-container ModelPackageName=$MODEL_PACKAGE_ARN --enable-network-isolation

aws sagemaker create-endpoint-config --endpoint-config-name $NAME --production-variants \
  '[{"VariantName":"AllTraffic","ModelName":"'$NAME'","InstanceType":"ml.g5.2xlarge","InitialInstanceCount":1,
     "ContainerStartupHealthCheckTimeoutInSeconds":900,
     "RoutingConfig":{"RoutingStrategy":"LEAST_OUTSTANDING_REQUESTS"}}]'

aws sagemaker create-endpoint --endpoint-name $NAME --endpoint-config-name $NAME
aws sagemaker wait endpoint-in-service --endpoint-name $NAME   # about 8-10 minutes
```

`--enable-network-isolation` is required for AWS Marketplace models. Least-outstanding-requests
routing sends each new stream to the least busy instance, which matters once you run
more than one instance.

### 4. Transcribe your first file

```bash
aws sagemaker-runtime invoke-endpoint --endpoint-name $NAME \
  --content-type audio/wav --body fileb://samples/en_us_sample.wav out.json && cat out.json
```

```json
{"transcription_id": "449addcb-...", "language_code": "en", "language_probability": 1.0,
 "text": "he did not set a figure for the cuts saying they would be made based on china's economic output",
 "words": [], "audio_duration_secs": 6.36}
```

### 5. Stream live audio

```bash
pip install "aws-sdk-sagemaker-runtime-http2[awscrt]>=0.11" boto3     # Python 3.12+
python examples/stream.py --endpoint $NAME --region $AWS_REGION samples/en_us_sample.wav
# options: --language de, --bvc (suppress background voices), --raw (print every message)
```

```
partial: he did not set a figure for the cuts saying they will be made based on china's economic output
final:   he did not set a figure for the cuts saying they will be made based on china's economic output
```

### 6. Clean up

The instance is billed by AWS for as long as the endpoint exists, even with no traffic.

```bash
aws sagemaker delete-endpoint --endpoint-name $NAME
aws sagemaker delete-endpoint-config --endpoint-config-name $NAME
aws sagemaker delete-model --model-name $NAME
```

Your subscription stays active; deploy again any time.

## Choose an instance

Measured on Amazon SageMaker in us-east-2, November 2026: live 16 kHz streams of
FLEURS speech sent at real-time pace, 120 seconds per load level. "Streams" is the
highest load tested at which 90% of final transcripts arrived within 250 ms of the
end of speech.

| Instance | GPU | Live streams | Final transcript, p90 at that load | Best for |
|---|---|---|---|---|
| **ml.g5.2xlarge** (recommended) | NVIDIA A10G | 96 | 222 ms | Lowest cost per stream |
| ml.g6.xlarge | NVIDIA L4 | 64 | 217 ms | Lowest price per instance |
| ml.g6.2xlarge | NVIDIA L4 | 64 | 204 ms | |
| ml.g5.xlarge | NVIDIA A10G | 64 | 143 ms | |
| ml.g6e.xlarge | NVIDIA L40S | 96 | 90 ms | Lowest latency |

Streams are for Finch Global. Finch Indic stayed under 165 ms (p90) at 64 streams on
every instance above; our Hindi test set did not allow higher loads. With a single
stream, final transcripts arrive in 45-85 ms (p90) on all of them.

Other instance types are not supported in this version: ml.g4dn (NVIDIA T4) is too slow
for live use, and ml.g7e (NVIDIA Blackwell) does not start.

**Sizing:** instances = peak concurrent streams / streams per instance, rounded up,
plus one for redundancy. Add
[SageMaker auto scaling](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling.html)
on `ConcurrentRequestsPerModel` for variable traffic.

**GPU shortages:** popular GPU types are sometimes unavailable in an Availability Zone
(`InsufficientInstanceCapacity`). Give the endpoint a fallback list with
[instance pools](https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints-deploy-models.html):
replace `"InstanceType"` in step 3 with

```json
"InstancePools": [{"InstanceType": "ml.g5.2xlarge", "Priority": 1},
                  {"InstanceType": "ml.g6.xlarge",  "Priority": 2},
                  {"InstanceType": "ml.g6.2xlarge", "Priority": 3}],
"VariantInstanceProvisionTimeoutInSeconds": 300
```

Every type in the pool needs quota of at least 1.

## Transcribe files (real time)

`InvokeEndpoint` with the audio file as the request body returns the full transcript.
WAV, FLAC, MP3, OGG/Opus, M4A and other common formats are accepted.

- `Content-Type: audio/wav` (or `audio/mpeg`, `application/octet-stream`, ...)
- Up to **25 MB per request** (about 13 minutes of 16 kHz WAV; far longer for MP3 or
  Opus), answered within SageMaker's 60-second limit. Use batch transform for longer files.

Options go in the `X-Amzn-SageMaker-Custom-Attributes` header (`--custom-attributes`
in the CLI, `CustomAttributes` in boto3) as comma-separated `key=value` pairs, for
example `language_code=de,timestamps_granularity=none`.

| Option | Required | Description |
|---|---|---|
| `language_code` | no | Language of the audio, e.g. `en`, `de`, `hi`. Detected automatically when omitted. |
| `timestamps_granularity` | no | `word` (default) returns word start and end times in Finch Indic; `none` omits them. |
| `keyterms` | no | Words or phrases to recognize more reliably, separated by `\|`, e.g. `Murf\|Finch`. |

```python
import boto3, json
rt = boto3.client("sagemaker-runtime")
r = rt.invoke_endpoint(EndpointName="murf-finch", ContentType="audio/wav",
                       CustomAttributes="language_code=hi",
                       Body=open("samples/hi_in_sample.wav", "rb").read())
print(json.loads(r["Body"].read())["text"])
```

### Output

| Field | Always | Description |
|---|---|---|
| `text` | yes | The transcript. Finch Global returns lowercase text without punctuation. |
| `language_code` | yes | Detected or requested language. |
| `language_probability` | yes | Confidence of the language detection, 0 to 1. |
| `words` | yes | Finch Indic: each word with `start` and `end` in seconds. Empty in Finch Global or with `timestamps_granularity=none`. |
| `audio_duration_secs` | yes | Length of the audio; this is the billed duration. |
| `transcription_id` | yes | Unique ID; include it in support requests. |

Example outputs: [samples/output](samples/output).

## Stream live audio

Open a bidirectional stream with
[`InvokeEndpointWithBidirectionalStream`](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpointWithBidirectionalStream.html).
[examples/stream.py](examples/stream.py) is a complete Python client.

Options go in `ModelQueryString`, for example `language=hi&keywords=Murf,Finch`:

| Option | Description |
|---|---|
| `language` | One language (`en`, `hi`, `de`, ...), or a comma-separated set to detect from. Detected automatically when omitted. |
| `keywords` | Comma-separated words or phrases to recognize more reliably. |
| `commit_mode` | `vad` (default): a turn ends after a short silence. `manual`: a turn ends only when you send `Finalize`. |
| `vad_silence_threshold_secs` | Silence that ends a turn in `vad` mode. Default 0.55, range 0.192 to 3.0. Raise it for slow speakers, lower it for snappier agents. |
| `bvc` | `true` suppresses background voices (a TV, people nearby) before transcription. Off by default; the capacity figures in [Choose an instance](#choose-an-instance) were measured with it off. |

**You send:**

1. Optionally, one JSON text message describing the audio. Without it the endpoint
   expects 16-bit little-endian mono PCM at 16 kHz.
   ```json
   {"type": "AudioConfig", "codec": "pcm_s16le", "sample_rate": 16000, "channels": 1}
   ```
   `codec`: `pcm_s16le`, `mulaw`, `alaw` (telephony) or `opus` (one packet per frame).
   `sample_rate`: 8000, 12000, 16000, 24000, 32000, 44100 or 48000.
2. Audio as binary frames, ideally 20-100 ms each, at real-time pace.
3. Control messages as JSON text: `{"type": "Finalize"}` ends the current turn now and
   keeps the stream open; `{"type": "CloseStream"}` flushes and closes;
   `{"type": "KeepAlive"}` keeps a paused stream open (send it instead of silence).

**You receive** JSON text messages:

```json
{"type": "SessionStarted", "session_id": "20261112T103817Z_05a4...", "language": null}
{"type": "partial", "transcript": "he did not set a figure", "rawEvent": {"event": "Update", "turn_index": 0, ...}}
{"type": "final", "transcript": "he did not set a figure for the cuts saying they will be made based on china's economic output",
 "rawEvent": {"event": "EndOfTurn", "turn_index": 0, "audio_window_start": 0.916, "audio_window_end": 5.26,
              "language": "en", "language_confidence": 1.0, "words": []}}
```

- `partial` messages update the current turn as the speaker talks; show them as live captions.
- One `final` per turn carries the settled text; send it to your LLM or agent.
  A `final` with an empty transcript means the turn contained no speech.
- `rawEvent` adds timing (`audio_window_start`/`end`, seconds from stream start),
  the detected language, and, in Finch Indic, word timestamps.
- Errors arrive as `{"type": "Error", "message": "..."}`.

A stream closes after 10 seconds without a first message, or after 180 seconds
without audio or `KeepAlive`.

## Batch transform

Put one audio file per S3 object under an input prefix. Each output object
`<input name>.out` holds the same JSON as a real-time response. Files can be up to
one hour long.

```bash
aws sagemaker create-transform-job --transform-job-name finch-batch-1 --model-name $NAME \
  --transform-input '{"DataSource":{"S3DataSource":{"S3DataType":"S3Prefix","S3Uri":"s3://my-bucket/audio/"}},"ContentType":"audio/wav"}' \
  --transform-output '{"S3OutputPath":"s3://my-bucket/transcripts/"}' \
  --transform-resources '{"InstanceType":"ml.g6.2xlarge","InstanceCount":1}' \
  --max-payload-in-mb 100 --batch-strategy SingleRecord
```

Batch transform runs on ml.g6.2xlarge, ml.g6.xlarge and ml.g5.xlarge, and needs
"for transform job usage" quota for that type.

## Accuracy and latency

Word error rate on the FLEURS test sets (lower is better; text normalized before
scoring):

| Language | WER | Language | WER |
|---|---|---|---|
| English (US) | 5.2% | Italian | 3.4% |
| German | 5.5% | Dutch | 6.5% |
| Spanish (Latin America) | 2.6% | Portuguese (Brazil) | 5.6% |
| French | 5.5% | **Average, Finch Global** | **4.9%** |
| Hindi (Finch Indic) | 10.3% | | |

Latency from the end of speech to the final transcript (90th percentile) on one
ml.g5.2xlarge: 66 ms at 1 stream, 106 ms at 32, 150 ms at 64, 222 ms at 96. See
[Choose an instance](#choose-an-instance) for other types.

## Billing

- **Real-time and streaming:** per minute of audio, metered in fractions of a minute.
  Streams of PCM, mu-law or A-law audio are billed by the audio duration sent; Opus
  streams by session time. Pauses covered by `KeepAlive` are not billed for PCM streams.
- **Batch transform:** per instance-hour while the job runs.
- AWS separately bills the SageMaker instance hours. See the listing for current prices.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ResourceLimitExceeded` when creating the endpoint | No GPU quota for that type. Request an increase, or use another supported type. |
| Endpoint `Failed` with `InsufficientInstanceCapacity` | AWS has no free GPUs of that type in the Region right now. Retry, use an [instance pool](#choose-an-instance), or another Region. |
| Endpoint `Failed` health check | Use `ContainerStartupHealthCheckTimeoutInSeconds` of 900 and a supported instance type (ml.g4dn and ml.g7e are not). |
| `ValidationError` mentioning network isolation | Create the model with `--enable-network-isolation`. |
| HTTP 413 on `InvokeEndpoint` | File over 25 MB. Compress it (MP3/Opus), split it, or use batch transform. |
| `ModelError` with a 400 status | The audio could not be decoded, or `language_code` is not in this version. The message says which. |
| Stream fails with `UnsupportedTransportError` (Python) | Use `smithy_http.aio.crt.AWSCRTHTTPClient` as the transport, as in `examples/stream.py`. |
| Stream returns nothing | Audio format does not match `AudioConfig` (default is 16 kHz 16-bit mono PCM), or audio is all silence. |
| Transcript in the wrong language | Set `language_code` / `language` explicitly. Finch Global does not transcribe Indian languages; use Finch Indic. |

## Security and privacy

- The endpoint runs with network isolation: it cannot make outbound calls.
- Audio and transcripts stay in your account and are not used to train models.
- Endpoint logs in Amazon CloudWatch contain one line per request with status and
  timing, never audio or transcript text.

## Support

Email [support@murf.ai](mailto:support@murf.ai) with your AWS Region, instance type,
listing version, the `transcription_id` or `session_id`, and the error message. Murf
cannot see your requests or logs, so these details are what we need to help.

## Sample audio

The files in [samples](samples) are from the
[FLEURS](https://huggingface.co/datasets/google/fleurs) dataset by Google,
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
