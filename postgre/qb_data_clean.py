import pandas as pd

# Load CSV handling encoding automatically
try:
  df = pd.read_csv(
      r'C:\Users\Admin\Downloads\Dahboard_data\hourly_sales.csv',
      dtype=str,
      encoding='utf-8',
  )
except UnicodeDecodeError:
  df = pd.read_csv(
      r'C:\Users\Admin\Downloads\Dahboard_data\hourly_sales.csv',
      dtype=str,
      encoding='latin1',
  )

# Remove internal line breaks
df = df.replace(r'[\r\n]+', ' ', regex=True)

# Standardize date column format (handles mixed MDY/DMY automatically)
df['date'] = pd.to_datetime(df['date'], format='mixed').dt.strftime('%Y-%m-%d')

# Save clean version
df.to_csv(
    r'C:\Users\Admin\Downloads\Dahboard_data\hourly_sales_clean.csv',
    index=False,
    encoding='utf-8',
)

print('hourly_sales_clean.csv standardized successfully!')