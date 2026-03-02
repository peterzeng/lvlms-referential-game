import json
from datetime import datetime

# Your JSON data
data = [
    # ... paste your JSON here or load from a file ...
]

def format_json_to_chat(json_data):
    # If loading from a file instead, use:
    # with open('your_file.json', 'r') as f:
    #     json_data = json.load(f)
    
    output = []
    output.append(f"{'SENDER':<10} | {'MESSAGE'}")
    output.append("-" * 80)
    
    for entry in json_data:
        role = entry.get('sender_role', 'N/A').upper()
        text = entry.get('text', '')
        
        # Optional: Format timestamp to be more readable
        raw_ts = entry.get('timestamp', '')
        time_str = ""
        if raw_ts:
            dt = datetime.fromisoformat(raw_ts)
            time_str = dt.strftime("[%H:%M:%S]")

        # Create a nicely padded row
        output.append(f"{time_str} {role:<8}: {text}\n")
    
    return "\n".join(output)

# Run the formatter
chat_transcript = format_json_to_chat(data)

# Print to console
print(chat_transcript)

# Optional: Save to a text file
# with open('transcript.txt', 'w', encoding='utf-8') as f:
#     f.write(chat_transcript)