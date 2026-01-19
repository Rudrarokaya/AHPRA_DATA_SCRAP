"""
HTML Parser for AHPRA practitioner detail pages.

Extracts all 16 required fields from practitioner profiles.
"""

import re
from typing import Dict, Optional, Any
from bs4 import BeautifulSoup
from loguru import logger

from config.settings import DATA_FIELDS


class PractitionerParser:
    """
    Parses AHPRA practitioner detail pages to extract required fields.

    AHPRA page structure (as of Jan 2026):
    - Name: <h2 class="practitioner-name">
    - Profession: <h3 class="practitioner-profession">
    - Division: <div class="reg-types"><span class="reg-type-1">
    - Reg Number: <span class="reg-number">
    - Fields: <div class="field-title"> paired with <div class="field-entry">
    """

    def __init__(self):
        """Initialize the parser."""
        self._soup = None
        self._field_map = {}  # Cache for field-title/field-entry pairs

    def parse(self, html_content: str) -> Dict[str, Any]:
        """
        Parse HTML content and extract all practitioner fields.

        Args:
            html_content: Raw HTML of practitioner detail page

        Returns:
            Dictionary with extracted fields
        """
        self._soup = BeautifulSoup(html_content, 'lxml')

        # Initialize result with all fields
        result = {field: None for field in DATA_FIELDS}

        try:
            # Build field map from field-title/field-entry pairs
            self._build_field_map()

            # Extract each field
            self._extract_name(result)
            self._extract_reg_id(result)
            self._extract_profession(result)
            self._extract_divisions(result)
            self._extract_registration_status(result)
            self._extract_registration_dates(result)
            self._extract_endorsements(result)
            self._extract_location(result)
            self._extract_sex(result)

        except Exception as e:
            logger.error(f"Error parsing practitioner page: {e}")

        return result

    def _build_field_map(self) -> None:
        """
        Build a map of field titles to their values from field-title/field-entry pairs.
        """
        self._field_map = {}

        # Find all section-row divs containing field-title and field-entry
        section_rows = self._soup.select('.section-row')

        for row in section_rows:
            title_elem = row.select_one('.field-title')
            entry_elem = row.select_one('.field-entry')

            if title_elem and entry_elem:
                title = title_elem.get_text(strip=True).lower()
                value = entry_elem.get_text(strip=True)
                if title and value:
                    self._field_map[title] = value

    def _get_field(self, *field_names) -> Optional[str]:
        """
        Get a field value by trying multiple possible field names.

        Args:
            field_names: Possible field name variations to try

        Returns:
            Field value or None
        """
        for name in field_names:
            name_lower = name.lower()
            for key, value in self._field_map.items():
                if name_lower in key:
                    return value
        return None

    def _extract_name(self, result: Dict) -> None:
        """Extract name fields from practitioner-name element."""
        try:
            # Primary: h2.practitioner-name
            name_elem = self._soup.select_one('h2.practitioner-name')
            if name_elem:
                full_name = name_elem.get_text(strip=True)
                result['name'] = full_name
                self._parse_name_parts(full_name, result)
                return

            # Fallback: page title
            title = self._soup.find('title')
            if title:
                name_text = title.get_text(strip=True)
                name_text = re.sub(r'\s*[-|]\s*AHPRA.*$', '', name_text)
                if name_text:
                    result['name'] = name_text
                    self._parse_name_parts(name_text, result)

        except Exception as e:
            logger.debug(f"Error extracting name: {e}")

    def _parse_name_parts(self, full_name: str, result: Dict) -> None:
        """Parse full name into components (title, first, middle, last)."""
        titles = ['Dr', 'Mr', 'Mrs', 'Ms', 'Miss', 'Prof', 'Professor', 'Associate Professor']

        name = full_name.strip()

        # Extract title
        for title in titles:
            if name.startswith(title + ' ') or name.startswith(title + '.'):
                result['name_title'] = title
                name = name[len(title):].strip(' .')
                break

        # Split remaining name
        parts = name.split()
        if len(parts) >= 1:
            result['first_name'] = parts[0]
        if len(parts) >= 2:
            result['last_name'] = parts[-1]
        if len(parts) >= 3:
            result['middle_name'] = ' '.join(parts[1:-1])

    def _extract_reg_id(self, result: Dict) -> None:
        """Extract registration ID."""
        try:
            # Primary: span.reg-number
            reg_elem = self._soup.select_one('span.reg-number')
            if reg_elem:
                text = reg_elem.get_text(strip=True)
                match = re.search(r'([A-Z]{3}\d{10,})', text)
                if match:
                    result['reg_id'] = match.group(1)
                    return

            # Fallback: field map
            reg_number = self._get_field('registration number')
            if reg_number:
                match = re.search(r'([A-Z]{3}\d{10,})', reg_number)
                if match:
                    result['reg_id'] = match.group(1)
                    return

            # Last resort: search page text
            page_text = self._soup.get_text()
            match = re.search(r'([A-Z]{3}\d{10,})', page_text)
            if match:
                result['reg_id'] = match.group(1)

        except Exception as e:
            logger.debug(f"Error extracting reg_id: {e}")

    def _extract_profession(self, result: Dict) -> None:
        """Extract profession from practitioner-profession element."""
        try:
            # Primary: h3.practitioner-profession
            prof_elem = self._soup.select_one('h3.practitioner-profession')
            if prof_elem:
                result['profession'] = prof_elem.get_text(strip=True)
                return

            # Fallback: field map
            profession = self._get_field('profession')
            if profession:
                result['profession'] = profession

        except Exception as e:
            logger.debug(f"Error extracting profession: {e}")

    def _extract_divisions(self, result: Dict) -> None:
        """Extract professional divisions from reg-types element."""
        try:
            # Primary: div.reg-types > span[class^="reg-type"]
            reg_types = self._soup.select('.reg-types span[class^="reg-type"]')
            if reg_types:
                divisions = [rt.get_text(strip=True) for rt in reg_types]
                result['divisions'] = '; '.join(divisions)
                return

            # Fallback: look for division in field map
            division = self._get_field('division', 'divisions')
            if division:
                result['divisions'] = division

        except Exception as e:
            logger.debug(f"Error extracting divisions: {e}")

    def _extract_registration_status(self, result: Dict) -> None:
        """Extract registration status."""
        try:
            # From field map
            status = self._get_field('registration status')
            if status:
                result['registration_status'] = status
                return

            # Fallback: search for status keywords
            page_text = self._soup.get_text()
            statuses = ['Registered', 'Suspended', 'Cancelled', 'Non-practising']
            for status in statuses:
                if re.search(rf'\b{status}\b', page_text, re.IGNORECASE):
                    result['registration_status'] = status
                    return

        except Exception as e:
            logger.debug(f"Error extracting registration status: {e}")

    def _extract_registration_dates(self, result: Dict) -> None:
        """Extract first registration date and expiry date."""
        try:
            # First registration date from field map
            first_reg = self._get_field('date of first registration', 'first registered')
            if first_reg:
                result['first_reg_date'] = self._normalize_date(first_reg)

            # Expiry date from field map
            expiry = self._get_field('registration expiry date', 'expiry date')
            if expiry:
                # Clean up - remove explanatory text
                expiry = expiry.split('.')[0] if '.' in expiry else expiry
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', expiry)
                if date_match:
                    result['reg_expiry'] = self._normalize_date(date_match.group(1))
                else:
                    result['reg_expiry'] = self._normalize_date(expiry)

        except Exception as e:
            logger.debug(f"Error extracting dates: {e}")

    def _normalize_date(self, date_str: str) -> str:
        """Normalize date string to DD/MM/YYYY format."""
        try:
            date_str = ' '.join(date_str.split())
            from datetime import datetime

            formats = [
                '%d/%m/%Y', '%d-%m-%Y', '%d %B %Y', '%d %b %Y',
                '%Y-%m-%d', '%m/%d/%Y',
            ]

            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%d/%m/%Y')
                except ValueError:
                    continue

            return date_str

        except Exception:
            return date_str

    def _extract_endorsements(self, result: Dict) -> None:
        """Extract endorsements from field map."""
        try:
            endorsement = self._get_field('endorsement', 'endorsements')
            if endorsement and endorsement.lower() != 'none':
                result['endorsement'] = endorsement

        except Exception as e:
            logger.debug(f"Error extracting endorsements: {e}")

    def _extract_location(self, result: Dict) -> None:
        """Extract practice location (suburb, state, postcode) from field map."""
        try:
            # Get individual location fields
            suburb = self._get_field('suburb')
            state = self._get_field('state')
            postcode = self._get_field('postcode')

            if suburb:
                result['suburb'] = suburb
            if state:
                result['state'] = state
            if postcode:
                result['postcode'] = postcode

        except Exception as e:
            logger.debug(f"Error extracting location: {e}")

    def _extract_sex(self, result: Dict) -> None:
        """Extract sex/gender from field map."""
        try:
            sex = self._get_field('sex', 'gender')
            if sex:
                result['sex'] = sex.capitalize()

        except Exception as e:
            logger.debug(f"Error extracting sex: {e}")
