def calculate_priority(created_utc, now):
    age_minutes = (now - created_utc) / 60

    if age_minutes < 5:
        return "aggressive"
    elif age_minutes < 60:
        return "normal"
    elif age_minutes < 1440:
        return "slow"
    else:
        return "inactive"
