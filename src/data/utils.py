import pandas as pd
from IPython.display import display, HTML


def pretty_print(df: pd.DataFrame):
    return display(HTML(df.to_html().replace("\\n", "<br>")))


def df_contains_keywords(df: pd.DataFrame, keywords: list):
    """
    Returns a boolean Series indicating which rows of the DataFrame
    contain any of the given keywords in any column.

    Parameters:
        df (pd.DataFrame): The DataFrame to search.
        keywords (list): List of keywords (strings) to search for.

    Returns:
        pd.Series: Boolean mask where True indicates a match.
    """
    assert not df.empty, "DataFrame is empty"

    if isinstance(keywords, str):
        keywords = [keywords]
    
    assert len(keywords) > 0, "No keywords provided"


    # Convert everything to string for safe searching
    df_str = df.astype(str)

    # Build a regex OR pattern like "kw1|kw2|kw3"
    pattern = "|".join(map(str, keywords))

    # Check each cell for containing any keyword
    mask = df_str.apply(lambda col: col.str.contains(pattern, case=False, na=False))

    # Return a boolean series where any column matched
    return mask.any(axis=1)


def get_conversations(df, round_ix, pair_ix, 
                      return_entire_transcript=False, 
                      chunk_separator="\n\n"):
    sub = df.copy()[df["Round"] == round_ix]
    convs = sub[pair_ix].to_list()
    answer = sub["TargetObjectIndex"].to_list()

    if return_entire_transcript:
        return f"{chunk_separator}".join(convs), answer
    else:
        return convs, answer