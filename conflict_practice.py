# ============================================================
# conflict_practice.py  –  Merge Conflict Practice File
# ============================================================

def greet(name):
    """Return a greeting message."""
    # Team A: added a friendly emoji and department info
    message = "Hey " + name + "! Great to have you in the Data Engineering team! 🚀"
    return message

def calculate_bonus(salary):
    """Calculate employee bonus."""
    bonus_rate = 0.15          # Team A: increased bonus to 15%
    bonus = salary * bonus_rate
    return bonus

def get_pipeline_status():
    """Return the current pipeline status."""
    # Team A: added detailed status
    status = "RUNNING - All systems operational"
    return status
