import os
import re
import logging
import argparse
import pandas as pd
from pathlib import Path
from src.data.utils import df_contains_keywords


logging.basicConfig(level=logging.INFO, 
                    format='[%(asctime)s] - %(levelname)s - %(message)s')


def find_headers(df):
    """
    Return the row indices for the header rows that contain
    1***1 (dogs) and 2***1 (baskets).
    """
    one_row = two_row = None

    for i in df.index:
        for j in df.columns:
            v = df.iat[i, j]
            if not isinstance(v, str):
                continue
            s = v.strip()
            # tolerant: any '1...1' / '2...1'
            if re.match(r"^1.*1$", s):
                one_row = i
            if re.match(r"^2.*1$", s):
                two_row = i
        if one_row is not None and two_row is not None:
            break

    return one_row, two_row


def find_round_cols(df, header_row, prefix):
    """
    Find columns for 1***1..1***4 or 2***1..2***4.

    Returns a mapping {round_index: column_index}.
    """
    pattern = re.compile(rf"^{prefix}.*([1-4])$")
    cols = {}

    for j in df.columns:
        v = df.iat[header_row, j]
        if not isinstance(v, str):
            continue
        m = pattern.match(v.strip())
        if m:
            r = int(m.group(1))    # 1,2,3,4
            cols[r] = j

    if len(cols) < 4:
        logging.warning(f"Warning: expected 4 round columns for prefix {prefix}, found {len(cols)}")

    return cols


def detect_card_column(df, header_row, end_row):
    """
    Heuristically detect which column contains the card numbers (1, 2, 3, ...),
    without relying on a 'Trials' header.

    We look at rows between header_row+1 and end_row and pick the column
    that has the most cells that are simple integers.
    """
    last_row = end_row if end_row is not None else (df.index.max() + 1)
    best_col = None
    best_count = 0

    for j in df.columns:
        count = 0
        for i in range(header_row + 1, last_row):
            v = df.iat[i, j]
            if v is None:
                continue
            s = str(v).strip()
            if s.isdigit():
                count += 1
        if count > best_count:
            best_count = count
            best_col = j

    if best_col is None or best_count == 0:
        raise ValueError(f"Could not detect card-number column below row {header_row}")

    return best_col


def parse_block(df, header_row, end_row, prefix, join_descriptions: bool=False):
    """
    Parse one block (dogs or baskets) into:

    {
      "CardX": {
        "Round1": [...],
        "Round2": [...],
        "Round3": [...],
        "Round4": [...]
      },
      ...
    }

    IMPORTANT: later rounds may occupy more rows than earlier ones.
    For each card, we take *all* rows from that card's row up to the next
    card's row, and we collect descriptions for every round within that slice.
    """
    if header_row is None:
        return {}

    round_cols = find_round_cols(df, header_row, prefix)
    card_col = detect_card_column(df, header_row, end_row)

    result = {}
    last_row = end_row if end_row is not None else (df.index.max() + 1)

    # 1) find all card rows
    card_rows = []
    for i in range(header_row + 1, last_row):
        v = df.iat[i, card_col]
        if v is None:
            continue
        s = str(v).strip()
        if s.isdigit():
            card_rows.append((i, int(s)))   # (row_index, card_id)

    # 2) for each card, look between its row and the next card row
    for idx, (start_row, card_id) in enumerate(card_rows):
        card_key = f"Card{card_id}"
        if card_key not in result:
            result[card_key] = {f"Round{r}": [] for r in range(1, 5)}

        # end boundary (exclusive)
        if idx + 1 < len(card_rows):
            end_row_card = card_rows[idx + 1][0]
        else:
            end_row_card = last_row

        # collect descriptions in each round column between start_row and end_row_card
        for r, col in round_cols.items():
            round_key = f"Round{r}"
            for i in range(start_row, end_row_card):
                cell = df.iat[i, col]

                if pd.isna(cell):
                    continue
                
                s = str(cell).strip()
                if not s:
                    continue
                # normalise internal whitespace
                s = " ".join(s.split())
                result[card_key][round_key].append(s)
            
            if join_descriptions:
                result[card_key][round_key] = " ".join(result[card_key][round_key])

    return result


def merge_dict(target, src):
    """Merge src into target, concatenating lists of descriptions."""
    for card, rounds in src.items():
        if card not in target:
            target[card] = {f"Round{r}": [] for r in range(1, 5)}
        for r_key, descs in rounds.items():
            target[card][r_key].extend(descs)


def restructure_one_file(path, output_csv: bool=False):
    df = pd.read_excel(path, header=None, dtype=str)
    one_header, two_header = find_headers(df)
    block1 = parse_block(df, one_header, two_header, prefix="1", join_descriptions=output_csv)
    block2 = parse_block(df, two_header, None, prefix="2", join_descriptions=output_csv)
    block1_df = pd.DataFrame.from_dict(block1).T
    block2_df = pd.DataFrame.from_dict(block2).T

    return block1_df, block2_df


def get_pair_code_from_filename(filename):
    m = re.search(r"pair(\d+)", filename)
    if m:
        return m.group(1)
    else:
        logging.warning(f"Warning: could not extract pair code from filename {filename}")
        return None


def classify_df_type(df):
    basket_kws = ["handle", "basket", "lid"]
    if df_contains_keywords(df, basket_kws).any():
        return "baskets"
    
    dogs_kws = ["dog", "puppy", "tail"]
    if df_contains_keywords(df, dogs_kws).any():
        return "dogs"
    
    return "unknown"


def restructure_all_files_and_save(input_dir, 
                                   output_dir: str=None,
                                   output_csv: bool=False):
    input_dir = Path(input_dir)

    if output_dir is None:
        output_dir = input_dir.parent / "restructured_entrainment_coding_data"
        dog_save_dir = output_dir / "dogs"
        basket_save_dir = output_dir / "baskets"

        os.makedirs(dog_save_dir, exist_ok=True)
        os.makedirs(basket_save_dir, exist_ok=True)
        

    num_file_processed = 0
    num_file_failed = 0
    for path in input_dir.glob("*.xls"):
        try:
            pair_code = get_pair_code_from_filename(path.name)
            block1_df, block2_df = restructure_one_file(path, output_csv)

            type1 = classify_df_type(block1_df)
            type2 = classify_df_type(block2_df)

            if type1 == "unknown" and type2 == "unknown":
                logging.warning(f"Warning: both blocks unknown type in file {path}, skipping.")
                continue

            if type1 == type2:
                logging.warning(f"Warning: both blocks same type ({type1}) in file {path}, skipping.")
                continue 

            if type1 == "baskets" or type2 == "dogs":
                if output_csv:
                    block1_df.index.name = "FirstRoundCardIndex"
                    block2_df.index.name = "FirstRoundCardIndex"
                    block1_df.to_csv(basket_save_dir / f"pair{pair_code}.csv", index=True)
                    block2_df.to_csv(dog_save_dir / f"pair{pair_code}.csv", index=True)
                else:
                    block1_df.to_json(basket_save_dir / f"pair{pair_code}.json", orient="index", indent=4)
                    block2_df.to_json(dog_save_dir / f"pair{pair_code}.json", orient="index", indent=4)
            else:
                if output_csv:
                    block1_df.index.name = "FirstRoundCardIndex"
                    block2_df.index.name = "FirstRoundCardIndex"
                    block1_df.to_csv(dog_save_dir / f"pair{pair_code}.csv", index=True)
                    block2_df.to_csv(basket_save_dir / f"pair{pair_code}.csv", index=True)
                else:
                    block1_df.to_json(dog_save_dir / f"pair{pair_code}.json", orient="index", indent=4)
                    block2_df.to_json(basket_save_dir / f"pair{pair_code}.json", orient="index", indent=4)
                block1_df.to_json(dog_save_dir / f"pair{pair_code}.json", orient="index", indent=4)
                block2_df.to_json(basket_save_dir / f"pair{pair_code}.json", orient="index", indent=4)
            
            num_file_processed += 1
            
        except Exception as e:
            logging.error(f"Failed to process {path}: {e}")
            num_file_failed += 1

    logging.info(f"Restructured file {path} and saved to {output_dir}")
    logging.info(f"Finished restructuring. Processed: {num_file_processed}, Failed: {num_file_failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Restructure entrainment coding Excel files into JSON format."
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        default="baskets_dogs_data/raw_entrainment_coding_data",
        help="Directory containing entrainment coding Excel files."
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=None,
        help="Directory to save restructured JSON files (default: sibling directory)."
    )

    parser.add_argument(
        "--output_csv",
        action="store_true",
        help="If true, join each list of descriptions as one string and save as CSV files."
    )

    args = parser.parse_args()

    restructure_all_files_and_save(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        output_csv=args.output_csv
    )