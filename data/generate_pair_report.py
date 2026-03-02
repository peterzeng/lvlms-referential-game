"""
Generate visual reports for human-AI pair sessions.
Creates a directory with:
- 4 round comparison images (Director's target vs Matcher's sequence)
- 1 transcript file with all 4 rounds of dialogue and accuracy

Works with pairs Excel files (ai-matcher or ai-director configurations).
"""

import argparse
import json
import os
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

# Configuration
IMAGES_DIR = "_static/images"
OUTPUT_BASE_DIR = "data/pair_reports"

# Grid layout
GRID_COLS = 4
GRID_ROWS = 3
CELL_SIZE = 150
PADDING = 10
LABEL_HEIGHT = 40


def parse_json_field(field_value):
    """Parse a JSON field from the data."""
    if pd.isna(field_value) or (isinstance(field_value, str) and field_value.strip() in ['', '[]']):
        return []
    try:
        if isinstance(field_value, str):
            return json.loads(field_value)
        return field_value
    except json.JSONDecodeError:
        return []


def get_round_data(row, round_num):
    """Extract data for a specific round from a pair row."""
    rp = f'round{round_num}'
    
    shared_grid = parse_json_field(row.get(f'{rp}_shared_grid', ''))
    matcher_sequence = parse_json_field(row.get(f'{rp}_matcher_sequence', ''))
    target_baskets = parse_json_field(row.get(f'{rp}_target_baskets', ''))
    
    # Get accuracy - handle both string and numeric
    accuracy = row.get(f'{rp}_matcher_sequence_accuracy', '')
    if pd.notna(accuracy):
        try:
            accuracy = f"{float(accuracy):.1f}"
        except (ValueError, TypeError):
            accuracy = str(accuracy)
    else:
        accuracy = 'N/A'
    
    # Get chat transcript
    director_transcript = row.get(f'{rp}_director_chat_transcript', '')
    matcher_transcript = row.get(f'{rp}_matcher_chat_transcript', '')
    
    # Use whichever transcript is available (they should be the same)
    transcript = director_transcript if pd.notna(director_transcript) and director_transcript else matcher_transcript
    if pd.isna(transcript):
        transcript = ''
    
    return {
        'shared_grid': shared_grid,
        'matcher_sequence': matcher_sequence,
        'target_baskets': target_baskets,
        'accuracy': accuracy,
        'transcript': transcript,
    }


def create_grid_image(sequence, images_dir, title, highlight_errors=None):
    """Create a grid image from a sequence of basket data."""
    width = GRID_COLS * (CELL_SIZE + PADDING) + PADDING
    height = GRID_ROWS * (CELL_SIZE + PADDING) + PADDING + LABEL_HEIGHT
    
    # Create image with dark background
    img = Image.new('RGB', (width, height), color=(40, 44, 52))
    draw = ImageDraw.Draw(img)
    
    # Try to load a font, fall back to default
    try:
        font = ImageFont.truetype("arial.ttf", 20)
        small_font = ImageFont.truetype("arial.ttf", 14)
    except:
        font = ImageFont.load_default()
        small_font = font
    
    # Draw title
    draw.text((PADDING, 5), title, fill=(255, 255, 255), font=font)
    
    # Sort sequence by position for display
    # For shared_grid: sort by row, col (reading order)
    # For matcher_sequence: sort by position number
    if sequence and 'row' in sequence[0]:
        sorted_seq = sorted(sequence, key=lambda x: (x.get('row', 0), x.get('col', 0)))
    else:
        sorted_seq = sorted(sequence, key=lambda x: x.get('position', 0))
    
    for idx, item in enumerate(sorted_seq):
        row = idx // GRID_COLS
        col = idx % GRID_COLS
        
        x = col * (CELL_SIZE + PADDING) + PADDING
        y = row * (CELL_SIZE + PADDING) + PADDING + LABEL_HEIGHT
        
        # Determine border color
        border_color = (100, 100, 100)  # Default gray
        if highlight_errors is not None:
            if idx in highlight_errors:
                border_color = (220, 50, 50)  # Red for errors
            else:
                border_color = (50, 180, 50)  # Green for correct
        
        # Draw cell border
        draw.rectangle([x-2, y-2, x+CELL_SIZE+2, y+CELL_SIZE+2], outline=border_color, width=3)
        
        # Load and paste basket image
        image_path = item.get('image', '')
        if image_path:
            # Handle both "images/XXX.png" and just "XXX.png" formats
            if image_path.startswith('images/'):
                image_path = image_path.replace('images/', '')
            
            full_path = os.path.join(images_dir, image_path)
            if os.path.exists(full_path):
                try:
                    basket_img = Image.open(full_path)
                    basket_img = basket_img.resize((CELL_SIZE, CELL_SIZE), Image.Resampling.LANCZOS)
                    img.paste(basket_img, (x, y))
                except Exception as e:
                    print(f"Error loading image {full_path}: {e}")
                    draw.rectangle([x, y, x+CELL_SIZE, y+CELL_SIZE], fill=(80, 80, 80))
            else:
                # Draw placeholder
                draw.rectangle([x, y, x+CELL_SIZE, y+CELL_SIZE], fill=(80, 80, 80))
                draw.text((x+10, y+60), "Missing", fill=(200, 200, 200), font=small_font)
        
        # Draw position number
        pos_label = str(idx + 1)
        draw.rectangle([x, y, x+25, y+20], fill=(0, 0, 0, 180))
        draw.text((x+5, y+2), pos_label, fill=(255, 255, 0), font=small_font)
    
    return img


def compare_sequences(target_seq, matcher_seq):
    """Compare sequences and return indices of errors."""
    errors = set()
    
    # Get target images in reading order (by row, col)
    target_images = []
    for item in sorted(target_seq, key=lambda x: (x.get('row', 0), x.get('col', 0))):
        target_images.append(item.get('image', ''))
    
    # Get matcher images in order by position
    matcher_images = []
    for item in sorted(matcher_seq, key=lambda x: x.get('position', 0)):
        matcher_images.append(item.get('image', ''))
    
    # Compare
    for i in range(min(len(target_images), len(matcher_images))):
        if target_images[i] != matcher_images[i]:
            errors.add(i)
    
    return errors


def create_round_visualization(round_num, round_data, images_dir, output_dir):
    """Create a visualization for a round."""
    shared_grid = round_data['shared_grid']
    matcher_sequence = round_data['matcher_sequence']
    accuracy = round_data['accuracy']
    
    if not shared_grid or not matcher_sequence:
        print(f"  Round {round_num}: No data available")
        return None
    
    # Find errors
    errors = compare_sequences(shared_grid, matcher_sequence)
    
    # Create director's grid (target)
    director_title = f"DIRECTOR'S TARGET SEQUENCE"
    director_img = create_grid_image(shared_grid, images_dir, director_title)
    
    # Create matcher's grid (with error highlighting)
    matcher_title = f"MATCHER'S SEQUENCE ({accuracy}% accuracy)"
    matcher_img = create_grid_image(matcher_sequence, images_dir, matcher_title, highlight_errors=errors)
    
    # Combine side by side
    gap = 40
    combined_width = director_img.width + matcher_img.width + gap
    combined_height = max(director_img.height, matcher_img.height) + 60
    
    combined = Image.new('RGB', (combined_width, combined_height), color=(30, 30, 35))
    draw = ImageDraw.Draw(combined)
    
    # Try to load a font
    try:
        title_font = ImageFont.truetype("arial.ttf", 28)
    except:
        title_font = ImageFont.load_default()
    
    # Draw round title
    round_title = f"Round {round_num}"
    draw.text((combined_width // 2 - 50, 10), round_title, fill=(255, 255, 255), font=title_font)
    
    # Paste grids
    combined.paste(director_img, (0, 50))
    combined.paste(matcher_img, (director_img.width + gap, 50))
    
    # Save
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"round_{round_num}_comparison.png")
    combined.save(output_path)
    print(f"  Saved: {output_path}")
    
    return output_path


def format_transcript(raw_transcript):
    """Convert raw transcript to human-readable format."""
    if not raw_transcript or pd.isna(raw_transcript):
        return "No transcript available."
    
    # The transcript format is: [HH:MM:SS] role: message
    # Split by the timestamp pattern
    lines = []
    
    # Pattern to match [HH:MM:SS] role: message
    pattern = r'\[(\d{2}:\d{2}:\d{2})\]\s*(director|matcher):\s*'
    
    # Split while keeping delimiters
    parts = re.split(pattern, raw_transcript, flags=re.IGNORECASE)
    
    # parts will be: ['', time1, role1, msg1, time2, role2, msg2, ...]
    i = 1
    while i < len(parts) - 2:
        timestamp = parts[i]
        role = parts[i + 1].upper()
        message = parts[i + 2].strip()
        
        if message:
            lines.append(f"[{timestamp}] {role}: {message}")
        
        i += 3
    
    if not lines:
        # Fallback: just return the raw transcript with some formatting
        return raw_transcript.replace('  ', '\n\n')
    
    return '\n\n'.join(lines)


def generate_transcript_file(row, output_dir, num_rounds=4):
    """Generate a human-readable transcript file for all rounds."""
    lines = []
    
    # Header
    pair_id = row.get('pair_id', 'unknown')
    session_code = row.get('session_code', 'unknown')
    
    # Determine if this is AI director or AI matcher
    director_code = row.get('director_participant_code', '')
    matcher_code = row.get('matcher_participant_code', '')
    
    if director_code == 'AI':
        ai_role = 'DIRECTOR'
        human_role = 'MATCHER'
        human_code = matcher_code
    else:
        ai_role = 'MATCHER'
        human_role = 'DIRECTOR'
        human_code = director_code
    
    lines.append("=" * 80)
    lines.append("SESSION TRANSCRIPT REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Pair ID:        {pair_id}")
    lines.append(f"Session Code:   {session_code}")
    lines.append(f"AI Role:        {ai_role}")
    lines.append(f"Human Role:     {human_role}")
    lines.append(f"Human Code:     {human_code}")
    lines.append("")
    
    # Session config
    config_name = row.get('session_config_name', '')
    basket_set = row.get('session_config_basket_set', '')
    director_view = row.get('session_config_director_view', '')
    prompt_version = row.get('prompt_version', '')
    reasoning_level = row.get('reasoning_level', '')
    
    lines.append("SESSION CONFIGURATION:")
    lines.append(f"  Config Name:    {config_name}")
    lines.append(f"  Basket Set:     {basket_set}")
    lines.append(f"  Director View:  {director_view}")
    lines.append(f"  Prompt Version: {prompt_version}")
    lines.append(f"  Reasoning:      {reasoning_level}")
    lines.append("")
    
    # Overall accuracy summary
    accuracies = []
    for round_num in range(1, num_rounds + 1):
        acc = row.get(f'round{round_num}_matcher_sequence_accuracy', None)
        if pd.notna(acc):
            accuracies.append(float(acc))
    
    if accuracies:
        avg_accuracy = sum(accuracies) / len(accuracies)
        lines.append(f"OVERALL ACCURACY: {avg_accuracy:.1f}% (avg across {len(accuracies)} rounds)")
    lines.append("")
    lines.append("=" * 80)
    
    # Per-round data
    for round_num in range(1, num_rounds + 1):
        round_data = get_round_data(row, round_num)
        
        lines.append("")
        lines.append(f"ROUND {round_num}")
        lines.append("-" * 40)
        lines.append(f"Accuracy: {round_data['accuracy']}%")
        lines.append("")
        
        lines.append("DIALOGUE:")
        lines.append("-" * 20)
        
        formatted_transcript = format_transcript(round_data['transcript'])
        lines.append(formatted_transcript)
        
        lines.append("")
        lines.append("=" * 80)
    
    # Write file
    os.makedirs(output_dir, exist_ok=True)
    transcript_path = os.path.join(output_dir, "transcript.txt")
    
    with open(transcript_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"  Saved transcript: {transcript_path}")
    return transcript_path


def get_images_dir(script_dir):
    """Find the images directory relative to the script location."""
    # Try relative to script directory
    possible_paths = [
        os.path.join(script_dir, '..', IMAGES_DIR),
        os.path.join(script_dir, IMAGES_DIR),
        IMAGES_DIR,
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return os.path.abspath(path)
    
    return IMAGES_DIR


def process_pair(row, output_dir, images_dir, num_rounds=4):
    """Process a single pair, generating images and transcript."""
    pair_id = row.get('pair_id', 'unknown')
    print(f"\nProcessing {pair_id}...")
    
    # Create output directory for this pair
    pair_output_dir = os.path.join(output_dir, pair_id)
    os.makedirs(pair_output_dir, exist_ok=True)
    
    # Generate round visualizations
    for round_num in range(1, num_rounds + 1):
        print(f"  Round {round_num}:")
        round_data = get_round_data(row, round_num)
        
        if round_data['shared_grid'] and round_data['matcher_sequence']:
            create_round_visualization(round_num, round_data, images_dir, pair_output_dir)
        else:
            print(f"    No grid/sequence data")
    
    # Generate transcript file
    generate_transcript_file(row, pair_output_dir, num_rounds)
    
    return pair_output_dir


def main():
    """Main function to process pairs Excel file and generate reports."""
    parser = argparse.ArgumentParser(
        description="Generate visual reports for human-AI pair sessions"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="Path to input pairs Excel file"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory (default: data/pair_reports/<input_filename>)"
    )
    parser.add_argument(
        "--pair-id", "-p",
        type=str,
        default=None,
        help="Process only a specific pair ID (default: process all)"
    )
    parser.add_argument(
        "--rounds", "-r",
        type=int,
        default=4,
        help="Number of rounds to process (default: 4)"
    )
    parser.add_argument(
        "--images-dir",
        type=str,
        default=None,
        help="Path to images directory (default: auto-detect)"
    )
    
    args = parser.parse_args()
    
    input_file = args.input
    num_rounds = args.rounds
    
    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        input_basename = Path(input_file).stem
        date_str = datetime.now().strftime('%Y-%m-%d')
        output_dir = os.path.join(OUTPUT_BASE_DIR, f"{input_basename}_{date_str}")
    
    # Determine images directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if args.images_dir:
        images_dir = args.images_dir
    else:
        images_dir = get_images_dir(script_dir)
    
    print(f"Input file:   {input_file}")
    print(f"Output dir:   {output_dir}")
    print(f"Images dir:   {images_dir}")
    print(f"Rounds:       {num_rounds}")
    
    # Load data
    print("\nLoading data...")
    if input_file.endswith('.xlsx'):
        df = pd.read_excel(input_file)
    else:
        df = pd.read_csv(input_file)
    
    print(f"Found {len(df)} pairs in file")
    
    # Filter to specific pair if requested
    if args.pair_id:
        df = df[df['pair_id'] == args.pair_id]
        if len(df) == 0:
            print(f"Error: Pair ID '{args.pair_id}' not found")
            return
        print(f"Processing single pair: {args.pair_id}")
    
    # Process each pair
    for idx, row in df.iterrows():
        process_pair(row.to_dict(), output_dir, images_dir, num_rounds)
    
    print(f"\n{'='*60}")
    print(f"Done! Reports saved to: {output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

