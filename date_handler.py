from datetime import datetime
from typing import Optional
import re


class DateHandler:
    """Simple date handler - converts any date reference to YYYYMMDD format."""

    def __init__(self, db_connection=None):
        """Initialize date handler."""
        self.db_connection = db_connection

    def parse_date_to_yyyymmdd(self, date_str: str) -> Optional[str]:
        """
        Parse date string in DD/MM/YYYY, MM/DD/YYYY, or YYYY-MM-DD formats to YYYYMMDD.
        Assumes DD/MM/YYYY format by default (01/12/2025 = December 1, 2025 = 20251201)
        """
        if not date_str:
            return None

        # Remove extra spaces
        date_str = date_str.strip()

        # Try DD/MM/YYYY format first (01/12/2025 = 1st Dec 2025)
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if match:
            day = match.group(1).zfill(2)
            month = match.group(2).zfill(2)
            year = match.group(3)
            return f"{year}{month}{day}"

        # Try YYYY-MM-DD format
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str)
        if match:
            return f"{match.group(1)}{match.group(2)}{match.group(3)}"

        # Try YYYYMMDD format (already correct)
        match = re.match(r"^(\d{8})$", date_str)
        if match:
            return match.group(1)

        return None

    def parse_user_input_dates(self, query: str):
        """Parse all dates from user query to YYYYMMDD format."""
        # Find all date patterns (DD/MM/YYYY, YYYY-MM-DD, YYYYMMDD)
        date_patterns = [
            r"(\d{1,2}/\d{1,2}/\d{4})",  # DD/MM/YYYY
            r"(\d{4}-\d{2}-\d{2})",  # YYYY-MM-DD
            r"\b(\d{8})\b",  # YYYYMMDD
        ]

        date_mapping = {}
        for pattern in date_patterns:
            for match in re.finditer(pattern, query):
                date_str = match.group(1)
                converted = self.parse_date_to_yyyymmdd(date_str)
                if converted and date_str not in date_mapping:
                    date_mapping[date_str] = converted

        return query, date_mapping

    def get_dateid_for_date(self, date_str: str) -> str:
        """Convert any date string to YYYYMMDD format."""
        converted = self.parse_date_to_yyyymmdd(date_str)
        return converted if converted else None

    def create_dateid_replacement_instructions(self, query: str) -> str:
        """Create instructions for LLM about DateID conversion."""
        _, date_mapping = self.parse_user_input_dates(query)

        if not date_mapping:
            return "\n### 🔢 CRITICAL: USE YYYYMMDD FORMAT FOR DATEID\nAlways use DateID in YYYYMMDD format (e.g., 20251201 for December 1, 2025)\n✅ WHERE f.dateid = YYYYMMDD (INTEGER, NO QUOTES)\n"

        instructions = ["\n### 🔢 CRITICAL DATE CONVERSION - USE f.dateid ONLY"]
        instructions.append("Date conversions found in your query:")
        instructions.append("")

        for original_date, converted_dateid in date_mapping.items():
            # Parse the converted dateid to show readable date
            year = converted_dateid[:4]
            month = converted_dateid[4:6]
            day = converted_dateid[6:8]
            instructions.append(
                f"- '{original_date}' → Use DateID: {converted_dateid} (Year={year}, Month={month}, Day={day})"
            )

        instructions.extend(
            [
                "",
                "🚨 ABSOLUTELY FORBIDDEN:",
                "- ❌ WHERE d.date = '2025-11-25'     (WILL FAIL)",
                "- ❌ WHERE d.date = ANY format     (WILL FAIL)",
                "- ❌ Any date column except f.dateid",
                "",
                "✅ ALWAYS USE:",
                f"- WHERE f.dateid = {list(date_mapping.values())[0]}  (converted from '{list(date_mapping.keys())[0]}')",
                "- Use INTEGER DateID, NO QUOTES, YYYYMMDD FORMAT",
                "",
            ]
        )

        return "\n".join(instructions)

    def get_date_context_for_llm(self, query: str) -> str:
        """Provide DateID context for LLM."""
        _, date_mapping = self.parse_user_input_dates(query)

        if not date_mapping:
            return ""

        context = ["\n### 📅 DATE INFORMATION\nDates found in your query:"]
        for original_date, converted_dateid in date_mapping.items():
            context.append(f"- {original_date} → DateID: {converted_dateid}")
        context.append("")

        return "\n".join(context)

    def extract_date_filters(self, query: str) -> dict:
        """Extract date filters from query."""
        _, date_mapping = self.parse_user_input_dates(query)

        return {
            "has_date_filter": len(date_mapping) > 0,
            "dates_found": list(date_mapping.keys()),
            "dateids": {v: v for v in date_mapping.values()},
        }
