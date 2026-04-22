import re
from collections import Counter
import numpy as np
import pandas as pd

# -------------------------
# Tokenization helpers
# -------------------------

STOP_WORDS = ['a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 
              'and', 'any', 'are', "aren't", 'as', 'at', 'be', 'because', 'been', 
              'before', 'being', 'below', 'between', 'both', 'but', 'by', "can't", 
              'cannot', 'could', "couldn't", 'did', "didn't", 'do', 'does', "doesn't", 
              'doing', "don't", 'down', 'during', 'each', 'few', 'for', 'from', 'further', 
              'had', "hadn't", 'has', "hasn't", 'have', "haven't", 'having', 'he', "he'd", 
              "he'll", "he's", 'her', 'here', "here's", 'hers', 'herself', 'him', 'himself', 
              'his', 'how', "how's", 'i', "i'd", "i'll", "i'm", "i've", 'if', 'in', 'into', 'is', 
              "isn't", 'it', "it's", 'its', 'itself', "let's", 'me', 'more', 'most', "mustn't", 'my', 
              'myself', 'no', 'nor', 'not', 'of', 'off', 'on', 'once', 'only', 'or', 'other', 'ought', 
              'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', "shan't", 'she', "she'd", "she'll", 
              "she's", 'should', "shouldn't", 'so', 'some', 'such', 'than', 'that', "that's", 'the', 'their', 
              'theirs', 'them', 'themselves', 'then', 'there', "there's", 'these', 'they', "they'd", "they'll", 
              "they're", "they've", 'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very', 
              'was', "wasn't", 'we', "we'd", "we'll", "we're", "we've", 'were', "weren't", 'what', "what's", 'when', 
              "when's", 'where', "where's", 'which', 'while', 'who', "who's", 'whom', 'why', "why's", 'with', "won't", 
              'would', "wouldn't", 'you', "you'd", "you'll", "you're", "you've", 'your', 'yours', 'yourself', 'yourselves']


def whitespace_tokens(text: str) -> list[str]:
    """Whitespace tokenization (keeps punctuation as part of tokens)."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return []
    text = str(text).strip()
    return text.split() if text else []


def tokenize(text: str, no_stop_words: bool = False, 
                      use_spacy: bool = False, nlp=None) -> list[str]:
    """Whitespace tokenization (keeps punctuation as part of tokens)."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return []

    if use_spacy and nlp is not None:
        doc = nlp(text)
        tokens = [token.text for token in doc if token.pos_ in ["NOUN", "ADJ", "VERB", "ADV", 'PROPN','NUM','PRON','ADP']]
        return tokens
    
    text = str(text).strip()
    tokens = text.split() if text else []
    if no_stop_words:
        tokens = [t for t in tokens if t not in STOP_WORDS]
    return tokens

_word_re = re.compile(r"[A-Za-z0-9]+")  # "word tokens only, no punctuation"

def word_tokens_no_punct(text: str) -> list[str]:
    """Word tokens only (drops punctuation). Keeps repetitions."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return []
    text = str(text).lower()
    return _word_re.findall(text)


def multiset_intersection_count(a_tokens: list[str], b_tokens: list[str]) -> int:
    """
    Multiset intersection size (counts repeats): sum(min(countA[w], countB[w])).
    This matches: 'tokens in case of repetition'.
    """
    ca, cb = Counter(a_tokens), Counter(b_tokens)
    return sum((ca & cb).values())


# -------------------------
# Word Novelty Rate (WNR) helpers
# -------------------------

def levenshtein_isd(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    """
    Token-level Levenshtein alignment counts:
      I = insertions, S = substitutions, D = deletions
    Unit costs; deterministic tie-break.
    """
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]  # "M","S","I","D"

    for i in range(1, n + 1):
        dp[i][0] = i
        back[i][0] = "D"
    for j in range(1, m + 1):
        dp[0][j] = j
        back[0][j] = "I"

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost_sub = 0 if ref[i - 1] == hyp[j - 1] else 1

            del_cost = dp[i - 1][j] + 1
            ins_cost = dp[i][j - 1] + 1
            sub_cost = dp[i - 1][j - 1] + cost_sub

            best = min(del_cost, ins_cost, sub_cost)
            dp[i][j] = best

            # Tie-break: prefer diagonal (match/sub), then insertion, then deletion
            if sub_cost == best:
                back[i][j] = "M" if cost_sub == 0 else "S"
            elif ins_cost == best:
                back[i][j] = "I"
            else:
                back[i][j] = "D"

    # backtrace
    i, j = n, m
    I = S = D = 0
    while i > 0 or j > 0:
        op = back[i][j]
        if op == "I":
            I += 1
            j -= 1
        elif op == "D":
            D += 1
            i -= 1
        elif op == "S":
            S += 1
            i -= 1
            j -= 1
        else:  # "M"
            i -= 1
            j -= 1

    return I, S, D


def wnr_from_tokens(ref: list[str], hyp: list[str]) -> float:
    """
    Word Novelty Rate (WNR): (Insertions + Substitutions) / len(ref)
    - ref is the previous round token list
    - hyp is the current round token list
    Returns NaN if ref is empty.
    """
    if len(ref) == 0:
        return np.nan
    I, S, _D = levenshtein_isd(ref, hyp)
    return (I + S) / len(ref)


# -------------------------
# ROUGE-L (F1) helpers (rouge-score)
# -------------------------
# Install: pip install rouge-score
try:
    from rouge_score import rouge_scorer  # type: ignore
    _ROUGE_SCORER = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)
except Exception:
    _ROUGE_SCORER = None


def lcs_length(a: list[str], b: list[str]) -> int:
    """Length of Longest Common Subsequence (token-level)."""
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return 0
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        ai = a[i - 1]
        row = dp[i]
        prev_row = dp[i - 1]
        for j in range(1, m + 1):
            if ai == b[j - 1]:
                row[j] = prev_row[j - 1] + 1
            else:
                row[j] = max(prev_row[j], row[j - 1])
    return dp[n][m]


def rouge_l_f1(ref: list[str], hyp: list[str]) -> float:
    """
    ROUGE-L F1 on token sequences.
    Uses `rouge-score` if installed; otherwise falls back to LCS-based F1.
    Returns NaN if ref or hyp is empty.
    """
    if len(ref) == 0 or len(hyp) == 0:
        return np.nan

    # Prefer rouge-score if available
    if _ROUGE_SCORER is not None:
        ref_str = " ".join(ref)
        hyp_str = " ".join(hyp)
        score = _ROUGE_SCORER.score(ref_str, hyp_str)["rougeL"]
        return float(score.fmeasure)

    # Fallback: LCS-based ROUGE-L F1
    lcs = lcs_length(ref, hyp)
    p = lcs / len(hyp)
    r = lcs / len(ref)
    return 0.0 if (p + r) == 0 else (2 * p * r) / (p + r)


# -------------------------
# Additional lexical overlap helpers
# -------------------------

def jaccard_unique(a: list[str], b: list[str]) -> float:
    """Jaccard overlap on UNIQUE tokens: |A∩B| / |A∪B|. Returns NaN if union empty."""
    sa, sb = set(a), set(b)
    u = len(sa | sb)
    if u == 0:
        return np.nan
    return len(sa & sb) / u


def sbert_score(tks1: list[str], tks2: list[str], sbert_model) -> float:
    """
    Compute SBERT cosine similarity between two strings.
    Returns a single float (typically in [0, 1] for normal sentences).
    """
    from sentence_transformers import util  
    
    text1 = " ".join(tks1)
    text2 = " ".join(tks2)
    emb1 = sbert_model.encode(text1, convert_to_tensor=True)
    emb2 = sbert_model.encode(text2, convert_to_tensor=True)

    # util.cos_sim returns a 1x1 tensor here
    score = util.cos_sim(emb1, emb2).item()
    return float(score)


# -------------------------
# Round column detection
# -------------------------

def get_round_col(df: pd.DataFrame, round_num: int):
    """
    Returns the column key for round_num in df, supporting:
      - column == round_num (int)
      - column == str(round_num)
      - MultiIndex columns containing round_num as one level
    """
    # exact matches
    if round_num in df.columns:
        return round_num
    if str(round_num) in df.columns:
        return str(round_num)

    # MultiIndex: look for any col tuple that contains round_num or str(round_num)
    if isinstance(df.columns, pd.MultiIndex):
        for col in df.columns:
            if round_num in col or str(round_num) in col:
                return col

    raise KeyError(f"Could not find a column for round {round_num}. Columns were: {df.columns}")


# -------------------------
# Metric computation (row-wise)
# -------------------------

def compute_red_metrics(df: pd.DataFrame,
                        group_cols: list[str] | None = None,
                        add_token_debug_cols: bool = False, 
                        no_stop_words: bool = True, 
                        use_spacy: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Computes per-row metrics and returns:
      (1) df_items: original df + metric columns (one row per item)
      (2) df_overall: overall (and optional grouped) averages

    group_cols: e.g. ["speaker_type"] or ["condition"] if you have those columns.

    Adds:
      - WNR: WNR12/WNR23/WNR34, WNRA, WNR14
      - ROUGE-L F1 (rouge-score): RL12/RL23/RL34, RLA, RL14
      - Additional overlap: COS*, JACC*
    """
    # Locate round columns robustly
    c1 = get_round_col(df, 1)
    c2 = get_round_col(df, 2)
    c3 = get_round_col(df, 3)
    c4 = get_round_col(df, 4)

    d = df.copy()

    # --- Length metrics (whitespace tokens) ---

    if use_spacy:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        nlp.remove_pipe("lemmatizer")
        nlp.add_pipe("lemmatizer", config={"mode": "lookup"}).initialize()
    else:
        nlp = None
    
    tok1 = d[c1].map(lambda s: tokenize(s, no_stop_words=no_stop_words, use_spacy=use_spacy, nlp=nlp))
    tok2 = d[c2].map(lambda s: tokenize(s, no_stop_words=no_stop_words, use_spacy=use_spacy, nlp=nlp))
    tok3 = d[c3].map(lambda s: tokenize(s, no_stop_words=no_stop_words, use_spacy=use_spacy, nlp=nlp))
    tok4 = d[c4].map(lambda s: tokenize(s, no_stop_words=no_stop_words, use_spacy=use_spacy, nlp=nlp))
    d["tok1"] = tok1  # for debugging
    d["tok2"] = tok2
    d["tok3"] = tok3
    d["tok4"] = tok4

    len1, len2, len3, len4 = tok1.map(len), tok2.map(len), tok3.map(len), tok4.map(len)

    # Avoid divide-by-zero if RED1 is empty
    denom1 = len1.replace(0, np.nan)

    d["len_RED1"] = len1
    d["len_RED2"] = len2
    d["len_RED3"] = len3
    d["len_RED4"] = len4

    # RALR = (3*len1 - len2 - len3 - len4)/(3*len1)
    d["RALR"] = (3 * len1 - len2 - len3 - len4) / (3 * denom1)

    # Round-specific length reduction vs RED1
    d["R2LR"] = (len1 - len2) / denom1
    d["R3LR"] = (len1 - len3) / denom1
    d["R4LR"] = (len1 - len4) / denom1

    # LRMM = average of indicators that length decreases each step
    dec12 = (len2 < len1).astype(float)
    dec23 = (len3 < len2).astype(float)
    dec34 = (len4 < len3).astype(float)
    d["LRMM"] = (dec12 + dec23 + dec34) / 3.0

    # --- Lexical overlap metrics (word tokens, no punctuation) ---

    wlen2 = tok2.map(len).replace(0, np.nan)
    wlen3 = tok3.map(len).replace(0, np.nan)
    wlen4 = tok4.map(len).replace(0, np.nan)

    inter12 = [multiset_intersection_count(a, b) for a, b in zip(tok1, tok2)]
    inter23 = [multiset_intersection_count(a, b) for a, b in zip(tok2, tok3)]
    inter34 = [multiset_intersection_count(a, b) for a, b in zip(tok3, tok4)]
    inter14 = [multiset_intersection_count(a, b) for a, b in zip(tok1, tok4)]

    # RALO = (1/3) * sum_{i=2..4} inters(RED_{i-1}, RED_i) / len(RED_i)
    d["RALO"] = ((np.array(inter12) / wlen2) + (np.array(inter23) / wlen3) + (np.array(inter34) / wlen4)) / 3.0

    # R4LO = inters(RED1, RED4)/len(RED4)
    d["R4LO"] = np.array(inter14) / wlen4

    # --- Word Novelty Rate (WNR): (Insertions + Substitutions)/len(previous_round) ---
    wnr12 = [wnr_from_tokens(a, b) for a, b in zip(tok1, tok2)]
    wnr23 = [wnr_from_tokens(a, b) for a, b in zip(tok2, tok3)]
    wnr34 = [wnr_from_tokens(a, b) for a, b in zip(tok3, tok4)]
    wnr14 = [wnr_from_tokens(a, b) for a, b in zip(tok1, tok4)]

    d["WNR12"] = wnr12
    d["WNR23"] = wnr23
    d["WNR34"] = wnr34
    d["WNRA"] = (np.array(wnr12) + np.array(wnr23) + np.array(wnr34)) / 3.0
    d["WNR14"] = wnr14

    # --- ROUGE-L F1 (rouge-score) ---
    rl12 = [rouge_l_f1(a, b) for a, b in zip(tok1, tok2)]
    rl23 = [rouge_l_f1(a, b) for a, b in zip(tok2, tok3)]
    rl34 = [rouge_l_f1(a, b) for a, b in zip(tok3, tok4)]
    rl14 = [rouge_l_f1(a, b) for a, b in zip(tok1, tok4)]

    d["RL12"] = rl12
    d["RL23"] = rl23
    d["RL34"] = rl34
    d["RLA"] = (np.array(rl12) + np.array(rl23) + np.array(rl34)) / 3.0
    d["RL14"] = rl14

    # --- Additional lexical overlap metrics ---
    from sentence_transformers import SentenceTransformer
    _sbert_model = SentenceTransformer("all-MiniLM-L6-v2")

    cos12 = [sbert_score(a, b, _sbert_model) for a, b in zip(tok1, tok2)]
    cos23 = [sbert_score(a, b, _sbert_model) for a, b in zip(tok2, tok3)]
    cos34 = [sbert_score(a, b, _sbert_model) for a, b in zip(tok3, tok4)]
    cos14 = [sbert_score(a, b, _sbert_model) for a, b in zip(tok1, tok4)]
    d["COS12"] = cos12
    d["COS23"] = cos23
    d["COS34"] = cos34
    d["COSA"] = (np.array(cos12) + np.array(cos23) + np.array(cos34)) / 3.0
    d["COS14"] = cos14

    jacc12 = [jaccard_unique(a, b) for a, b in zip(tok1, tok2)]
    jacc23 = [jaccard_unique(a, b) for a, b in zip(tok2, tok3)]
    jacc34 = [jaccard_unique(a, b) for a, b in zip(tok3, tok4)]
    jacc14 = [jaccard_unique(a, b) for a, b in zip(tok1, tok4)]
    d["JACC12"] = jacc12
    d["JACC23"] = jacc23
    d["JACC34"] = jacc34
    d["JACCA"] = (np.array(jacc12) + np.array(jacc23) + np.array(jacc34)) / 3.0
    d["JACC14"] = jacc14

    if add_token_debug_cols:
        d["wordlen_RED2"] = tok2.map(len)
        d["wordlen_RED3"] = tok3.map(len)
        d["wordlen_RED4"] = tok4.map(len)
        d["inters_12"] = inter12
        d["inters_23"] = inter23
        d["inters_34"] = inter34
        d["inters_14"] = inter14

        # Optional WNR op-count debug (I/S/D) per transition
        isd12 = [levenshtein_isd(a, b) for a, b in zip(tok1, tok2)]
        isd23 = [levenshtein_isd(a, b) for a, b in zip(tok2, tok3)]
        isd34 = [levenshtein_isd(a, b) for a, b in zip(tok3, tok4)]
        if len(isd12):
            d["wnr_I12"], d["wnr_S12"], d["wnr_D12"] = zip(*isd12)
        if len(isd23):
            d["wnr_I23"], d["wnr_S23"], d["wnr_D23"] = zip(*isd23)
        if len(isd34):
            d["wnr_I34"], d["wnr_S34"], d["wnr_D34"] = zip(*isd34)

        d["rouge_score_available"] = (_ROUGE_SCORER is not None)

    # -------------------------
    # Overall / grouped summary
    # -------------------------
    metric_cols = [
        "RALR", "R2LR", "R3LR", "R4LR", "LRMM",
        "RALO", "R4LO",
        "WNRA", "WNR14",
        "RLA", "RL14",
        "COSA", "COS14",
        "JACCA", "JACC14",
    ]

    def summarize(frame: pd.DataFrame) -> pd.Series:
        out = {}
        for m in metric_cols:
            out[m + "_mean"] = frame[m].mean(skipna=True)
        return pd.Series(out)

    if group_cols:
        df_overall = d.groupby(group_cols, dropna=False).apply(summarize).reset_index()
    else:
        df_overall = summarize(d).to_frame().T

    return d, df_overall


def computer_lexical_adaptation(df: pd.DataFrame,
                                no_stop_words: bool = True,
                                use_spacy: bool = True, 
                                against_t1_only: bool = False) -> pd.DataFrame:
    """
    Long-format lexical adaptation table.

    For each row in df, and for each round i in {1,2,3,4}:
      - round 1: metrics are defined as 1.0 (baseline)
      - round i>1: compare round i utterance ONLY to round 1 utterance if against_t1_only=True, else to round i-1 utterance

    Output columns:
      [pair_id, condition, round_ix, LEN, LO, WNR, RL, COS, JAC]

    Metric definitions (using the same tokenization/metrics as compute_red_metrics):
      - LEN: len(tokens_i) / len(tokens_{i-1})  (token length ratio; <1 means shorter)
      - LO:  multiset_intersection(prev, curr) / len(curr)  (overlap in current)
      - WNR: (Insertions + Substitutions) / len(prev)  (can be > 1)
      - RL:  ROUGE-L F1 (rouge-score if installed; else LCS fallback)
      - COS: SBERT cosine similarity (SentenceTransformer "all-MiniLM-L6-v2")
      - JAC: Jaccard similarity on unique token sets
    """
    # Locate round columns robustly
    c1 = get_round_col(df, 1)
    c2 = get_round_col(df, 2)
    c3 = get_round_col(df, 3)
    c4 = get_round_col(df, 4)

    # Load spaCy once (optional)
    if use_spacy:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        if "lemmatizer" in nlp.pipe_names:
            nlp.remove_pipe("lemmatizer")
        nlp.add_pipe("lemmatizer", config={"mode": "lookup"}).initialize()
    else:
        nlp = None

    # Load SBERT once
    from sentence_transformers import SentenceTransformer
    _sbert_model = SentenceTransformer("all-MiniLM-L6-v2")

    out_rows = []

    for _, r in df.iterrows():
        pair_id = r.get("pair_id", np.nan)
        condition = r.get("condition", np.nan)

        # Tokenize each round using the same tokenize() as compute_red_metrics
        t1 = tokenize(r[c1], no_stop_words=no_stop_words, use_spacy=use_spacy, nlp=nlp)
        t2 = tokenize(r[c2], no_stop_words=no_stop_words, use_spacy=use_spacy, nlp=nlp)
        t3 = tokenize(r[c3], no_stop_words=no_stop_words, use_spacy=use_spacy, nlp=nlp)
        t4 = tokenize(r[c4], no_stop_words=no_stop_words, use_spacy=use_spacy, nlp=nlp)

        # Round 1 baseline: always 1 for all metrics
        out_rows.append({
            "pair_id": pair_id,
            "condition": condition,
            "round_ix": 1,
            "Len Reduction Rate": 1.0,
            "Lexical Overlap": 1.0,
            "Word Novelty Rate": 1.0,
            "Rouge-L": 1.0,
            "SBERT Cosim": 1.0,
            "Jaccard": 1.0,
        })

        def step(prev: list[str], curr: list[str]) -> dict:
            prev_len = len(prev)
            curr_len = len(curr)

            # LR ratio
            LR = np.nan if prev_len == 0 else (curr_len / prev_len)

            # LO: overlap proportion in current
            LO = np.nan if curr_len == 0 else (multiset_intersection_count(prev, curr) / curr_len)

            # WNR
            WNR = wnr_from_tokens(prev, curr)

            # ROUGE-L F1
            RL = rouge_l_f1(prev, curr)

            # SBERT cosine similarity
            COS = sbert_score(prev, curr, _sbert_model)

            # Jaccard on unique tokens
            JAC = jaccard_unique(prev, curr)

            return {"Len Reduction Rate": LR, "Lexical Overlap": LO, "Word Novelty Rate": WNR, "Rouge-L": RL, "SBERT Cosim": COS, "Jaccard": JAC}

        # Round 2..4 step comparisons
        if against_t1_only:
            out_rows.append({"pair_id": pair_id, "condition": condition, "round_ix": 2, **step(t1, t2)})
            out_rows.append({"pair_id": pair_id, "condition": condition, "round_ix": 3, **step(t1, t3)})
            out_rows.append({"pair_id": pair_id, "condition": condition, "round_ix": 4, **step(t1, t4)})
        else:
            out_rows.append({"pair_id": pair_id, "condition": condition, "round_ix": 2, **step(t1, t2)})
            out_rows.append({"pair_id": pair_id, "condition": condition, "round_ix": 3, **step(t2, t3)})
            out_rows.append({"pair_id": pair_id, "condition": condition, "round_ix": 4, **step(t3, t4)})

    out = pd.DataFrame(out_rows)
    return out[["pair_id", "condition", "round_ix", "Len Reduction Rate", "Lexical Overlap", "Word Novelty Rate", "Rouge-L", "SBERT Cosim", "Jaccard"]]
