# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""An example showing how to use vLLM to serve multimodal models
and run online serving with OpenAI client.

Launch the vLLM server with the following command:

vllm serve Qwen/Qwen3-VL-4B-Instruct --max-model-len 58096
"""

import requests
from openai import OpenAI
from typing import List
from ..data.image_utils import is_local_image_file, is_online_image, encode_resized_image
    

openai_api_key = "EMPTY"
openai_api_base = "http://localhost:8000/v1"

client = OpenAI(
    api_key=openai_api_key,
    base_url=openai_api_base,
)


def is_server_up(url: str, timeout: float = 2.0) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code < 500
    except requests.RequestException:
        return False
    

if not is_server_up(f"{openai_api_base}/models"):
    raise RuntimeError("vLLM server is not running at {}".format(openai_api_base))


def construct_message(content_items: List[str], 
                      role: str = "user", 
                      max_image_dim: int = 1024) -> dict:
    content = []

    for item in content_items:
        if is_local_image_file(item):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": encode_resized_image(item, max_dim=max_image_dim)
                }
            })
        elif is_online_image(item):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": item
                }
            })
        else:
            content.append({
                "type": "text",
                "text": item
            })

    return {
        "role": role,
        "content": content
    }


def get_openai_chat_completion(model: str, 
                               messages: List[dict], 
                               temperature: float = 0.0,
                               max_completion_tokens: int | None = 500):
    
    response = client.chat.completions.create(
        messages=messages,
        model=model,
        max_completion_tokens=max_completion_tokens,
        temperature=temperature
    )

    result = response.choices[0].message.content

    return result