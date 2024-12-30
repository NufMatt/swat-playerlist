from datetime import datetime, timedelta

def convert_time(input_str):
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_of_week_str, time_str = input_str.split()
    day_of_week = (weekdays.index(day_of_week_str))+1
    input_time = datetime.strptime(time_str, "%H:%M").replace(year=datetime.now().year)
    now = datetime.now()
    days_difference = (day_of_week - now.weekday()) % 7
    target_day = now + timedelta(days=days_difference)
    input_datetime = target_day.replace(hour=input_time.hour, minute=input_time.minute, second=0, microsecond=0)
    now = input_datetime
    days_until_saturday = (5 - now.weekday()) % 7
    saturday = now + timedelta(days=days_until_saturday)
    saturday_2359 = saturday.replace(hour=23, minute=59, second=0, microsecond=0)
    remaining_time = saturday_2359 - now
    remaining_minutes = remaining_time.total_seconds() / 60
    game_minutes = remaining_minutes / 48
    hours = int(game_minutes // 60)
    remaining_minutes = int(game_minutes % 60)
    
    if hours == 1:
        restart_timer = f"Next restart in ~{hours} hour and {remaining_minutes} minutes"
    elif hours > 1:
        restart_timer = f"Next restart in ~{hours} hours and {remaining_minutes} minutes"
    else:
        restart_timer = f"Next restart in ~{remaining_minutes} minutes"
    return restart_timer

print(convert_time("Monday 05:59"))
