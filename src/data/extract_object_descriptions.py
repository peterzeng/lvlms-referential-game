import json
import logging
import argparse
import pandas as pd
from tqdm import tqdm
from pathlib import Path
from string import Template
from src.llms.openai import get_response


logging.basicConfig(level=logging.INFO, 
                    format='[%(asctime)s] - %(levelname)s - %(message)s')

prompt_temp = """
This is an extractive task.

You will be given a transcript of a conversation between two participants engaged in a collaborative object-matching task. \
There are exactly $num_objects target objects. One participant (the describer) describes each target object, \
and the other participant (the matcher) attempts to identify them.

Your task is to extract the descriptive phrases used by the describer for each target object. 
- Extract phrases verbatim from the transcript. 
- Do not extract the whole utterance, only the descriptive phrases.
- Exclude disfluencies, fillers, and false starts (e.g., “um,” “uh,” “like”).
- Do not paraphrase or infer missing information.
- Each object may have one or multiple descriptive phrases.

Return the results in the following JSON format:

{
    "object_#1": "descriptive phrases for object 1",
    "object_#2": "descriptive phrases for object 2",
    ...
    "object_#$num_objects": "descriptive phrases for object $num_objects"
}

Example description phrases:

- doesn't have handle, tip of it is thicker than rest of body, brownish color, weaves are in squares if you look at it directly
- half circle, no handles, top tip of it is a little bit thicker than rest of body
- tip which is a little bit thicker than rest of body
- tip that is a little bit larger than body, looks a little bit thicker

Transcript:

$transcript

Output only the JSON object. Do not include any additional text or explanations.
""".strip()

prompt_tmp = Template(prompt_temp)


def parse_llm_response(response):
    response = response.replace("json", "").strip()
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")
        parsed = []
    return parsed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Restructure entrainment coding Excel files into JSON format."
    )
    parser.add_argument(
        "--input_fp",
        type=str,
        default="data/cleaned_human_to_human_transcripts.csv",
        help="File path to the cleaned human-to-human transcripts CSV."
    )

    parser.add_argument(
        "--num_objects",
        type=int,
        default=12,
        help="Number of target objects in the task."
    )

    parser.add_argument(
        "--output_col_name",
        type=str,
        default="llm_extracted_object_descriptions",
        help="Name of the column to store LLM extracted object descriptions."      
    )

    parser.add_argument(
        "--model_name",
        type=str,
        default="gpt-5-2025-08-07",
        help="Name of the LLM model to use for extraction."
    )

    args = parser.parse_args()
    input_fp = Path(args.input_fp)
    transcripts_df = pd.read_csv(input_fp)

    if args.output_col_name == "llm_extracted_object_descriptions" and args.model_name == "gpt-5-2025-08-07":
        args.output_col_name = "llm_extracted_object_descriptions_GPT_5"

    if args.output_col_name not in transcripts_df.columns:
        transcripts_df[args.output_col_name] = ""

    for ix, row in tqdm(transcripts_df.iterrows(), total=len(transcripts_df)):
        transcript = row.transcript
        prompt = prompt_tmp.substitute(transcript=transcript, num_objects=args.num_objects)

        llm_extracted_object_descriptions = row[args.output_col_name]
        if not pd.isnull(llm_extracted_object_descriptions) and (isinstance(llm_extracted_object_descriptions, str) 
                                                                 and llm_extracted_object_descriptions.strip() != ""):
            logging.info(f"Skipping index {ix} as it already has LLM extracted descriptions.")
            continue
        
        try:
            _, llm_response = get_response(
                prompt,
               model_name=args.model_name
            )

            transcripts_df.at[ix, args.output_col_name] = llm_response
            transcripts_df.at[ix, f"parsed_{args.output_col_name}"] = parse_llm_response(llm_response)
            transcripts_df.to_csv(input_fp, index=False)
        except Exception as e:
            logging.error(f"Error processing index {ix}: {e}")
            continue

    logging.info(f"Completed processing. Updated file saved to {input_fp}.")
