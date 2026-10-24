"""Compute device selection for local model inference.

The same code runs on a laptop with an NVIDIA GPU, inside a CPU-only container, or on a
reviewer's machine without a GPU. `resolve_device` picks the best available option and
never fails: if a GPU is requested but unavailable we log a warning and fall back to CPU.
"""

from dataclasses import dataclass
from typing import Literal

import structlog

logger = structlog.get_logger(__name__)

DevicePreference = Literal["auto", "cuda", "cpu"]


@dataclass(frozen=True)
class DeviceInfo:
    device: str  # "cuda", "mps" or "cpu"
    name: str  # human readable, e.g. "NVIDIA GeForce RTX 4060 Laptop GPU"


def resolve_device(preference: DevicePreference = "auto") -> DeviceInfo:
    if preference == "cpu":
        return DeviceInfo("cpu", "CPU (forced by configuration)")

    try:
        import torch
    except ImportError:  # torch is optional for the hash/mock embedding provider
        return DeviceInfo("cpu", "CPU (torch not installed)")

    if torch.cuda.is_available():
        return DeviceInfo("cuda", torch.cuda.get_device_name(0))

    mps = getattr(torch.backends, "mps", None)
    if preference == "auto" and mps is not None and mps.is_available():
        return DeviceInfo("mps", "Apple Silicon GPU (MPS)")

    if preference == "cuda":
        logger.warning("cuda_requested_but_unavailable", fallback="cpu")
    return DeviceInfo("cpu", "CPU")
