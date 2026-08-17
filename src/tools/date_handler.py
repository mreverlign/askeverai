"""Date parsing and SQL-generation context for HighTower queries."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from src.config.runtime import DATE_INPUT_ORDER


class DateHandler:
    """Parse user dates and describe the correct HighTower date filter.

    HighTower CSV exports use U.S. ``MM/DD/YYYY`` dates.  Ambiguous slash
    dates therefore default to MDY, while values that can only be interpreted
    one way (for example ``13/02/2025``) are inferred automatically.

    ``today_provider`` and ``date_input_order`` are optional primarily so the
    behavior can be tested deterministically.  Existing callers can continue
    to pass only the database connection.
    """

    _DATE_LIKE_RE = re.compile(
        r"(?<![\w/.-])(?:\d{1,2}/\d{1,2}/\d{4}|"
        r"\d{4}-\d{1,2}-\d{1,2}|\d{8})(?![\w/.-])"
    )
    _ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
    _COMPACT_RE = re.compile(r"\d{8}")
    _SLASH_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

    _MONTHS = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sept": 9,
        "sep": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }
    _MONTH_PATTERN = "|".join(
        sorted((re.escape(name) for name in _MONTHS), key=len, reverse=True)
    )
    _PERIOD_START_PATTERN = (
        r"on|in|during|before|after|between|since|from|through|until|"
        r"this|last|past|previous|next|q[1-4]|quarter|"
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|\d{4}"
    )

    # More specific intents must appear before the generic close/created ones.
    _NAMED_DATE_INTENTS: Sequence[Tuple[str, str, re.Pattern]] = (
        (
            "expectedclosedate",
            "expected close date",
            re.compile(
                r"\b(?:expectedclosedate|expected\s+(?:close|closing)\s+date|"
                r"expected\s+to\s+close)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "oppclosedate",
            "opportunity close date",
            re.compile(
                r"\b(?:oppclosedate|opp(?:ortunity)?\s+close(?:d|ing)?\s+date|"
                r"opportunity\s+(?:closed|closes|closing)\b)",
                re.IGNORECASE,
            ),
        ),
        (
            "createdfromdate",
            "created-from date",
            re.compile(
                r"\b(?:createdfromdate|created[ -]?from\s+date)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "shipdate",
            "ship date",
            re.compile(
                r"\b(?:shipdate|ship(?:ping|ped)?\s+date|shipped\s+"
                rf"(?:{_PERIOD_START_PATTERN}))\b",
                re.IGNORECASE,
            ),
        ),
        (
            "createddate",
            "created date",
            re.compile(
                r"\b(?:createddate|creat(?:ed|ion)\s+date|created\s+"
                rf"(?:{_PERIOD_START_PATTERN}))\b",
                re.IGNORECASE,
            ),
        ),
        (
            "closedate",
            "transaction close date",
            re.compile(
                r"\b(?:closedate|(?:transaction\s+)?close(?:d|ing)?\s+date|"
                rf"closed\s+(?:{_PERIOD_START_PATTERN}))\b",
                re.IGNORECASE,
            ),
        ),
    )

    def __init__(
        self,
        db_connection=None,
        *,
        today_provider: Optional[Callable[[], date]] = None,
        date_input_order: Optional[str] = None,
    ):
        self.db_connection = db_connection
        self._today_provider = today_provider or date.today

        configured_order = date_input_order or DATE_INPUT_ORDER
        configured_order = str(configured_order).strip().upper()
        self.date_input_order = (
            configured_order if configured_order in {"MDY", "DMY"} else "MDY"
        )

    @staticmethod
    def _as_date(value: date) -> date:
        return value.date() if isinstance(value, datetime) else value

    def _today(self) -> date:
        return self._as_date(self._today_provider())

    @staticmethod
    def _dateid(value: date) -> str:
        return value.strftime("%Y%m%d")

    @staticmethod
    def _iso(value: date) -> str:
        return value.isoformat()

    def parse_date_to_yyyymmdd(self, date_str: str) -> Optional[str]:
        """Convert one complete, valid date string to ``YYYYMMDD``.

        Accepted inputs are ISO ``YYYY-MM-DD``, compact ``YYYYMMDD``, and
        slash dates.  The full input must match; malformed suffixes and invalid
        calendar dates are rejected rather than normalized by guesswork.
        """
        if not isinstance(date_str, str) or not date_str.strip():
            return None

        value = date_str.strip()
        parsed: Optional[date] = None

        try:
            if self._ISO_RE.fullmatch(value):
                parsed = datetime.strptime(value, "%Y-%m-%d").date()
            elif self._COMPACT_RE.fullmatch(value):
                parsed = datetime.strptime(value, "%Y%m%d").date()
            else:
                slash_match = self._SLASH_RE.fullmatch(value)
                if not slash_match:
                    return None

                first, second, year = (int(part) for part in slash_match.groups())
                if first > 12 and second <= 12:
                    day, month = first, second
                elif second > 12 and first <= 12:
                    month, day = first, second
                elif first > 12 or second > 12:
                    return None
                elif self.date_input_order == "DMY":
                    day, month = first, second
                else:
                    month, day = first, second

                parsed = date(year, month, day)
        except (TypeError, ValueError):
            return None

        return self._dateid(parsed)

    def _date_candidates(
        self, query: str
    ) -> Tuple[Dict[str, str], List[str], List[Tuple[int, int]]]:
        mapping: Dict[str, str] = {}
        invalid: List[str] = []
        occupied_spans: List[Tuple[int, int]] = []

        for match in self._DATE_LIKE_RE.finditer(query or ""):
            original = match.group(0)
            occupied_spans.append(match.span())
            converted = self.parse_date_to_yyyymmdd(original)
            if converted:
                mapping.setdefault(original, converted)
            elif original not in invalid:
                invalid.append(original)

        return mapping, invalid, occupied_spans

    def parse_user_input_dates(self, query: str):
        """Return the query and every valid explicit date found within it."""
        date_mapping, _, _ = self._date_candidates(query or "")
        return query, date_mapping

    def get_dateid_for_date(self, date_str: str) -> Optional[str]:
        """Convert one supported date string to a DateID."""
        return self.parse_date_to_yyyymmdd(date_str)

    @staticmethod
    def _overlaps(span: Tuple[int, int], occupied: Sequence[Tuple[int, int]]) -> bool:
        return any(span[0] < other[1] and other[0] < span[1] for other in occupied)

    @staticmethod
    def _month_bounds(year: int, month: int) -> Tuple[date, date]:
        return date(year, month, 1), date(
            year, month, calendar.monthrange(year, month)[1]
        )

    @staticmethod
    def _quarter_bounds(year: int, quarter: int) -> Tuple[date, date]:
        first_month = ((quarter - 1) * 3) + 1
        start = date(year, first_month, 1)
        end_month = first_month + 2
        end = date(year, end_month, calendar.monthrange(year, end_month)[1])
        return start, end

    def _range(
        self,
        original: str,
        kind: str,
        start: date,
        end: date,
        span: Tuple[int, int],
    ) -> dict:
        return {
            "original": original,
            "kind": kind,
            "start_dateid": self._dateid(start),
            "end_dateid": self._dateid(end),
            "start_iso": self._iso(start),
            "end_iso": self._iso(end),
            "span": span,
        }

    def _relative_bounds(self, phrase: str, today: date) -> Tuple[date, date]:
        phrase = re.sub(r"^current\s+", "this ", phrase)
        if phrase == "this day":
            phrase = "today"
        if phrase == "today":
            return today, today
        if phrase == "yesterday":
            yesterday = today - timedelta(days=1)
            return yesterday, yesterday

        this_week_start = today - timedelta(days=today.weekday())
        if phrase == "this week":
            return this_week_start, this_week_start + timedelta(days=6)
        if phrase == "last week":
            start = this_week_start - timedelta(days=7)
            return start, start + timedelta(days=6)

        if phrase == "this month":
            return self._month_bounds(today.year, today.month)
        if phrase == "last month":
            previous_month_end = date(today.year, today.month, 1) - timedelta(days=1)
            return self._month_bounds(previous_month_end.year, previous_month_end.month)

        current_quarter = ((today.month - 1) // 3) + 1
        if phrase == "this quarter":
            return self._quarter_bounds(today.year, current_quarter)
        if phrase == "last quarter":
            if current_quarter == 1:
                return self._quarter_bounds(today.year - 1, 4)
            return self._quarter_bounds(today.year, current_quarter - 1)

        if phrase == "this year":
            return date(today.year, 1, 1), date(today.year, 12, 31)
        if phrase == "last year":
            return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)

        raise ValueError(f"Unsupported relative date phrase: {phrase}")

    def _extract_period_ranges(
        self, query: str, initially_occupied: Sequence[Tuple[int, int]]
    ) -> List[dict]:
        periods: List[dict] = []
        occupied = list(initially_occupied)

        def add(match: re.Match, kind: str, start: date, end: date) -> None:
            if self._overlaps(match.span(), occupied):
                return
            periods.append(self._range(match.group(0), kind, start, end, match.span()))
            occupied.append(match.span())

        relative_re = re.compile(
            r"\b(?:today|yesterday|(?:this|current)\s+(?:day|week|month|quarter|year)|"
            r"last\s+(?:week|month|quarter|year))\b",
            re.IGNORECASE,
        )
        for match in relative_re.finditer(query):
            phrase = " ".join(match.group(0).lower().split())
            start, end = self._relative_bounds(phrase, self._today())
            add(match, "relative", start, end)

        quarter_patterns = (
            (re.compile(r"\bq([1-4])\s+(?:of\s+)?((?:19|20)\d{2})\b", re.I), 1, 2),
            (re.compile(r"\b((?:19|20)\d{2})\s+q([1-4])\b", re.I), 2, 1),
            (
                re.compile(
                    r"\b(first|1st|second|2nd|third|3rd|fourth|4th)\s+"
                    r"quarter(?:\s+of)?\s+((?:19|20)\d{2})\b",
                    re.I,
                ),
                1,
                2,
            ),
        )
        quarter_names = {
            "first": 1,
            "1st": 1,
            "second": 2,
            "2nd": 2,
            "third": 3,
            "3rd": 3,
            "fourth": 4,
            "4th": 4,
        }
        for pattern, quarter_group, year_group in quarter_patterns:
            for match in pattern.finditer(query):
                quarter_text = match.group(quarter_group).lower()
                quarter = quarter_names.get(
                    quarter_text, int(quarter_text) if quarter_text.isdigit() else 0
                )
                year = int(match.group(year_group))
                start, end = self._quarter_bounds(year, quarter)
                add(match, "quarter", start, end)

        month_patterns = (
            re.compile(
                rf"\b({self._MONTH_PATTERN})\.?\s+(?:of\s+)?((?:19|20)\d{{2}})\b",
                re.IGNORECASE,
            ),
            re.compile(
                rf"\b((?:19|20)\d{{2}})\s+({self._MONTH_PATTERN})\.?\b",
                re.IGNORECASE,
            ),
        )
        for pattern_number, pattern in enumerate(month_patterns):
            for match in pattern.finditer(query):
                if pattern_number == 0:
                    month_text, year_text = match.group(1), match.group(2)
                else:
                    year_text, month_text = match.group(1), match.group(2)
                month = self._MONTHS[month_text.lower()]
                start, end = self._month_bounds(int(year_text), month)
                add(match, "month", start, end)

        numeric_month_re = re.compile(
            r"(?<![\w-])((?:19|20)\d{2})-(0[1-9]|1[0-2])(?![\w-])"
        )
        for match in numeric_month_re.finditer(query):
            start, end = self._month_bounds(int(match.group(1)), int(match.group(2)))
            add(match, "month", start, end)

        year_re = re.compile(r"(?<![\w/.-])((?:19|20)\d{2})(?![\w/.-])")
        for match in year_re.finditer(query):
            year = int(match.group(1))
            add(match, "year", date(year, 1, 1), date(year, 12, 31))

        periods.sort(key=lambda item: item["span"])
        return periods

    def _date_target(self, query: str) -> dict:
        for column, label, pattern in self._NAMED_DATE_INTENTS:
            if pattern.search(query or ""):
                return {
                    "column": f"f.{column}",
                    "column_name": column,
                    "label": label,
                    "uses_dateid": False,
                }
        return {
            "column": "f.dateid",
            "column_name": "dateid",
            "label": "transaction/reporting date",
            "uses_dateid": True,
        }

    def _analysis(self, query: str) -> dict:
        query = query or ""
        mapping, invalid_dates, occupied = self._date_candidates(query)
        ranges = self._extract_period_ranges(query, occupied)

        for match in self._DATE_LIKE_RE.finditer(query):
            original = match.group(0)
            converted = mapping.get(original)
            if not converted:
                continue
            parsed = datetime.strptime(converted, "%Y%m%d").date()
            ranges.append(self._range(original, "date", parsed, parsed, match.span()))
        ranges.sort(key=lambda item: item["span"])

        # Turn natural two-ended periods into one range rather than presenting
        # two equality predicates to the model.
        pair_patterns = (
            re.compile(r"\bbetween\s+(.+?)\s+and\s+(.+?)(?=$|[,;.])", re.I),
            re.compile(
                r"\bfrom\s+(.+?)\s+(?:to|through|until)\s+(.+?)(?=$|[,;.])", re.I
            ),
        )
        for pair_pattern in pair_patterns:
            pair_match = pair_pattern.search(query)
            if not pair_match:
                continue
            pair_span = pair_match.span()
            contained = [
                item
                for item in ranges
                if pair_span[0] <= item["span"][0] and item["span"][1] <= pair_span[1]
            ]
            if len(contained) >= 2:
                first, last = contained[0], contained[-1]
                ranges = [item for item in ranges if item not in contained]
                ranges.append(
                    self._range(
                        pair_match.group(0),
                        "between",
                        datetime.strptime(first["start_iso"], "%Y-%m-%d").date(),
                        datetime.strptime(last["end_iso"], "%Y-%m-%d").date(),
                        pair_span,
                    )
                )
                break

        comparison = None
        if len(ranges) == 1:
            before = query[: ranges[0]["span"][0]].lower()
            if re.search(r"\b(?:on\s+or\s+after|since|from)\s*$", before):
                comparison = "gte"
            elif re.search(r"\bafter\s*$", before):
                comparison = "gt"
            elif re.search(r"\b(?:on\s+or\s+before|through|until|up\s+to)\s*$", before):
                comparison = "lte"
            elif re.search(r"\bbefore\s*$", before):
                comparison = "lt"

        if not ranges:
            trailing_window = re.search(
                r"\b(?:last|past|previous)\s+(\d+)\s+days?\b", query, re.I
            )
            if trailing_window:
                days = int(trailing_window.group(1))
                if days > 0:
                    end = self._today()
                    start = end - timedelta(days=days - 1)
                    ranges.append(
                        self._range(
                            trailing_window.group(0),
                            "rolling_days",
                            start,
                            end,
                            trailing_window.span(),
                        )
                    )

        ranges.sort(key=lambda item: item["span"])

        return {
            "mapping": mapping,
            "invalid_dates": invalid_dates,
            "ranges": ranges,
            "comparison": comparison,
            "target": self._date_target(query),
        }

    @staticmethod
    def _target_expression(target: dict, layer: str = None) -> str:
        if (
            target["column_name"] == "oppclosedate"
            and str(layer or "").upper() == "OLTP"
        ):
            return "TO_DATE(NULLIF(f.oppclosedate, ''), 'MM/DD/YYYY')"
        return target["column"]

    @classmethod
    def _target_guidance(cls, target: dict, layer: str = None) -> List[str]:
        if target["uses_dateid"]:
            return [
                "The question does not name a special business date, so filter f.dateid.",
                "DateID is an INTEGER in YYYYMMDD form; do not quote it or compare dim_date.date.",
            ]

        lines = [
            f"The question explicitly refers to {target['label']}; filter {cls._target_expression(target, layer)}, not f.dateid.",
            "Named DATE columns use ISO PostgreSQL literals such as DATE '2025-01-31'.",
        ]
        if target["column_name"] == "oppclosedate":
            if str(layer or "").upper() == "OLTP":
                lines.append(
                    "oppclosedate is MM/DD/YYYY text in OLTP; parse it with TO_DATE before comparison."
                )
            elif str(layer or "").upper() == "OLAP":
                lines.append("oppclosedate is a native DATE column in OLAP.")
            else:
                lines.append(
                    "oppclosedate is DATE in OLAP but MM/DD/YYYY text in OLTP; on OLTP use "
                    "TO_DATE(NULLIF(f.oppclosedate, ''), 'MM/DD/YYYY') before comparison."
                )
        return lines

    def create_dateid_replacement_instructions(
        self, query: str, layer: str = None
    ) -> str:
        """Create unambiguous date-filter instructions for SQL generation."""
        analysis = self._analysis(query)
        target = analysis["target"]
        lines = ["\n### DATE FILTERING"]
        lines.extend(f"- {line}" for line in self._target_guidance(target, layer))

        for invalid in analysis["invalid_dates"]:
            lines.append(
                f"- INVALID DATE INPUT '{invalid}': it is not a valid complete calendar date. "
                "Do not guess or silently reinterpret it."
            )

        if not analysis["ranges"]:
            lines.append(
                "- Use a date predicate only if the question actually requests a date period."
            )
            lines.append(
                "- closedate, createddate, shipdate, expectedclosedate, and oppclosedate are "
                "separate business dates; use one only when the user explicitly names that meaning."
            )
            return "\n".join(lines) + "\n"

        lines.append("- Resolved date filters:")
        for item in analysis["ranges"]:
            if target["uses_dateid"]:
                if analysis["comparison"]:
                    operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[
                        analysis["comparison"]
                    ]
                    boundary = (
                        item["end_dateid"]
                        if analysis["comparison"] in {"gt", "lte"}
                        else item["start_dateid"]
                    )
                    predicate = f"f.dateid {operator} {boundary}"
                elif item["start_dateid"] == item["end_dateid"]:
                    predicate = f"f.dateid = {item['start_dateid']}"
                else:
                    predicate = (
                        f"f.dateid BETWEEN {item['start_dateid']} "
                        f"AND {item['end_dateid']}"
                    )
            else:
                expression = self._target_expression(target, layer)
                if analysis["comparison"]:
                    operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[
                        analysis["comparison"]
                    ]
                    boundary = (
                        item["end_iso"]
                        if analysis["comparison"] in {"gt", "lte"}
                        else item["start_iso"]
                    )
                    predicate = f"{expression} {operator} DATE '{boundary}'"
                elif item["start_iso"] == item["end_iso"]:
                    predicate = f"{expression} = DATE '{item['start_iso']}'"
                else:
                    predicate = (
                        f"{expression} BETWEEN DATE '{item['start_iso']}' "
                        f"AND DATE '{item['end_iso']}'"
                    )
            lines.append(f"  - '{item['original']}' -> {predicate}")

        return "\n".join(lines) + "\n"

    def get_date_context_for_llm(self, query: str) -> str:
        """Return compact structured date context for callers that need it."""
        analysis = self._analysis(query)
        if not analysis["ranges"] and not analysis["invalid_dates"]:
            return ""

        context = ["\n### DATE INFORMATION"]
        context.append(
            f"Date meaning: {analysis['target']['label']} ({analysis['target']['column']})"
        )
        for item in analysis["ranges"]:
            context.append(
                f"- {item['original']}: {item['start_dateid']} through {item['end_dateid']}"
            )
        for invalid in analysis["invalid_dates"]:
            context.append(f"- Invalid date input (must not be guessed): {invalid}")
        return "\n".join(context) + "\n"

    def extract_date_filters(self, query: str) -> dict:
        """Extract exact dates, calendar ranges, invalid inputs, and date intent."""
        analysis = self._analysis(query)
        public_ranges = [
            {key: value for key, value in item.items() if key != "span"}
            for item in analysis["ranges"]
        ]
        return {
            "has_date_filter": bool(public_ranges),
            "dates_found": [item["original"] for item in public_ranges],
            # Preserve the legacy DateID mapping while exposing range metadata.
            "dateids": {value: value for value in analysis["mapping"].values()},
            "ranges": public_ranges,
            "invalid_dates": analysis["invalid_dates"],
            "date_column": analysis["target"]["column"],
            "date_intent": analysis["target"]["label"],
            "uses_dateid": analysis["target"]["uses_dateid"],
            "comparison": analysis["comparison"],
        }
