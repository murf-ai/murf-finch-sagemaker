"""Stream a WAV file to a Murf Finch SageMaker endpoint and print transcripts as they arrive.

    pip install "aws-sdk-sagemaker-runtime-http2[awscrt]>=0.11" boto3   # Python 3.12+
    python examples/stream.py --endpoint my-finch-endpoint --region us-east-1 samples/en_us_sample.wav

The audio is sent in 100 ms chunks at real-time pace, as a microphone or phone line would.
The WAV must be 16-bit PCM, mono, at 8, 12, 16, 24, 32, 44.1 or 48 kHz.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import wave

import boto3
from aws_sdk_sagemaker_runtime_http2.client import AsyncSageMakerRuntimeHTTP2Client
from aws_sdk_sagemaker_runtime_http2.models import (
    InvokeEndpointWithBidirectionalStreamInput,
    RequestPayloadPart,
    RequestStreamEventPayloadPart,
)
from smithy_aws_core.identity import EnvironmentCredentialsResolver
from smithy_http.aio.crt import AWSCRTHTTPClient

CHUNK_S = 0.1


def client(region: str) -> AsyncSageMakerRuntimeHTTP2Client:
    session = boto3.Session(region_name=region)
    creds = session.get_credentials().get_frozen_credentials()
    os.environ.update(AWS_ACCESS_KEY_ID=creds.access_key, AWS_SECRET_ACCESS_KEY=creds.secret_key, AWS_REGION=region)
    if creds.token:
        os.environ["AWS_SESSION_TOKEN"] = creds.token
    url = session.client("sagemaker-runtime").meta.endpoint_url

    def plugin(cfg):
        cfg.endpoint_uri = f"{url}:8443"
        cfg.region = region
        cfg.aws_credentials_identity_resolver = EnvironmentCredentialsResolver()
        cfg.transport = AWSCRTHTTPClient()

    return AsyncSageMakerRuntimeHTTP2Client(plugins=[plugin])


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    ap.add_argument("--language", help="e.g. en, de, hi; detected automatically when omitted")
    ap.add_argument("--bvc", action="store_true", help="suppress background voices (TV, nearby speakers)")
    ap.add_argument("--raw", action="store_true", help="print every message as received")
    args = ap.parse_args()

    with wave.open(args.wav) as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1, "need 16-bit mono PCM WAV"
        rate, pcm = w.getframerate(), w.readframes(w.getnframes())

    query = "&".join(([f"language={args.language}"] if args.language else []) + (["bvc=true"] if args.bvc else []))
    extra = {"model_query_string": query} if query else {}
    stream = await client(args.region).invoke_endpoint_with_bidirectional_stream(
        InvokeEndpointWithBidirectionalStreamInput(endpoint_name=args.endpoint, **extra))
    output = (await stream.await_output())[1]

    async def send(data: bytes, text: bool = False) -> None:
        part = RequestPayloadPart(bytes_=data, data_type="UTF8" if text else "BINARY")
        await stream.input_stream.send(RequestStreamEventPayloadPart(value=part))

    async def sender() -> None:
        await send(json.dumps({"type": "AudioConfig", "codec": "pcm_s16le", "sample_rate": rate,
                               "channels": 1}).encode(), text=True)
        step = int(rate * CHUNK_S) * 2
        for i in range(0, len(pcm), step):
            await send(pcm[i:i + step])
            await asyncio.sleep(CHUNK_S)
        await send(b'{"type": "CloseStream"}', text=True)

    task = asyncio.create_task(sender())
    while True:
        event = await output.receive()
        if event is None:
            break
        raw = getattr(getattr(event, "value", None), "bytes_", None)
        if not raw:
            continue
        msg = json.loads(raw)
        if args.raw:
            print(json.dumps(msg, ensure_ascii=False))
        elif msg.get("type") == "final" and msg.get("transcript"):
            print("final:  ", msg["transcript"])
        elif msg.get("type") == "partial" and msg.get("transcript"):
            print("partial:", msg["transcript"])
        elif msg.get("type") == "Error":
            print("error:  ", msg.get("message"))
    await task
    await stream.input_stream.close()


if __name__ == "__main__":
    asyncio.run(main())
