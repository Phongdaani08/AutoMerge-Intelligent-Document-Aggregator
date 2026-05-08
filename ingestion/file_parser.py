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

def parse_file_to_json(file_path: str, file_name: str) -> List[Dict[str, Any]]:
    """
    Generic file parser: Reads Excel/CSV and returns a list of dictionaries.
    """
    logger.info(f"Starting to parse file: {file_name} from {file_path}")
    try:
        if file_name.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_name.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_name}")
        
        # Convert DataFrame to JSON string to natively handle NaN, NaT, etc., then back to dict
        json_str = df.to_json(orient='records', date_format='iso')
        raw_records = json.loads(json_str)
        
        # Clean and validate
        records = []
        for row in raw_records:
            cleaned_row = clean_and_validate_row(row)
            if cleaned_row:
                records.append(cleaned_row)
        
        logger.info(f"PARSED AND CLEANED {len(records)} ROWS (Dropped {len(raw_records) - len(records)} empty rows)")
        if records:
            logger.info(f"Sample data (first 3 rows): {records[:3]}")
        return records
        
    except Exception as e:
        logger.error(f"Error parsing file {file_name}: {str(e)}")
        raise
