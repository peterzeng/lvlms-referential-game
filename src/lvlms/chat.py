from typing import List
from time import sleep
from ..data.image_utils import is_local_image_file, is_online_image, encode_resized_image

import warnings
# from pydantic.warnings import PydanticSerializationUnexpectedValue

warnings.filterwarnings(
    "ignore",
    # category=PydanticSerializationUnexpectedValue,
)


def construct_message(content_items: List[str] | str, 
                      role: str = "user", 
                      max_image_dim: int = 1024) -> dict:
    content = []

    if isinstance(content_items, str):
        content_items = [content_items]

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


def get_completion_fn(model, 
                      temperature: float = 0):
    '''Try to create a completion function for the given model.
    Tries local_via_openai first, then litellm.'''

    try:
        from .local_via_openai import get_openai_chat_completion as completion
        completion_fn = lambda messages: completion(
            model=model, messages=messages, temperature=temperature)
        
        # test the completion function
        completion_fn([construct_message("Hello!", role="user")])
        print("Using local_via_openai for model:", model)

        return completion_fn
    
    except Exception as e:
        pass

    if "gpt-5" in model:
        temperature = 1.0
        print("Setting temperature to 1.0 for gpt-5 models.")

    try:
        from litellm import completion

        def get_response(model, messages, temperature: float = 0):
            response = completion(
                model=model, messages=messages, temperature=temperature,
            )
            return response.choices[0].message.content
        
        print("Using litellm for model:", model)
        completion_fn = lambda messages: get_response(
            model=model, messages=messages, temperature=temperature)
        return completion_fn
    
    except Exception as e:
        print("Error creating completion function:", e)
        return None


class LVLMChat:

    def __init__(self, 
                 model="openai/gpt-4o-mini", 
                 completion_fn=None,
                 system_prompt=None, 
                 max_img_dim=1024, 
                 temperature=0, 
                 max_tries=5, 
                 keep_chat_history=True):

        if completion_fn is None:
            self.completion_fn = get_completion_fn(model=model, )
        else:
            self.completion_fn = completion_fn

        self.model = model
        self.max_img_dim = max_img_dim
        self.temperature = temperature
        self.max_tries = max_tries
        self.system_prompt = system_prompt
        self.keep_chat_history = keep_chat_history
        self.reset_chat()

    def reset_chat(self):
        self.messages = []
        if self.system_prompt is not None:
            self.messages.append(construct_message(self.system_prompt, role="system"))
   
    def get_chat_completion(self, content_items: List[str] | str) -> str:
        assistant_response = None
        message = construct_message(
            content_items, 
            role="user", 
            max_image_dim=self.max_img_dim
        )
        self.messages.append(message)

        for _ in range(self.max_tries):

            try:
                assistant_response = self.completion_fn(self.messages)
                break

            except Exception as e:
                print("Running into problem:", e)
                print("Retrying...")
                assistant_response = f"SOMETHING_WRONG: {e}"
                sleep(5)

        if not assistant_response.startswith("SOMETHING_WRONG"):
            assistant_response = assistant_response

            if self.keep_chat_history:
                self.messages.append(construct_message(
                    assistant_response, role="assistant"))
            else:
                self.reset_chat()

        return assistant_response

    def __call__(self, content_items: List[str] | str) -> str:
        return self.get_chat_completion(content_items)