"""
Clean up all_apps_wide CSV by removing columns that are mostly empty.
This removes partner perception columns from rounds 1-3 (only relevant for round 4).
"""
import pandas as pd
import sys

def clean_wide_export(input_file, output_file=None, empty_threshold=0.9):
    """
    Remove columns that are mostly empty (above threshold).
    
    Args:
        input_file: Path to the all_apps_wide CSV
        output_file: Path for cleaned output (defaults to input_file with '_cleaned' suffix)
        empty_threshold: Remove columns where this fraction of values are empty (default 0.9 = 90%)
    """
    if output_file is None:
        base = input_file.rsplit('.', 1)[0]
        output_file = f"{base}_cleaned.xlsx"
    
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    
    original_cols = len(df.columns)
    original_shape = df.shape
    print(f"Original shape: {original_shape[0]} rows, {original_shape[1]} columns")
    
    # Calculate empty fraction for each column
    empty_fractions = df.isna().sum() / len(df)
    
    # Also count empty strings as empty
    for col in df.columns:
        if df[col].dtype == 'object':
            empty_fractions[col] = (df[col].isna() | (df[col] == '')).sum() / len(df)
    
    # Identify columns to keep (below threshold)
    cols_to_keep = empty_fractions[empty_fractions < empty_threshold].index.tolist()
    cols_removed = [c for c in df.columns if c not in cols_to_keep]
    
    print(f"\nRemoving {len(cols_removed)} columns that are >{empty_threshold*100:.0f}% empty:")
    for col in cols_removed[:20]:  # Show first 20
        print(f"  - {col}")
    if len(cols_removed) > 20:
        print(f"  ... and {len(cols_removed) - 20} more")
    
    # Filter dataframe
    df_clean = df[cols_to_keep]
    
    print(f"\nCleaned shape: {df_clean.shape[0]} rows, {df_clean.shape[1]} columns")
    print(f"Removed {original_cols - len(cols_to_keep)} columns")
    
    # Save as Excel for better formatting
    print(f"\nSaving to {output_file}...")
    if output_file.endswith('.xlsx'):
        df_clean.to_excel(output_file, index=False, engine='openpyxl')
    else:
        df_clean.to_csv(output_file, index=False)
    
    print("Done!")
    return df_clean

if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "all_apps_wide-2025-12-29 (2).csv"
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    clean_wide_export(input_file, output_file)

