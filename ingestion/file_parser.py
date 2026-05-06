import pandas as pd
import io
import json
from typing import List, Dict, Any
from utils.logger import logger

def parse_file_to_json(file_content: bytes, file_name: str) -> List[Dict[str, Any]]:
    """
    Generic file parser: Reads Excel/CSV and returns a list of dictionaries.
    """
    logger.info(f"Starting to parse file: {file_name}")
    try:
        if file_name.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        elif file_name.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise ValueError(f"Unsupported file format: {file_name}")
        
        # Convert DataFrame to JSON string to natively handle NaN, NaT, etc., then back to dict
        json_str = df.to_json(orient='records', date_format='iso')
        records = json.loads(json_str)
        
        logger.info(f"PARSED {len(records)} ROWS")
        if records:
            logger.info(f"Sample data (first 3 rows): {records[:3]}")
        return records
        
    except Exception as e:
        logger.error(f"Error parsing file {file_name}: {str(e)}")
        raise
