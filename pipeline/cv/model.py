"""The CV U-Net: a segmentation-models-pytorch U-Net on NISAR HH/HV.

The encoder is a ResNet50 pretrained by self-supervision on Sentinel-1 radar
(SSL4EO-S12, MoCo; distributed by TorchGeo). It was trained on C-band VV/VH in
dB; we feed L-band HH/HV in dB, standardized with our own channel statistics,
so co-pol goes where co-pol went and cross-pol where cross-pol went. With more
inputs (the "current+ref" channels hh, hv, hh_median, hv_median, hh_p90, hv_p90)
the pretrained first layer is repeated in the same co-pol / cross-pol order.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import segmentation_models_pytorch as smp
import torch

ENCODER = "resnet50"
S1_WEIGHTS = "SENTINEL1_ALL_MOCO"  # torchgeo ResNet50_Weights member
IN_CHANNELS = 2                    # HH, HV (dB)


def expand_conv1(weight: torch.Tensor, in_channels: int) -> torch.Tensor:
    """Pretrained first-layer weights (out, k, h, w) for in_channels inputs.

    Input channel i reuses pretrained channel i % k (even channels co-pol, odd
    channels cross-pol), and everything is scaled by k / in_channels so a scene
    whose channels agree gives the same first-layer response as before.
    """
    k = weight.shape[1]
    if in_channels == k:
        return weight
    return torch.stack([weight[:, i % k] for i in range(in_channels)], dim=1) * (k / in_channels)


def build_unet(encoder_weights: str | None = S1_WEIGHTS, in_channels: int = IN_CHANNELS,
               classes: int = 1) -> torch.nn.Module:
    """U-Net with `classes` output channels (1 = water logit). encoder_weights=None gives random init."""
    model = smp.Unet(ENCODER, encoder_weights=None, in_channels=in_channels, classes=classes)
    if encoder_weights:
        from torchgeo.models import ResNet50_Weights

        state = getattr(ResNet50_Weights, encoder_weights).get_state_dict(progress=False)
        state = {k: v for k, v in state.items() if not k.startswith("fc.")}  # classifier head, unused
        state["conv1.weight"] = expand_conv1(state["conv1.weight"], in_channels)
        # smp's encoder overrides load_state_dict and returns nothing, so call the base
        # method in strict mode: any missing or unexpected key raises instead of passing silently.
        torch.nn.Module.load_state_dict(model.encoder, state, strict=True)
    return model
