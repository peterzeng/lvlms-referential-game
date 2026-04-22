import torch
from vllm import LLM, SamplingParams
from vllm.outputs import RequestOutput
from typing import Tuple, List, Dict
import logging
from transformers import AutoTokenizer

logging.getLogger("vllm").setLevel(logging.ERROR)


def _is_ministral_3_model(model_name: str) -> bool:
    return model_name.startswith("mistralai/Ministral-3-")


class LocalLLMWrapper:
    def __init__(
        self,
        model_name: str = "meta-llama/Llama-3.2-3B-Instruct",
        expirement_condition: str = "no_tool_use",
        **kwargs,
    ):
        self.model_name = model_name
        self.expirement_condition = expirement_condition
        self.kwargs = kwargs

        self.model = LLM(
            model_name,
            dtype=torch.bfloat16,
            max_model_len=self.kwargs.get("max_model_len", 20_000),
        )

        self.is_ministral = _is_ministral_3_model(model_name)

        if not self.is_ministral:
            # normal HF flow
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        else:
            # let vLLM + mistral_common handle tokenization
            self.tokenizer = None

        self.sampling_params = SamplingParams(
            max_tokens=self.kwargs.get("max_tokens", 20_000),
        )

    def __call__(self, prompt: str) -> Tuple[RequestOutput, str]:
        return self.get_response(prompt)

    def get_response(self, prompt: str) -> Tuple[RequestOutput, str]:
        if self.is_ministral:
            return self._get_response_ministral(prompt)
        else:
            return self._get_response_hf(prompt)

    # ---------- non-Ministral (uses AutoTokenizer + generate) ----------

    def _get_response_hf(self, prompt: str) -> Tuple[RequestOutput, str]:
        messages: List[Dict[str, str]] = [{"role": "user", "content": prompt}]

        formatted_prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        outputs = self.model.generate(
            prompts=[formatted_prompt],
            sampling_params=self.sampling_params,
            use_tqdm=False,
        )

        resp: RequestOutput = outputs[0]
        output_text = resp.outputs[0].text
        return resp, output_text

    # ---------- Ministral-3 (uses chat API) ----------

    def _get_response_ministral(self, prompt: str) -> Tuple[RequestOutput, str]:
        conversation: List[Dict[str, str]] = [
            {"role": "user", "content": prompt},
        ]

        # NOTE: use llm.chat, not generate
        outputs = self.model.chat(
            messages=conversation,
            sampling_params=self.sampling_params,
            use_tqdm=False,
        )

        resp: RequestOutput = outputs[0]
        output_text = resp.outputs[0].text
        return resp, output_text
