#!/bin/bash

# Navigate to the app directory
cd "/Users/subhankarshukla/Desktop/aryan proj/valuation_app"

# Run the valuation app with logging
python3 valuation_professional.py companies_enhanced.csv 2>&1 | tee valuation_app_log.txt

# Keep the terminal open
echo ""
echo "Press any key to exit..."
read -n 1
