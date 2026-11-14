"""The CV U-Net: a segmentation-models-pytorch U-Net on NISAR HH/HV.

The encoder is a ResNet50 pretrained by self-supervision on Sentinel-1 radar
(SSL4EO-S12, MoCo; distributed by TorchGeo). It was trained on C-band VV/VH in
dB; we feed L-band HH/HV in dB, standardized with our own channel statistics,
so co-pol goes where co-pol went and cross-pol where cross-pol went.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import segmentation_models_pytorch as smp
import torch

ENCODER = "resnet50"
S1_WEIGHTS = "SENTINEL1_ALL_MOCO"  # torchgeo ResNet50_Weights member
IN_CHANNELS = 2                    # HH, HV (dB)


def build_unet(encoder_weights: str | None = S1_WEIGHTS) -> torch.nn.Module:
    """U-Net with one output channel (water logit). encoder_weights=None gives random init."""
    model = smp.Unet(ENCODER, encoder_weights=None, in_channels=IN_CHANNELS, classes=1)
    if encoder_weights:
        from torchgeo.models import ResNet50_Weights

        state = getattr(ResNet50_Weights, encoder_weights).get_state_dict(progress=False)
        state = {k: v for k, v in state.items() if not k.startswith("fc.")}  # classifier head, unused
        # smp's encoder overrides load_state_dict and returns nothing, so call the base
        # method in strict mode: any missing or unexpected key raises instead of passing silently.
        torch.nn.Module.load_state_dict(model.encoder, state, strict=True)
    return model
