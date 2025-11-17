"""Philippine holidays utilities."""
import datetime
from typing import List, Set

class PhilippineHolidays:
    """Utility class for handling Philippine holidays."""
    
    @staticmethod
    def get_fixed_holidays(year: int) -> List[datetime.date]:
        """Get fixed Philippine holidays for a given year."""
        return [
            datetime.date(year, 1, 1),   # New Year's Day
            datetime.date(year, 4, 9),   # Araw ng Kagitingan (Day of Valor)
            datetime.date(year, 5, 1),   # Labor Day
            datetime.date(year, 6, 12),  # Independence Day
            datetime.date(year, 8, 21),  # Ninoy Aquino Day
            datetime.date(year, 8, 26),  # National Heroes Day (last Monday of August)
            datetime.date(year, 11, 30), # Bonifacio Day
            datetime.date(year, 12, 8),  # Feast of the Immaculate Conception
            datetime.date(year, 12, 25), # Christmas Day
            datetime.date(year, 12, 30), # Rizal Day
            datetime.date(year, 12, 31), # New Year's Eve
        ]
    
    @staticmethod
    def get_variable_holidays(year: int) -> List[datetime.date]:
        """Get variable Philippine holidays for a given year (approximate dates)."""
        # These dates change yearly and would need to be updated
        # For now, providing common approximate dates
        holidays = []
        
        # Chinese New Year (varies)
        if year == 2025:
            holidays.append(datetime.date(2025, 1, 29))
        elif year == 2026:
            holidays.append(datetime.date(2026, 2, 17))
        
        # Maundy Thursday and Good Friday (varies based on Easter)
        easter_dates = PhilippineHolidays._get_easter_dates(year)
        holidays.extend(easter_dates)
        
        # Eid al-Fitr (varies)
        # These would need to be updated annually
        
        return holidays
    
    @staticmethod
    def _get_easter_dates(year: int) -> List[datetime.date]:
        """Calculate Easter dates for Maundy Thursday and Good Friday."""
        # Simple Easter calculation algorithm
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        n = (h + l - 7 * m + 114) // 31
        p = (h + l - 7 * m + 114) % 31
        
        easter = datetime.date(year, n, p + 1)
        maundy_thursday = easter - datetime.timedelta(days=3)
        good_friday = easter - datetime.timedelta(days=2)
        
        return [maundy_thursday, good_friday]
    
    @staticmethod
    def get_all_holidays(year: int) -> Set[datetime.date]:
        """Get all Philippine holidays for a given year."""
        fixed = PhilippineHolidays.get_fixed_holidays(year)
        variable = PhilippineHolidays.get_variable_holidays(year)
        return set(fixed + variable)
    
    @staticmethod
    def is_holiday(date: datetime.date) -> bool:
        """Check if a given date is a Philippine holiday."""
        holidays = PhilippineHolidays.get_all_holidays(date.year)
        return date in holidays
    
    @staticmethod
    def is_weekend(date: datetime.date) -> bool:
        """Check if a given date is a weekend (Saturday or Sunday)."""
        return date.weekday() >= 5  # 5 = Saturday, 6 = Sunday
    
    @staticmethod
    def is_workday(date: datetime.date) -> bool:
        """Check if a given date is a workday (not weekend or holiday)."""
        return not (PhilippineHolidays.is_weekend(date) or PhilippineHolidays.is_holiday(date))
    
    @staticmethod
    def get_next_workday(date: datetime.date) -> datetime.date:
        """Get the next workday after the given date."""
        next_date = date + datetime.timedelta(days=1)
        while not PhilippineHolidays.is_workday(next_date):
            next_date += datetime.timedelta(days=1)
        return next_date
    
    @staticmethod
    def get_workdays_in_week(start_date: datetime.date) -> List[datetime.date]:
        """Get all workdays in a week starting from Monday."""
        # Find the Monday of the week containing start_date
        days_since_monday = start_date.weekday()
        monday = start_date - datetime.timedelta(days=days_since_monday)
        
        workdays = []
        for i in range(5):  # Monday to Friday
            current_date = monday + datetime.timedelta(days=i)
            if PhilippineHolidays.is_workday(current_date):
                workdays.append(current_date)
        
        return workdays