"""
Convert CSV to Excel format to preserve formatting
"""
import pandas as pd

# Read the CSV file
input_file = "all_apps_wide-2025-12-29 (2).csv"
output_file = "all_apps_wide-2025-12-29.xlsx"

print(f"Reading {input_file}...")
df = pd.read_csv(input_file)

print(f"Shape: {df.shape[0]} rows, {df.shape[1]} columns")
print(f"Columns: {list(df.columns[:10])}...")  # Show first 10 columns

print(f"\nWriting to {output_file}...")
df.to_excel(output_file, index=False, engine='openpyxl')

print(f"Done! Excel file saved as: {output_file}")

