import json
from datetime import datetime
from dateutil.relativedelta import relativedelta

class ProfessionalExperienceCalculator:
    """
    A class to calculate professional experience from CV data in decimal years.
    """
    
    def __init__(self, file_path=None, cv_data_dict=None):
        """
        Initialize the calculator with CV data.
        
        Args:
            file_path (str, optional): Path to JSON file containing CV data
            cv_data_dict (dict, optional): Dictionary containing CV data
        """
        self.cv_data = self._load_cv_data(file_path, cv_data_dict)
        self.experience_summary = None
    
    def _load_cv_data(self, file_path=None, cv_data_dict=None):
        """
        Load CV data from file or use provided dictionary.
        
        Args:
            file_path (str, optional): Path to JSON file
            cv_data_dict (dict, optional): CV data dictionary
            
        Returns:
            dict: CV data
        
        Raises:
            FileNotFoundError: If file_path is invalid
            json.JSONDecodeError: If JSON is invalid
        """
        if cv_data_dict:
            return cv_data_dict
        
        if file_path:
            with open(file_path, 'r') as file:
                return json.load(file)
        
        return {"CV_data": {"work_experience": []}}
    
    def _parse_date(self, date_str):
        """
        Parse date string to datetime object.
        
        Args:
            date_str (str): Date string (e.g., 'November 2023', 'Nov 2023', '2023')
            
        Returns:
            datetime: Parsed datetime or current date if parsing fails
        """
        if not date_str or date_str.lower() == 'present':
            return datetime.now()
        
        date_str = date_str.strip()
        try:
            return datetime.strptime(date_str, "%B %Y")
        except ValueError:
            try:
                return datetime.strptime(date_str, "%b %Y")
            except ValueError:
                try:
                    return datetime.strptime(date_str, "%Y")
                except ValueError:
                    return datetime.now()
    
    def _merge_intervals(self, intervals):
        """
        Merge overlapping intervals.
        
        Args:
            intervals: list of (start_datetime, end_datetime)
            
        Returns:
            list: Merged intervals
        """
        if not intervals:
            return []

        intervals.sort(key=lambda x: x[0])
        merged = [intervals[0]]

        for current_start, current_end in intervals[1:]:
            last_start, last_end = merged[-1]
            if current_start <= last_end:
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                merged.append((current_start, current_end))
        
        return merged
    
    def calculate_experience(self):
        """
        Calculate total professional experience in decimal years.
        
        Returns:
            float: Total years of experience (decimal)
        """
        try:
            work_experiences = self.cv_data['CV_data']['structured_data'].get('work_experience', [])
        except KeyError:
            return 0.0

        intervals = []
        for job in work_experiences:
            start_date_str = job.get('start_date')
            if not start_date_str:
                continue
            start_date = self._parse_date(start_date_str)
            end_date = self._parse_date(job.get('end_date'))
            intervals.append((start_date, end_date))

        merged_intervals = self._merge_intervals(intervals)

        total_months = 0
        for start, end in merged_intervals:
            diff = relativedelta(end, start)
            total_months += diff.years * 12 + diff.months

        return round(total_months / 12, 2)
    
    def update_cv_data(self, file_path=None, cv_data_dict=None):
        """
        Update the CV data and reset experience summary.
        
        Args:
            file_path (str, optional): Path to new JSON file
            cv_data_dict (dict, optional): New CV data dictionary
        """
        self.cv_data = self._load_cv_data(file_path, cv_data_dict)
        self.experience_summary = None
    
    def get_total_years(self):
        """
        Get total experience in years (decimal).
        
        Returns:
            float: Total years of experience
        """
        if self.experience_summary is None:
            self.experience_summary = self.calculate_experience()
        return self.experience_summary