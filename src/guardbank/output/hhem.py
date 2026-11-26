"""HHEM-2.1-open groundedness scorer, loaded without `trust_remote_code`.

The scoring logic is vendored from `modeling_hhem_v2.py` in vectara/hallucination_evaluation_model
(Apache-2.0, (c) Vectara): a `T5ForTokenClassification` on google/flan-t5-base whose first-token
logits give P(consistent). Here the published safetensors weights are loaded into a plain T5 model,
so no code from the model repo is executed. See docs/specs/ml-output.md.
"""

from __future__ import annotations

import functools
from typing import Any

from guardbank.input.detectors import resolve_device

_WEIGHTS = "model.safetensors"
_PREFIX = "t5."  # the published state dict wraps the T5 model as `self.t5`


@functools.cache
def _load(name: str, revision: str, foundation: str, device: str) -> tuple[Any, Any]:
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file
    from transformers import AutoConfig, AutoTokenizer, T5ForTokenClassification

    model = T5ForTokenClassification(AutoConfig.from_pretrained(foundation, num_labels=2))
    state = load_file(hf_hub_download(name, _WEIGHTS, revision=revision))
    missing, unexpected = model.load_state_dict(
        {k.removeprefix(_PREFIX): v for k, v in state.items()}, strict=False
    )
    # The encoder embedding is stored once as `shared`; anything else missing is a real error.
    if unexpected or set(missing) - {"transformer.encoder.embed_tokens.weight"}:
        raise RuntimeError(f"HHEM weights do not fit: missing={missing}, unexpected={unexpected}")
    model.transformer.encoder.embed_tokens = model.transformer.shared
    return model.to(device).eval(), AutoTokenizer.from_pretrained(foundation)


class HHEMScorer:
    """score(claim, evidences) = max over chunks of P(claim is consistent with the chunk)."""

    def __init__(
        self, name: str, revision: str, foundation: str, prompt: str, max_length: int, device: str
    ) -> None:
        self.name, self.revision, self.foundation = name, revision, foundation
        self.prompt, self.max_length, self.device = prompt, max_length, device
        self.model: Any = None
        self._tokenizer: Any = None

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def score(self, claim: str, evidences: list[str]) -> float:
        if not evidences:
            return 0.0
        import torch

        if self.model is None:
            self.model, self._tokenizer = _load(
                self.name, self.revision, self.foundation, resolve_device(self.device)
            )
        texts = [self.prompt.format(text1=ev, text2=claim) for ev in evidences]
        batch = self._tokenizer(
            texts, return_tensors="pt", padding=True, truncation=True, max_length=self.max_length
        ).to(self.model.device)
        with torch.no_grad():
            logits = self.model(**batch).logits[:, 0, :]
        return float(torch.softmax(logits, dim=-1)[:, 1].max())
