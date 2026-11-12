# Murf Finch speech-to-text: usage

Murf Finch transcribes speech to text in real time or in batch. It runs entirely
inside your AWS account with network isolation: audio and transcripts never leave
the endpoint.

The listing has two versions. Pick the one that matches your audio:

| Version | Languages |
|---|---|
| Finch Global | English, German, Spanish, French, Italian, Portuguese, Dutch |
| Finch Indic | Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Odia, Assamese, English (India) |

- Real-time endpoint: `InvokeEndpoint` with an audio file returns the full transcript.
- Streaming endpoint: `InvokeEndpointWithBidirectionalStream` takes audio as it is
  captured and returns transcripts as each phrase is recognized.
- Batch transform: one audio file per S3 object, one JSON transcript per output object.

## Recommended instances

| Instance | GPU | Notes |
|---|---|---|
| ml.g6.2xlarge (recommended) | NVIDIA L4 24 GB | Up to 64 concurrent real-time streams |
| ml.g6.xlarge | NVIDIA L4 24 GB | Supported |
| ml.g5.xlarge | NVIDIA A10G 24 GB | Supported |
| ml.g5.2xlarge | NVIDIA A10G 24 GB | Supported |

Batch transform runs on ml.g5.xlarge, ml.g6.xlarge and ml.g6.2xlarge. Scale out
with more instances or SageMaker auto scaling.

## Real-time and batch input

Send the audio file as the request body. WAV, FLAC, MP3, OGG and other common
formats are accepted.

`Content-Type: audio/wav` (or `application/octet-stream`)

Options go in the `X-Amzn-SageMaker-Custom-Attributes` header as comma-separated
`key=value` pairs, for example `language_code=de,timestamps_granularity=none`.

| Option | Required | Description |
|---|---|---|
| `language_code` | no | Language of the audio, e.g. `en`, `de`, `hi`. Detected automatically when omitted. |
| `timestamps_granularity` | no | `word` (default) returns word start and end times; `none` omits them. |
| `keyterms` | no | Words or phrases to recognize more reliably, separated by `\|`, e.g. `Murf\|Finch`. |

A real-time request is limited to 6 MB and 60 seconds by SageMaker; use batch
transform for longer files (up to one hour each).

## Output

```json
{
  "transcription_id": "6f1c2b9e",
  "language_code": "en",
  "language_probability": 0.99,
  "text": "He did not set a figure for the cuts, saying they will be made based on China's economic output.",
  "words": [{"text": "He", "start": 0.12, "end": 0.24, "type": "word"}],
  "audio_duration_secs": 6.36
}
```

`words` is empty when `timestamps_granularity` is `none`.

## Streaming

Open a bidirectional stream with `InvokeEndpointWithBidirectionalStream`. Pass
options in `ModelQueryString`, for example `language=hi&keywords=Murf,Finch`.

1. Optionally send one JSON text message describing the audio. Without it the
   endpoint expects 16-bit little-endian mono PCM at 16 kHz.

   ```json
   {"type": "AudioConfig", "codec": "pcm_s16le", "sample_rate": 16000, "channels": 1}
   ```

   `codec` is one of `pcm_s16le`, `mulaw`, `alaw` or `opus` (one packet per frame).
   `sample_rate` is one of 8000, 12000, 16000, 24000, 32000, 44100 or 48000.

2. Send audio as binary frames.

3. Receive a JSON message for each recognized phrase:

   ```json
   {
     "type": "Results",
     "transcript": "He did not set a figure for the cuts",
     "speech_final": false,
     "words": [{"word": "He", "start": 0.12, "end": 0.24}],
     "start_ms": 0.0,
     "end_ms": 2310.0
   }
   ```

4. Send `{"type": "Finalize"}` to end a turn and keep the stream open, or
   `{"type": "CloseStream"}` to flush the last phrase and close. While audio is
   paused, send `{"type": "KeepAlive"}` instead of silence.

## Pricing

Real-time and streaming usage is billed per minute of audio. Batch transform is
billed per instance-hour.

## Example

See [Murf-Finch-STT-on-SageMaker.ipynb](Murf-Finch-STT-on-SageMaker.ipynb) for an
end-to-end example: deploy, transcribe a file, stream audio and run a batch job.

## Sample audio

The files in [samples](samples) are from the
[FLEURS](https://huggingface.co/datasets/google/fleurs) dataset by Google,
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
