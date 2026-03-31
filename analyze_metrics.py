import os
import json
import re
from openai import OpenAI
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def calculate_overlap(re_i, re_prev):
    if not re_i or not re_prev:
        return 0.0
    
    def get_content_words(text):
        return re.findall(r'\b\w+\b', text.lower())
    
    words_i = get_content_words(re_i)
    words_prev = get_content_words(re_prev)
    
    if not words_i or not words_prev:
        return 0.0
    
    # Multiset overlap is the sum of minimum counts of each word in both multisets
    counts_i = {}
    for w in words_i: counts_i[w] = counts_i.get(w, 0) + 1
        
    counts_prev = {}
    for w in words_prev: counts_prev[w] = counts_prev.get(w, 0) + 1
        
    intersection_size = sum(min(counts_i.get(w, 0), counts_prev.get(w, 0)) for w in set(words_i) | set(words_prev))
    union_size = len(words_i) + len(words_prev) - intersection_size
    
    # Jaccard index is |A ∩ B| / |A ∪ B| (or Multiset Jaccard)
    return intersection_size / union_size if union_size > 0 else 0.0
    
def get_content_word_count(text):
    words = re.findall(r'\b\w+\b', text.lower())
    return len(words)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", required=True, help="Filename of the JSON trace")
    args = parser.parse_args()
    
    data_path = args.filename
    if not os.path.isabs(data_path) and not data_path.startswith("data/"):
        data_path = f"data/{data_path}"

    with open(data_path, 'r', encoding='utf-8') as f:
        content = f.read()
        if ']' in content:
            content = content[:content.rindex(']') + 1]
        data = json.loads(content)

    # Initialize OpenAI client 
    from dotenv import load_dotenv
    load_dotenv()
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    results = []
    # Using target_position as the canonical key between rounds for true tracking:
    # However, AI-AI sometimes refers to baskets by their position randomly. Wait, the extraction prompt extracts by "object_#". 
    # In the game, the director describes Target Basket 1..12 in each round. 
    # Importantly, Target Basket 1 in Round 1 == the basket with basket_id=data[round]['shared_grid'].find(position==1)['basket_id']
    # Wait: The extraction prompt uses "object_#1" etc. The describer calls it "Basket 1", "Basket 2" etc.
    # We must track the SAME BASKET across rounds regardless of its position in that round!
    
    re_history = {} # basket_id -> last round RE

    for round_idx, round_data in enumerate(data):
        r_num = round_data.get("round_number", round_idx + 1)
        status = round_data.get("status", {})
        accuracy = status.get("accuracy", 0.0)
        messages = status.get("messages", [])
        turn_count = status.get("turn_count", len(messages))
        
        # Get mapping from positional object_id to actual basket_id in this round
        # The AI director describes targets in the order 1-12 based on the grid positions. 
        # position "11" -> Object 1, "12" -> Object 2, "13" -> Object 3, "14" -> Object 4
        # "21" -> Object 5, "22" -> Object 6, "23" -> Object 7, "24" -> Object 8
        # "31" -> Object 9, "32" -> Object 10, "33" -> Object 11, "34" -> Object 12
        grid = round_data.get("shared_grid", [])
        # Let's map positions by their integer value if we sort ascending by (row, col)
        grid_sorted = sorted(grid, key=lambda x: (x['row'], x['col']))
        target_map = {} # Object index (1..12) -> basket_id
        for i, cell in enumerate(grid_sorted):
            target_map[i + 1] = cell.get("basket_id")

        total_words = sum(len(re.findall(r'\b\w+\b', m.get("text", ""))) for m in messages)
        
        # build transcript
        transcript_lines = []
        for m in messages:
            role = "describer" if m.get("sender_role") == "director" else "matcher"
            transcript_lines.append(f"{role}: {m.get('text', '')}")
        transcript_text = "\n".join(transcript_lines)

        prompt = f"""This is an extractive task.

You will be given a transcript of a conversation between two participants engaged in a collaborative object-matching task. There are exactly 12 target objects. One participant (the describer) describes each target object, and the other participant (the matcher) attempts to identify them.

Your task is to extract the descriptive phrases used by the describer for each target object. 
- Extract phrases verbatim from the transcript. 
- Do not extract the whole utterance, only the descriptive phrases.
- Exclude disfluencies, fillers, and false starts (e.g., "um", "uh", "like").
- Do not paraphrase or infer missing information.
- Each object may have one or multiple descriptive phrases.

Return the results in the following JSON format:

{{
    "object_#1": "descriptive phrases for object 1",
    "object_#2": "descriptive phrases for object 2",
    "object_#3": "descriptive phrases for object 3",
    "object_#4": "descriptive phrases for object 4",
    "object_#5": "descriptive phrases for object 5",
    "object_#6": "descriptive phrases for object 6",
    "object_#7": "descriptive phrases for object 7",
    "object_#8": "descriptive phrases for object 8",
    "object_#9": "descriptive phrases for object 9",
    "object_#10": "descriptive phrases for object 10",
    "object_#11": "descriptive phrases for object 11",
    "object_#12": "descriptive phrases for object 12"
}}

Example description phrases:

- doesn't have handle, tip of it is thicker than rest of body, brownish color, weaves are in squares if you look at it directly
- half circle, no handles, top tip of it is a little bit thicker than rest of body
- tip which is a little bit thicker than rest of body
- tip that is a little bit larger than body, looks a little bit thicker

Transcript:

{transcript_text}

Output only the JSON object. Do not include any additional text or explanations."""

        print(f"Extracting referring expressions for Round {r_num}...")
        try:
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[{"role": "user", "content": prompt}],
                response_format={'type': 'json_object'}
            )
            res_json = json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"LLM Error: {e}")
            res_json = {}

        total_re_len = 0
        total_overlap = 0.0
        overlap_count = 0
        
        for i in range(1, 13):
            obj_key = f"object_#{i}"
            re_text = res_json.get(obj_key, "")
            
            # Use basket_id to match identity across rounds
            basket_id = target_map.get(i)
            if not basket_id:
                # Fallback to positional tracking if grid not available
                basket_id = i

            # calculate metrics
            re_len = get_content_word_count(re_text)
            total_re_len += re_len
            
            if r_num > 1 and basket_id in re_history:
                overlap = calculate_overlap(re_text, re_history[basket_id])
                total_overlap += overlap
                overlap_count += 1
                
            re_history[basket_id] = re_text
            
        mean_re_len = total_re_len / 12
        mean_overlap = total_overlap / overlap_count if overlap_count > 0 else 0.0
        
        results.append({
            "round": r_num,
            "accuracy": accuracy,
            "turns": turn_count,
            "words": total_words,
            "mean_re_length": mean_re_len,
            "mean_lexical_overlap": mean_overlap
        })

    print("\n\n=== ANALYSIS RESULTS ===")
    print(f"{'Round':<10} {'Accuracy':<10} {'Turns':<10} {'Words':<10} {'Mean RE Len':<15} {'Lexical Overlap':<20}")
    print("-" * 80)
    for r in results:
        print(f"{r['round']:<10} {r['accuracy']:<10.1f} {r['turns']:<10} {r['words']:<10} {r['mean_re_length']:<15.1f} {r['mean_lexical_overlap']:<20.3f}")

    import csv
    csv_file = "metrics.csv"
    with open(csv_file, mode='w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["round", "accuracy", "turns", "words", "mean_re_length", "mean_lexical_overlap"])
        writer.writeheader()
        for r in results:
            writer.writerow(r)
    print(f"\nResults saved to {csv_file}")

if __name__ == "__main__":
    main()
