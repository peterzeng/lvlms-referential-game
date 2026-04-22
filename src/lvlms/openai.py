from openai import OpenAI
from openai.types.responses.response import Response as OpenAIResponseObject

from typing import Tuple

client = OpenAI()

def get_response(prompt: str,
                 model_name: str = "gpt-5-nano-2025-08-07", 
                 **kwargs) -> Tuple[OpenAIResponseObject, str]:    

    response = client.responses.create(
        model=model_name,
        input=prompt,
        **kwargs
    )
    output_text = getattr(response, "output_text", None)
    return response, output_text