
"""
Predictions service for game predictions
"""
import random
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_current_period_number():
    """Get current period number using the real Tiranga algorithm"""
    from datetime import datetime

    # Step 1: Get current time
    now = datetime.now()

    # Step 2: Format date
    date_str = now.strftime("%Y%m%d")  # YYYYMMDD

    # Step 3: Fixed game code for 1-min game
    game_code = "10001"

    # Step 4: Calculate counter (minutes since 00:00) + 1 to match real period
    counter = now.hour * 60 + now.minute + 1
    counter_str = f"{counter:04d}"  # zero-padded to 4 digits

    # Final period number
    period_number = f"{date_str}{game_code}{counter_str}"
    return period_number


def should_generate_new_period(context):
    """Check if we should generate a new period (every minute)"""
    from datetime import datetime

    # Get current and stored period numbers
    current_period = get_current_period_number()
    stored_period = context.bot_data.get('current_period')

    # Generate new period if period number has changed
    return stored_period != current_period


def generate_auto_prediction(context):
    """Generate automatic prediction with all components"""
    import random
    from datetime import datetime

    # Get current period number from "server"
    current_period = get_current_period_number()

    # Check if we should generate new prediction (only when period changes)
    should_generate_new_pred = should_generate_new_period(context)

    if should_generate_new_pred:
        # Generate Big/Small
        purchase_type = random.choice(["Big", "Small"])

        # Generate Color (Green/Red 95%, Violet 5%)
        color_roll = random.randint(1, 100)
        if color_roll <= 5:
            color = "Violet"
        else:
            color = random.choice(["Green", "Red"])

        # Generate Numbers based on Big/Small
        if purchase_type == "Big":
            # Big: numbers 5,6,7,8,9
            available_numbers = [5, 6, 7, 8, 9]
        else:
            # Small: numbers 0,1,2,3,4
            available_numbers = [0, 1, 2, 3, 4]

        # Select 2 random numbers from available set
        selected_numbers = random.sample(available_numbers, 2)
        selected_numbers.sort()

        # Store prediction data with current period
        context.bot_data['auto_prediction_data'] = {
            'period': current_period,
            'purchase_type': purchase_type,
            'color': color,
            'numbers': selected_numbers,
            'generated_time': datetime.now()
        }
        context.bot_data['last_period_time'] = datetime.now()
        context.bot_data['current_period'] = current_period
    else:
        # Use existing prediction data but update period if changed
        prediction_data = context.bot_data.get('auto_prediction_data', {})

        # Check if period changed (new minute)
        stored_period = context.bot_data.get('current_period')
        if stored_period != current_period:
            # Period changed, keep same prediction but update period
            context.bot_data['current_period'] = current_period
            if prediction_data:
                context.bot_data['auto_prediction_data'][
                    'period'] = current_period

        # Get existing prediction data
        purchase_type = prediction_data.get('purchase_type', 'Big')
        color = prediction_data.get('color', 'Green')
        selected_numbers = prediction_data.get('numbers', [3, 6])

    # Always return current period, but prediction only changes when new period is generated
    final_period = context.bot_data.get('current_period', current_period)
    final_prediction = context.bot_data.get('auto_prediction_data', {})

    return (final_period, final_prediction.get('purchase_type', 'Big'),
            final_prediction.get('color', 'Green'),
            final_prediction.get('numbers', [3, 6]))


def generate_aviator_prediction(round_id):
    """Generate aviator prediction based on round ID with range 1.0x to 3.0x"""
    import random
    
    # Generate multipliers from 1.0x to 3.0x with 0.2x increments
    # 1.0x, 1.2x, 1.4x, 1.6x, 1.8x, 2.0x, 2.2x, 2.4x, 2.6x, 2.8x, 3.0x
    multipliers = []
    for i in range(11):  # 0 to 10
        multiplier = 1.0 + (i * 0.2)
        multipliers.append(f"{multiplier:.1f}x")
    
    # Weighted probability distribution for more realistic aviator game
    rand = random.random()
    
    if rand < 0.35:  # 35% - Lower multipliers (1.0x-1.8x)
        low_multipliers = ["1.0x", "1.2x", "1.4x", "1.6x", "1.8x"]
        return random.choice(low_multipliers)
    elif rand < 0.70:  # 35% - Medium multipliers (2.0x-2.6x)
        medium_multipliers = ["2.0x", "2.2x", "2.4x", "2.6x"]
        return random.choice(medium_multipliers)
    else:  # 30% - Higher multipliers (2.8x-3.0x)
        high_multipliers = ["2.8x", "3.0x"]
        return random.choice(high_multipliers)
