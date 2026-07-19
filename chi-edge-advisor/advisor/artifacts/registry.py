"""Registry of seeded Trovi artifacts.

Each artifact is one independently-retrievable namespace (keyed by
``artifact_id``). Metadata here is the routing signal; the prose lives in the
flattened files under ``grounding/<artifact_id>/`` (README + notebook markdown).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..config import settings


@dataclass
class ArtifactMeta:
    artifact_id: str
    repo: str
    title: str
    # routing/grounding facts
    machine_types: List[str]
    device_profiles: List[str]
    image: str
    architecture: str
    gpu: bool
    # keywords used by the router's task classifier
    tags: List[str] = field(default_factory=list)
    # subdirectory under grounding_dir (defaults to artifact_id)
    subdir: str = ""
    # logical partition keys for RouterTree (site -> use_case -> artifact)
    site: str = "CHI@Edge"
    # empty use_case means the artifact is its own use-case
    use_case: str = ""

    def dir(self) -> Path:
        return settings.grounding_dir / (self.subdir or self.artifact_id)


# Seed set requested for the prototype. Facts are taken verbatim from each
# artifact's grounded notebook (see grounding/<id>/).
ARTIFACTS: List[ArtifactMeta] = [
    ArtifactMeta(
        artifact_id="edge_ssh_image",
        repo="github.com/ChameleonCloud/edge_ssh_image",
        title="SSH on CHI@Edge containers",
        machine_types=["raspberrypi4-64"],
        device_profiles=[],
        image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
        architecture="arm64",
        gpu=False,
        tags=[
            "ssh", "remote access", "interactive shell", "login", "ubuntu",
            "networking", "floating ip", "port 22", "sshd", "terminal",
        ],
        use_case="access",
    ),
    ArtifactMeta(
        artifact_id="edge-picamera-image",
        repo="github.com/ChameleonCloud/edge-picamera-image",
        title="Pi Camera Module 3 on CHI@Edge",
        machine_types=["raspberrypi4-64"],
        device_profiles=["pi_libcamera"],
        image="ghcr.io/chameleoncloud/edge-picamera-image:latest",
        architecture="arm64",
        gpu=False,
        tags=[
            "camera", "picamera", "libcamera", "photo", "image capture",
            "video", "h264", "rpicam", "vision", "still", "recording",
        ],
        use_case="peripherals",
    ),
    ArtifactMeta(
        artifact_id="edge_sensehat_image",
        repo="github.com/ChameleonCloud/edge_sensehat_image",
        title="Sense HAT sensors on CHI@Edge",
        machine_types=["raspberrypi4-64"],
        device_profiles=["pi_sensehat", "pi_gpio"],
        image="ghcr.io/chameleoncloud/edge_sensehat_image:latest",
        architecture="arm64",
        gpu=False,
        tags=[
            "sensor", "sense hat", "temperature", "humidity", "pressure",
            "barometric", "imu", "accelerometer", "gyroscope", "magnetometer",
            "i2c", "gpio", "environmental", "waveshare", "adc",
        ],
        use_case="peripherals",
    ),
    ArtifactMeta(
        artifact_id="edge-cpu-inference",
        repo="github.com/teaching-on-testbeds/edge-cpu-inference",
        title="CPU-based ML inference on CHI@Edge",
        machine_types=["raspberrypi4-64"],
        device_profiles=[],
        image="python:3.9-slim",
        architecture="arm64",
        gpu=False,
        tags=[
            "inference", "machine learning", "ml", "model", "cpu",
            "image classification", "mobilenet", "tflite", "prediction",
            "ai", "neural network", "tensorflow lite", "edge ai",
        ],
        use_case="inference",
    ),
    ArtifactMeta(
        artifact_id="serve-edge-chi",
        repo="github.com/teaching-on-testbeds/serve-edge-chi",
        title="Serving ML models on edge devices (Raspberry Pi 5)",
        machine_types=["raspberrypi5"],
        device_profiles=[],
        image="quay.io/jupyter/minimal-notebook:latest",
        architecture="arm64",
        gpu=False,
        tags=[
            "model serving", "quantization", "int8", "onnx", "onnxruntime",
            "benchmark", "latency", "throughput", "raspberry pi 5",
            "pytorch", "food classification", "jupyter",
        ],
        use_case="inference",
    ),
]

ARTIFACTS_BY_ID = {a.artifact_id: a for a in ARTIFACTS}
