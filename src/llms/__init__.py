import os
from typing import Callable, Tuple

os.environ["VLLM_CONFIGURE_LOGGING"] = "0"

OPENAI_MODELS = [
    "gpt-5-nano-2025-08-07",
    "gpt-5-mini-2025-08-07",
]

OTHER_MODELS = [
    "deepseek/deepseek-chat",
    "deepseek/deepseek-reasoner",
]


def get_llm_response_function(llm_name: str, 
                              experiment_condition: str, 
                              **kwargs) -> Callable:
    
    if llm_name in OPENAI_MODELS or llm_name.startswith("gpt-"):
        from .openai import get_response as llm_response_function
    
    elif llm_name in OTHER_MODELS:
        from .others import get_response as llm_response_function

    else:
        from .local import LocalLLMWrapper
        llm_response_function = LocalLLMWrapper(
            model_name=llm_name,
            expirement_condition=experiment_condition,
            **kwargs
        )
        return llm_response_function
    
    
    def wrapped_llm_response_function(prompt: str) -> Tuple:
        return llm_response_function(
            prompt=prompt,
            model_name=llm_name,
            experiment_condition=experiment_condition,
            **kwargs
        )
    
    return wrapped_llm_response_function
