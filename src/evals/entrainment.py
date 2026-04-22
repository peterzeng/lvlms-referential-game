import json


object_filename_map = {
  "rounds": [
    {
      "round": 1,
      "baskets": [
        "076.png", "001.png", "015.png", "009.png", "022.png", "033.png",
        "012.png", "040.png", "037.png", "019.png", "065.png", "017.png"
      ]
    },
    {
      "round": 2,
      "baskets": [
        "015.png", "037.png", "001.png", "022.png", "040.png", "076.png",
        "033.png", "019.png", "012.png", "065.png", "017.png", "009.png"
      ]
    },
    {
      "round": 3,
      "baskets": [
        "012.png", "009.png", "033.png", "076.png", "017.png", "037.png",
        "001.png", "040.png", "022.png", "019.png", "065.png", "015.png"
      ]
    },
    {
      "round": 4,
      "baskets": [
        "019.png", "022.png", "076.png", "012.png", "065.png", "001.png",
        "037.png", "015.png", "033.png", "009.png", "017.png", "040.png"
      ]
    },
    {
      "fullList": [
        "076.png", "001.png", "015.png", "009.png", "022.png", "033.png",
        "012.png", "040.png", "037.png", "019.png", "065.png", "017.png",
        "005.png", "039.png", "057.png", "081.png", "077.png", "078.png"
      ]
    }
  ]
}
object_filename_map = object_filename_map["rounds"]


def parse_llm_response(response, expected_len=12):
    if not isinstance(response, str):
        return []
    
    response = response.replace("json", "").strip()
    try:
        parsed = json.loads(response)
        if len(parsed) != expected_len:
            print("Warning: Parsed response length does not match expected length.")
            
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")
        parsed = []
    return parsed