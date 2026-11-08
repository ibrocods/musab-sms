def format_student_id(pattern, year, sequence):
    """Build a student ID from the school's pattern, for example {year}/{seq:04d}."""
    return pattern.format(year=year, seq=sequence)