from analytics.services.clusters import export_portfolio_stocks_to_csv_and_json

def run(*args):
    portfolio_id = int(args[0]) if args else 1
    export_portfolio_stocks_to_csv_and_json(portfolio_id)
