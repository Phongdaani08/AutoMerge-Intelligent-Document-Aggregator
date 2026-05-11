import pandas as pd
import io
import json
from typing import List, Dict, Any, Optional
from utils.logger import logger

def clean_and_validate_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Cleans string fields by stripping whitespace.
    Returns None if the row is entirely empty or null.
    """
    cleaned_row = {}
    is_empty = True
    for key, value in row.items():
        if isinstance(value, str):
            value = value.strip()
        cleaned_row[key] = value
        
        # Check if the row has any meaningful data
        if value is not None and str(value).strip() != "":
            is_empty = False
            
    if is_empty:
        return None
    return cleaned_row

def process_chunk(df: pd.DataFrame) -> List[Dict[str, Any]]:
    # Convert dates to ISO format strings to match previous to_json(date_format='iso') behavior
    for col in df.select_dtypes(include=['datetime64', 'datetimetz']).columns:
        df[col] = df[col].dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
    
    # Replace NaNs and NaTs with None to allow safe JSON conversion downstream
    df = df.where(pd.notnull(df), None)
    
    raw_records = df.to_dict(orient='records')
    records = []
    for row in raw_records:
        cleaned_row = clean_and_validate_row(row)
        if cleaned_row:
            records.append(cleaned_row)
    return records

def parse_file_in_chunks(file_path: str, file_name: str, chunk_size: int = 5000):
    """
    Generic file parser: Reads Excel/CSV and yields lists of dictionaries in chunks.
    """
    logger.info(f"Starting to parse file: {file_name} from {file_path} in chunks")
    try:
        if file_name.endswith('.csv'):
            # Stream the CSV incrementally
            for chunk_df in pd.read_csv(file_path, chunksize=chunk_size):
                records = process_chunk(chunk_df)
                if records:
                    yield records
        elif file_name.endswith(('.xls', '.xlsx')):
            # read_excel doesn't support chunksize natively, load once then chunk
            df = pd.read_excel(file_path)
            total_rows = len(df)
            for start_idx in range(0, total_rows, chunk_size):
                chunk_df = df.iloc[start_idx:start_idx+chunk_size].copy()
                records = process_chunk(chunk_df)
                if records:
                    yield records
        else:
            raise ValueError(f"Unsupported file format: {file_name}")
            
    except Exception as e:
        logger.error(f"Error parsing file {file_name}: {str(e)}")
        raise
