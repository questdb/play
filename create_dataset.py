#!/usr/bin/env python3

import sys
sys.dont_write_bytecode = True
import pandas as pd


def main():
    df = pd.read_csv(
        'https://data.open-power-system-data.org/time_series/2020-10-06/' +
        'time_series_15min_singleindex.csv')

    # upper bound is exclusive, so only 2018 and 2019 here
    df = df.loc[df["utc_timestamp"].between("2018-01-01", "2020-01-01")]

    country_rows = []
    country_codes = ['AT', 'BE', 'DE', 'HU', 'LU', 'NL']
    common_columns = ['utc_timestamp']
    base_column_names = [
        'load_actual_entsoe_transparency',
        'load_forecast_entsoe_transparency']

    for country_code in country_codes:
        local_column_names = [
            country_code + '_' + sub
            for sub in base_column_names]
        country_columns = common_columns + local_column_names
        country_df = df.filter(country_columns)
        country_df.dropna(inplace=True)
        country_df.columns = common_columns + base_column_names
        country_df['country_code'] = country_code
        country_rows.append(country_df)

    all_countries = pd.concat(country_rows).rename(columns={
        'utc_timestamp': 'timestamp',
        'load_actual_entsoe_transparency': 'load_actual',
        'load_forecast_entsoe_transparency': 'load_forecast'})

    all_countries.timestamp = pd.to_datetime(
        all_countries.timestamp, format="%Y-%m-%dT%H:%M:%SZ")

    all_countries.to_parquet(
        'notebooks/energy.parquet.gzip',
        compression='gzip')


if __name__ == '__main__':
    main()
