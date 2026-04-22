from typing import Tuple
from litellm import completion
from litellm.types.utils import ModelResponse


def get_response(prompt: str,
                 model_name: str = "deepseek/deepseek-chat", 
                 experiment_condition: str = "no_tool_use", 
                 **kwargs) -> Tuple[ModelResponse, str]:
    tool_map = {
        "no_tool_use": [],
        # "with_web_search": [{"type": "web_search"}],
    } 
    tools = tool_map.get(experiment_condition)
    if tools is None:
        print(f"Unrecognized experiment_condition: {experiment_condition}. "
              "Defaulting to no tool use.")
        tools = []
    
    tool_choice = None if not tools else "auto"
    response = completion(model=model_name, 
                          tools=tools, tool_choice=tool_choice,
                          messages=[{"role": "user", "content": prompt}],
                          **kwargs)
    output_text = response.choices[0].message['content']
    return response, output_text