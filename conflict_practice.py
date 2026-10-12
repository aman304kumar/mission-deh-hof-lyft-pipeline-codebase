# ============================================================
# conflict_practice.py  –  Merge Conflict Practice File
# ============================================================

def greet(name):
    """Return a greeting message."""
    # Master: formal greeting with company name
    message = "Dear " + name + ", welcome to Mission DEH. Please review the onboarding docs."
    return message

def calculate_bonus(salary):
    """Calculate employee bonus."""
    bonus_rate = 0.05          # Master: conservative bonus rate of 5%
    bonus = salary * bonus_rate
    return bonus

def get_pipeline_status():
    """Return the current pipeline status."""
    # Master: added environment tag
    status = "RUNNING [env=production]"
    return status
